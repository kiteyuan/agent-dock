import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:web_socket_channel/io.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../audio/player.dart';
import '../audio/recorder.dart';
import '../models/chat_message.dart';
import '../pets/pet_catalog.dart';
import '../protocol/messages.dart' as proto;
import 'client_state.dart';

export '../models/chat_message.dart';

class DeviceSession {
  DeviceSession({
    required this.deviceId,
    this.deviceType = 'mobile',
  });

  final String deviceId;
  final String deviceType;

  WebSocketChannel? _ws;
  StreamSubscription? _sub;
  Timer? _heartbeat;
  Timer? _reconnectTimer;
  bool _wantConnected = false;
  bool _connecting = false;
  bool _intentionalClose = false;

  final WavRecorder recorder = WavRecorder();
  final TtsPlayer player = TtsPlayer();

  ClientState state = ClientState.offline;
  String? sessionId;
  String? lastError;
  String statusLine = '';
  /// Agent reply target text this turn (typewriter chases this).
  String _assistantTurnText = '';
  Timer? _typeTimer;
  int _typeToken = 0;
  /// Draft mirrored into the chat composer (cleared after STT → bubble).
  String composerText = '';
  /// Hint for composer placeholder while listening / recognizing.
  String composerHint = '有问题，随便问';

  /// Chat transcript (persisted by UI).
  final List<ChatMessage> messages = [];
  static const msgLimit = 50;
  String? activeAssistantId;
  /// Muted one-line process trail for the current turn.
  String processLine = '';

  String url = 'ws://127.0.0.1:8765';
  String token = '';
  String ttsId = '';
  String petId = '';
  List<Map<String, dynamic>> ttsProviders = const [];
  String? ttsDefaultId;
  String? petDefaultId;
  int petsEpoch = 0;

  final List<int> _ttsBuf = [];
  String _ttsPendingText = '';
  bool _awaitingIdle = false;
  /// After barge-in / cancel, ignore late TTS until the next turn starts.
  bool _dropRemoteTts = false;
  String _thinkingBuf = '';
  DateTime? _lastThinkingFlush;
  static const _thinkingMin = Duration(milliseconds: 400);
  static const _processMaxLen = 72;

  final _changes = StreamController<void>.broadcast();
  Stream<void> get changes => _changes.stream;

  bool get canToggleTalk =>
      sessionId != null &&
      (state == ClientState.idle ||
          state == ClientState.listening ||
          state == ClientState.busy ||
          state == ClientState.speaking ||
          state == ClientState.error);

  bool get canReplay {
    ChatMessage? lastAssistant;
    for (final m in messages.reversed) {
      if (m.role == ChatRole.assistant) {
        lastAssistant = m;
        break;
      }
    }
    return sessionId != null &&
        !player.isBusy &&
        player.lastTurn.isNotEmpty &&
        lastAssistant != null &&
        lastAssistant.text.trim().isNotEmpty;
  }

  bool get canComposeText =>
      sessionId != null &&
      _ws != null &&
      state != ClientState.offline &&
      state != ClientState.connecting &&
      state != ClientState.error;

  void _notify() {
    if (!_changes.isClosed) _changes.add(null);
  }

  String encodeMessages() => jsonEncode([
        for (final m in messages.take(msgLimit)) m.toJson(),
      ]);

  void loadMessagesJson(String? raw) {
    messages.clear();
    activeAssistantId = null;
    if (raw == null || raw.isEmpty) return;
    try {
      final parsed = jsonDecode(raw);
      if (parsed is! List) return;
      for (final item in parsed) {
        if (item is! Map) continue;
        final m = ChatMessage.fromJson(Map<String, dynamic>.from(item));
        if (m != null) messages.add(m);
      }
      if (messages.length > msgLimit) {
        messages.removeRange(0, messages.length - msgLimit);
      }
    } catch (_) {
      messages.clear();
    }
  }

  void clearMessages() {
    _stopTypewriter();
    messages.clear();
    activeAssistantId = null;
    processLine = '';
    _assistantTurnText = '';
    _notify();
  }

  void _trimMessages() {
    if (messages.length > msgLimit) {
      messages.removeRange(0, messages.length - msgLimit);
    }
  }

  void _appendUser(String text, {List<Uint8List> imageBytes = const []}) {
    final t = _plainReply(text);
    if (t.isEmpty && imageBytes.isEmpty) return;
    _stopTypewriter();
    activeAssistantId = null;
    _assistantTurnText = '';
    processLine = '';
    messages.add(ChatMessage(
      id: newChatId(),
      role: ChatRole.user,
      text: t,
      imageBytes: List<Uint8List>.from(imageBytes),
    ));
    _trimMessages();
    _notify();
  }

  ChatMessage _ensureAssistant() {
    if (activeAssistantId != null) {
      for (final m in messages) {
        if (m.id == activeAssistantId) return m;
      }
    }
    final id = newChatId();
    activeAssistantId = id;
    final msg = ChatMessage(id: id, role: ChatRole.assistant, text: '');
    messages.add(msg);
    _trimMessages();
    return msg;
  }

  void _setAssistantText(String text) {
    _stopTypewriter();
    final msg = _ensureAssistant();
    msg.text = text;
    _notify();
  }

  void _appendAssistantChunk(String raw) {
    final t = raw.replaceAll('\r\n', '\n');
    if (t.trim().isEmpty) return;
    final sep = _assistantTurnText.isEmpty
        ? ''
        : _joinSep(_assistantTurnText, t);
    _assistantTurnText = '$_assistantTurnText$sep$t';
    _clearProcessLine();
    _ensureAssistant();
    _ensureTypewriterRunning();
  }

  void _stopTypewriter({bool snap = false}) {
    _typeToken++;
    _typeTimer?.cancel();
    _typeTimer = null;
    if (snap && activeAssistantId != null && _assistantTurnText.isNotEmpty) {
      for (final m in messages) {
        if (m.id == activeAssistantId) {
          m.text = _assistantTurnText;
          break;
        }
      }
      _notify();
    }
  }

  void _finishTypewriter() => _stopTypewriter(snap: true);

  Duration _typeInterval(int behind) {
    if (behind > 60) return const Duration(milliseconds: 10);
    if (behind > 24) return const Duration(milliseconds: 16);
    return const Duration(milliseconds: 22);
  }

  int _charsThisTick(int behind) {
    if (behind > 48) return 3;
    if (behind > 18) return 2;
    return 1;
  }

  void _ensureTypewriterRunning() {
    if (_typeTimer != null) return;
    final my = ++_typeToken;
    void tick() {
      if (my != _typeToken) return;
      final id = activeAssistantId;
      final target = _assistantTurnText;
      if (id == null || target.isEmpty) {
        _stopTypewriter();
        return;
      }
      ChatMessage? msg;
      for (final m in messages) {
        if (m.id == id) {
          msg = m;
          break;
        }
      }
      if (msg == null) {
        _stopTypewriter();
        return;
      }
      final cur = msg.text;
      if (cur.length >= target.length) {
        _stopTypewriter();
        return;
      }
      final behind = target.length - cur.length;
      final n = _charsThisTick(behind);
      msg.text = target.substring(0, cur.length + n);
      _notify();
      _typeTimer?.cancel();
      if (my != _typeToken) return;
      if (msg.text.length >= target.length) {
        _typeTimer = null;
        return;
      }
      _typeTimer = Timer(_typeInterval(behind - n), tick);
    }

    _typeTimer = Timer(Duration.zero, tick);
  }

  String _joinSep(String prev, String next) {
    if (prev.isEmpty) return '';
    final last = prev[prev.length - 1];
    if (RegExp(r'\s').hasMatch(last)) return '';
    if (RegExp(
      r'[\u3000-\u303F\u4E00-\u9FFF\uFF00-\uFFEF。！？…」』）】]',
    ).hasMatch(last)) {
      return '';
    }
    if (next.isNotEmpty &&
        RegExp(r'[，。！？、；：…」』）】,.!?;:]').hasMatch(next[0])) {
      return '';
    }
    return ' ';
  }

  String _clipProcess(String s) {
    final t = s.replaceAll(RegExp(r'\s+'), ' ').trim();
    if (t.length <= _processMaxLen) return t;
    return '…${t.substring(t.length - (_processMaxLen - 1))}';
  }

  String _nativeProcessText(String type, Map<String, dynamic> payload) {
    final content = '${payload['content'] ?? payload['text'] ?? ''}'.trim();
    if (content.isNotEmpty) return content;
    if (type == 'agent.tool_call') {
      final tool = '${payload['tool'] ?? ''}'.trim();
      final args = payload['args'];
      if (args is Map && args.isNotEmpty) {
        return tool.isEmpty ? '$args' : '$tool $args';
      }
      return tool;
    }
    return '';
  }

  void _showProcessLine(String line) {
    if (_assistantTurnText.isNotEmpty) {
      _setState(ClientState.busy);
      return;
    }
    final s = _clipProcess(line);
    if (s.isEmpty) return;
    processLine = s;
    _setState(ClientState.busy);
  }

  void _clearProcessLine() {
    if (processLine.isEmpty) return;
    processLine = '';
    _notify();
  }

  String _plainReply(String raw) =>
      raw.replaceAll('\r\n', '\n').trim();

  Future<void> sendText(
    String raw, {
    List<Map<String, String>>? images,
    List<Uint8List>? previewBytes,
  }) async {
    final text = raw.trim();
    final imgs = images ?? const <Map<String, String>>[];
    final previews = previewBytes ?? const <Uint8List>[];
    if ((text.isEmpty && imgs.isEmpty) || sessionId == null || _ws == null) {
      return;
    }
    if (state == ClientState.listening) {
      try {
        await recorder.cancel();
      } catch (_) {}
    }
    if (state == ClientState.busy ||
        state == ClientState.speaking ||
        player.isBusy) {
      try {
        _ws!.sink.add(proto.sessionCancel(sessionId!));
      } catch (_) {}
    }
    _armDropRemoteTts();
    _awaitingIdle = false;
    _resetThinking();
    _clearProcessLine();
    composerText = '';
    composerHint = '有问题，随便问';
    final sendText = text.isNotEmpty
        ? text
        : (imgs.isNotEmpty ? '（发送了 ${imgs.length} 张图片）' : '');
    _appendUser(sendText, imageBytes: previews);
    _setState(ClientState.busy, status: '…');
    try {
      _ws!.sink.add(proto.userMessage(
        sessionId: sessionId!,
        text: sendText,
        images: imgs.isEmpty ? null : imgs,
      ));
    } catch (e) {
      _failTurn(e.toString());
    }
  }


  void _resetThinking() {
    _thinkingBuf = '';
    _lastThinkingFlush = null;
  }

  void _flushThinking({required bool finalFlush}) {
    final shown = _thinkingBuf.trim();
    if (shown.isEmpty) {
      if (finalFlush) _resetThinking();
      return;
    }
    final now = DateTime.now();
    if (!finalFlush &&
        _lastThinkingFlush != null &&
        now.difference(_lastThinkingFlush!) < _thinkingMin) {
      return;
    }
    _showProcessLine(shown);
    _lastThinkingFlush = now;
    if (finalFlush) _resetThinking();
  }

  void _setState(ClientState s, {String? status}) {
    state = s;
    if (status != null) statusLine = status;
    _notify();
  }

  Future<void> connect() async {
    _wantConnected = true;
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    if (_connecting) return;
    _connecting = true;
    await disconnect(silent: true, clearWant: false);
    lastError = null;
    _setState(ClientState.connecting, status: url);
    try {
      _ws = IOWebSocketChannel.connect(
        Uri.parse(url),
        pingInterval: const Duration(seconds: 20),
      );
      _sub = _ws!.stream.listen(
        _onData,
        onError: (Object e) {
          lastError = e.toString();
          activeAssistantId = null;
          _setAssistantText(lastError!);
          _setState(ClientState.error, status: lastError);
          if (!_intentionalClose) _scheduleReconnect();
        },
        onDone: () {
          sessionId = null;
          _heartbeat?.cancel();
          _setState(ClientState.offline, status: '未连接');
          if (!_intentionalClose) _scheduleReconnect();
        },
        cancelOnError: false,
      );
      _ws!.sink.add(proto.deviceHello(
        deviceId: deviceId,
        deviceType: deviceType,
        token: token.isEmpty ? null : token,
      ));
      _heartbeat = Timer.periodic(const Duration(seconds: 20), (_) {
        if (_ws != null && sessionId != null) {
          try {
            _ws!.sink.add(proto.ping());
          } catch (_) {
            _scheduleReconnect();
          }
        }
      });
      player.onBecameIdle = () {
        if (state == ClientState.speaking && !player.isBusy) {
          _setState(ClientState.idle, status: '在线');
        } else {
          _notify();
        }
      };
      player.onQueueChanged = _notify;
    } catch (e) {
      lastError = e.toString();
      _setState(ClientState.error, status: lastError);
      _scheduleReconnect();
    } finally {
      _connecting = false;
    }
  }

  Future<void> onAppResumed() async {
    if (!_wantConnected) return;
    if (sessionId == null ||
        state == ClientState.offline ||
        state == ClientState.error) {
      await connect();
      return;
    }
    try {
      _ws?.sink.add(proto.ping());
    } catch (_) {
      await connect();
    }
  }

  void _scheduleReconnect() {
    if (!_wantConnected || _connecting) return;
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(const Duration(seconds: 1), () {
      if (!_wantConnected) return;
      if (sessionId != null &&
          state != ClientState.offline &&
          state != ClientState.error) {
        return;
      }
      unawaited(connect());
    });
  }

  Future<void> disconnect({bool silent = false, bool clearWant = true}) async {
    if (clearWant) _wantConnected = false;
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    _heartbeat?.cancel();
    _heartbeat = null;
    _intentionalClose = true;
    await _sub?.cancel();
    _sub = null;
    try {
      await _ws?.sink.close();
    } catch (_) {}
    _ws = null;
    sessionId = null;
    _intentionalClose = false;
    player.clear();
    await recorder.cancel();
    if (!silent) {
      _setState(ClientState.offline, status: '未连接');
    }
  }

  Future<void> toggleTalk() async {
    if (state == ClientState.listening) {
      await _stopAndSend();
      return;
    }
    if (state == ClientState.busy) {
      await cancelTurn();
      return;
    }
    if (state == ClientState.speaking || player.isBusy) {
      // Cancel server turn so late TTS cannot refill while we listen.
      await cancelTurn();
    }
    if (sessionId == null) return;
    if (state != ClientState.idle && state != ClientState.error) return;
    await _startListen();
  }

  Future<void> replayLast() => player.replayLast();

  void _armDropRemoteTts() {
    _dropRemoteTts = true;
    player.clear();
    _ttsBuf.clear();
  }

  void _clearDropRemoteTts() {
    _dropRemoteTts = false;
  }

  Future<void> cancelTurn() async {
    if (sessionId == null || _ws == null) return;
    try {
      _ws!.sink.add(proto.sessionCancel(sessionId!));
    } catch (_) {}
    _armDropRemoteTts();
    _awaitingIdle = false;
    _stopTypewriter();
    _resetThinking();
    _clearProcessLine();
    composerText = '';
    composerHint = '有问题，随便问';
    await recorder.cancel();
    _setState(ClientState.idle, status: '已取消');
  }

  Future<void> resetConversation() async {
    if (sessionId == null || _ws == null) {
      lastError = '未连接';
      _notify();
      return;
    }
    if (state == ClientState.listening) {
      try {
        await recorder.cancel();
      } catch (_) {}
    }
    if (state == ClientState.busy || state == ClientState.speaking) {
      try {
        _ws!.sink.add(proto.sessionCancel(sessionId!));
      } catch (_) {}
      player.clear();
      _ttsBuf.clear();
    }
    _awaitingIdle = false;
    _resetThinking();
    clearMessages();
    try {
      _ws!.sink.add(proto.sessionReset(sessionId));
    } catch (e) {
      _failTurn(e.toString());
      return;
    }
    _setState(ClientState.idle, status: '已新开会话');
  }

  Future<void> _startListen() async {
    try {
      await recorder.start();
      _armDropRemoteTts();
      player.beginTurn();
      _awaitingIdle = false;
        _resetThinking();
      _clearProcessLine();
      composerText = '';
      composerHint = '正在听…';
      _setState(ClientState.listening, status: '正在录音…');
    } catch (e) {
      _failTurn(e.toString());
    }
  }

  Future<void> _stopAndSend() async {
    Uint8List? bytes;
    try {
      bytes = await recorder.stop();
    } catch (e) {
      composerHint = '有问题，随便问';
      _failTurn(e.toString());
      return;
    }
    if (bytes == null || bytes.isEmpty || _ws == null || sessionId == null) {
      composerHint = '有问题，随便问';
      _setState(ClientState.idle, status: '空录音');
      return;
    }
    composerText = '';
    composerHint = '识别中…';
    _setState(ClientState.busy, status: '识别中…');
    try {
      _ws!.sink.add(proto.audioStart(sessionId!));
      const chunk = 4096;
      for (var i = 0; i < bytes.length; i += chunk) {
        final end = (i + chunk < bytes.length) ? i + chunk : bytes.length;
        _ws!.sink.add(bytes.sublist(i, end));
      }
      _ws!.sink.add(proto.audioEnd(sessionId!));
    } catch (e) {
      composerHint = '有问题，随便问';
      _failTurn(e.toString());
    }
  }

  void _failTurn(String detail) {
    final text = detail.trim().isEmpty ? '出错了' : detail.trim();
    lastError = text;
    activeAssistantId = null;
    _setAssistantText(text);
    _armDropRemoteTts();
    _awaitingIdle = false;
    _resetThinking();
    _clearProcessLine();
    if (sessionId != null && _ws != null) {
      _setState(ClientState.error, status: text);
      return;
    }
    _setState(ClientState.error, status: text);
    _scheduleReconnect();
  }

  void _onData(dynamic data) {
    try {
      _onMessage(data);
    } catch (e) {
      _failTurn(e.toString());
    }
  }

  void _onMessage(dynamic data) {
    if (data is List<int>) {
      if (!_dropRemoteTts) _ttsBuf.addAll(data);
      return;
    }
    if (data is! String) return;
    final m = proto.decodeJson(data);
    if (m == null) return;
    final type = m['type'] as String? ?? '';
    final payload = (m['payload'] is Map)
        ? Map<String, dynamic>.from(m['payload'] as Map)
        : <String, dynamic>{};

    switch (type) {
      case 'session.accept':
        sessionId = payload['session_id'] as String?;
        final acceptTts = (payload['tts_id'] as String?)?.trim() ?? '';
        final acceptPet = (payload['pet_id'] as String?)?.trim() ?? '';
        if (acceptTts.isNotEmpty) ttsId = acceptTts;
        if (acceptPet.isNotEmpty) petId = acceptPet;
        _clearDropRemoteTts();
        _setState(ClientState.idle, status: '在线');
        _ws?.sink.add(proto.ttsList());
        _ws?.sink.add(proto.petsList());
        break;
      case 'tts.list.result':
        final providers = payload['providers'];
        if (providers is List) {
          ttsProviders = [
            for (final p in providers)
              if (p is Map) Map<String, dynamic>.from(p),
          ];
        } else {
          ttsProviders = const [];
        }
        ttsDefaultId = payload['default'] as String?;
        if ((ttsDefaultId ?? '').isNotEmpty) {
          ttsId = ttsDefaultId!;
        }
        _notify();
        break;
      case 'pets.list.result':
        _applyPets(payload);
        break;
      case 'session.reset.ok':
            clearMessages();
            _resetThinking();
        player.clear();
        _ttsBuf.clear();
        _dropRemoteTts = false;
        _awaitingIdle = false;
        _setState(ClientState.idle, status: '已新开会话');
        break;
      case 'error':
      case 'agent.error':
        _failTurn(
          '${payload['detail'] ?? payload['message'] ?? payload['content'] ?? payload['text'] ?? '出错了'}',
        );
        break;
      case 'stt.final':
        _clearDropRemoteTts();
        _resetThinking();
            final stt = '${payload['text'] ?? payload['content'] ?? ''}'.trim();
        if (stt.isNotEmpty) {
          composerText = '';
          composerHint = '有问题，随便问';
          _appendUser(stt);
        } else {
          composerText = '';
          composerHint = '有问题，随便问';
        }
        _setState(ClientState.busy);
        break;
      case 'agent.start':
        _clearDropRemoteTts();
        _flushThinking(finalFlush: true);
        _setState(ClientState.busy);
        break;
      case 'agent.thinking':
        if (_dropRemoteTts) return;
        final chunk = '${payload['content'] ?? payload['text'] ?? ''}';
        if (chunk.isNotEmpty) {
          _thinkingBuf += chunk;
          _flushThinking(finalFlush: false);
        } else {
          _setState(ClientState.busy);
        }
        break;
      case 'agent.tool_call':
      case 'agent.tool_result':
        if (_dropRemoteTts) return;
        _flushThinking(finalFlush: true);
        final line = _nativeProcessText(type, payload);
        if (line.isNotEmpty) {
          _showProcessLine(line);
        } else {
          _setState(ClientState.busy);
        }
        break;
      case 'agent.message':
        if (_dropRemoteTts) return;
        _flushThinking(finalFlush: true);
        final t =
            (payload['content'] ?? payload['text'] ?? '').toString().trim();
        if (t.isNotEmpty) {
          _appendAssistantChunk(t);
        }
        _setState(ClientState.busy);
        break;
      case 'tts.start':
        if (_dropRemoteTts) return;
        _ttsBuf.clear();
        _ttsPendingText = (payload['text'] as String? ?? '').trim();
        _setState(ClientState.speaking);
        break;
      case 'tts.end':
        if (_dropRemoteTts) {
          _ttsBuf.clear();
          _ttsPendingText = '';
          return;
        }
        if (_ttsBuf.isNotEmpty) {
          player.enqueue(TtsSegment(
            bytes: Uint8List.fromList(_ttsBuf),
            text: _ttsPendingText,
          ));
          _ttsBuf.clear();
          _ttsPendingText = '';
        }
        break;
      case 'agent.done':
        if (_dropRemoteTts || state == ClientState.listening) {
          _ttsBuf.clear();
          _ttsPendingText = '';
          return;
        }
        _flushThinking(finalFlush: true);
        if (!_dropRemoteTts && _ttsBuf.isNotEmpty) {
          player.enqueue(TtsSegment(
            bytes: Uint8List.fromList(_ttsBuf),
            text: _ttsPendingText,
          ));
          _ttsBuf.clear();
          _ttsPendingText = '';
        } else {
          _ttsBuf.clear();
          _ttsPendingText = '';
        }
        _awaitingIdle = true;
        _finishTypewriter();
        _maybeIdle();
        break;
      case 'agent.cancel':
        // Ignore late cancel from a replaced turn after we already barged in.
        if (_dropRemoteTts) {
          player.clear();
          _ttsBuf.clear();
          return;
        }
        _armDropRemoteTts();
        _awaitingIdle = false;
        _stopTypewriter();
        _resetThinking();
        _clearProcessLine();
        _setState(ClientState.idle, status: '已取消');
        break;
      case 'device.pong':
        break;
      default:
        break;
    }
  }

  void _maybeIdle() {
    if (!_awaitingIdle) return;
    _awaitingIdle = false;
    player.commitTurn();
    _assistantTurnText = '';
    activeAssistantId = null;
    _clearProcessLine();
    if (player.isBusy) {
      _setState(ClientState.speaking, status: '播报中');
    } else if (state == ClientState.busy ||
        state == ClientState.speaking ||
        state == ClientState.error) {
      _setState(ClientState.idle, status: '在线');
    } else {
      _notify();
    }
  }

  Future<void> _applyPets(Map<String, dynamic> payload) async {
    await PetCatalog.applyRemoteCatalog(payload, wsUrl: url);
    petDefaultId = payload['default'] as String?;
    petId = PetCatalog.resolveId(petDefaultId ?? petId);
    petsEpoch++;
    _notify();
  }

  Future<void> dispose() async {
    await disconnect(silent: true);
    await recorder.dispose();
    await player.dispose();
    await _changes.close();
  }
}
