import 'dart:async';
import 'dart:typed_data';

import 'package:web_socket_channel/io.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../audio/player.dart';
import '../audio/recorder.dart';
import '../protocol/messages.dart' as proto;
import '../ui/pet_catalog.dart';
import 'client_state.dart';

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
  /// User/app wants a live session (auto-reconnect until disconnect/dispose).
  bool _wantConnected = false;
  bool _connecting = false;
  bool _intentionalClose = false;

  final WavRecorder recorder = WavRecorder();
  final TtsPlayer player = TtsPlayer();

  ClientState state = ClientState.offline;
  String? sessionId;
  String? lastError;
  String statusLine = '';
  String replyText = '';
  bool captionMode = false;

  String url = 'ws://192.168.1.1:8765';
  String token = '';
  /// Filled from Runtime session.accept / catalog push — not client config.
  String ttsId = '';
  String petId = '';
  /// From Runtime `tts.list.result` — empty until connected.
  List<Map<String, dynamic>> ttsProviders = const [];
  String? ttsDefaultId;
  String? petDefaultId;
  /// Bumps when pets catalog is refreshed from Runtime.
  int petsEpoch = 0;

  final List<int> _ttsBuf = [];
  String _ttsPendingText = '';
  bool _awaitingIdle = false;
  String _thinkingBuf = '';
  DateTime? _lastThinkingFlush;
  bool _captionLive = false;
  static const _thinkingMin = Duration(milliseconds: 400);
  static const _processMaxLen = 72;

  final _changes = StreamController<void>.broadcast();
  Stream<void> get changes => _changes.stream;

  bool get canToggleTalk =>
      sessionId != null &&
      (state == ClientState.idle || state == ClientState.listening);

  bool get canReplay =>
      sessionId != null &&
      state == ClientState.idle &&
      !player.isBusy &&
      player.lastTurn.isNotEmpty &&
      replyText.trim().isNotEmpty;

  void _notify() {
    if (!_changes.isClosed) _changes.add(null);
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

  /// One-line native process text from the agent event. No invented labels.
  void _showProcessLine(String line) {
    final s = _clipProcess(line);
    if (s.isEmpty) return;
    if (!_captionLive) {
      replyText = s;
    }
    _setState(ClientState.busy, status: s);
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
      player.onCaption = (t) {
        final line = t.trim();
        if (line.isEmpty) return;
        if (captionMode) {
          if (!_captionLive) {
            _captionLive = true;
            replyText = line;
          } else {
            replyText = '$replyText\n$line';
          }
        }
        _notify();
      };
      player.onBecameIdle = _maybeIdle;
      player.onQueueChanged = _notify;
    } catch (e) {
      lastError = e.toString();
      _setState(ClientState.error, status: lastError);
      _scheduleReconnect();
    } finally {
      _connecting = false;
    }
  }

  /// Call when app returns to foreground — recover from OS-killed sockets.
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
    if (state != ClientState.idle || sessionId == null) return;
    await _startListen();
  }

  Future<void> replayLast() => player.replayLast();

  Future<void> cancelTurn() async {
    if (sessionId == null || _ws == null) return;
    _ws!.sink.add(proto.sessionCancel(sessionId!));
    player.clear();
    _ttsBuf.clear();
    _awaitingIdle = false;
    captionMode = false;
    await recorder.cancel();
    _setState(ClientState.idle, status: '已取消');
  }

  Future<void> _startListen() async {
    try {
      await recorder.start();
      _ttsBuf.clear();
      player.clear();
      player.beginTurn();
      _awaitingIdle = false;
      captionMode = false;
      replyText = '';
      _setState(ClientState.listening, status: '正在录音…');
    } catch (e) {
      lastError = e.toString();
      _setState(ClientState.error, status: lastError);
    }
  }

  Future<void> _stopAndSend() async {
    final bytes = await recorder.stop();
    if (bytes == null || bytes.isEmpty || _ws == null || sessionId == null) {
      _setState(ClientState.idle, status: '空录音');
      return;
    }
    _setState(ClientState.busy, status: '识别中…');
    _ws!.sink.add(proto.audioStart(sessionId!));
    const chunk = 4096;
    for (var i = 0; i < bytes.length; i += chunk) {
      final end = (i + chunk < bytes.length) ? i + chunk : bytes.length;
      _ws!.sink.add(bytes.sublist(i, end));
    }
    _ws!.sink.add(proto.audioEnd(sessionId!));
  }

  void _onData(dynamic data) {
    if (data is List<int>) {
      _ttsBuf.addAll(data);
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
        _setState(ClientState.idle, status: '点按角色通话');
        // Catalogs are pushed by Runtime after accept; keep optional pull for older hosts.
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
        // Catalog apply is async — HomePage listens via petsEpoch.
        _applyPets(payload);
        break;
      case 'error':
        lastError = '${payload['detail'] ?? payload['message'] ?? 'error'}';
        _setState(ClientState.error, status: lastError);
        break;
      case 'stt.final':
        _resetThinking();
        _captionLive = false;
        _setState(ClientState.busy);
        break;
      case 'agent.start':
        _flushThinking(finalFlush: true);
        _setState(ClientState.busy);
        break;
      case 'agent.thinking':
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
        _flushThinking(finalFlush: true);
        final line = _nativeProcessText(type, payload);
        if (line.isNotEmpty) {
          _showProcessLine(line);
        } else {
          _setState(ClientState.busy);
        }
        break;
      case 'agent.message':
        _flushThinking(finalFlush: true);
        final speak = payload['speak'] != false;
        final t = (payload['content'] ?? payload['text'] ?? '').toString().trim();
        if (t.isNotEmpty) {
          _showProcessLine(t);
        }
        if (speak) {
          captionMode = true;
        }
        break;
      case 'tts.start':
        _ttsBuf.clear();
        _ttsPendingText = (payload['text'] as String? ?? '').trim();
        _setState(
          ClientState.speaking,
          status: _ttsPendingText.isEmpty ? null : _clipProcess(_ttsPendingText),
        );
        break;
      case 'tts.end':
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
        _flushThinking(finalFlush: true);
        _awaitingIdle = true;
        _maybeIdle();
        break;
      case 'agent.cancel':
        player.clear();
        _ttsBuf.clear();
        _awaitingIdle = false;
        captionMode = false;
        _captionLive = false;
        _resetThinking();
        _setState(ClientState.idle, status: '已取消');
        break;
      case 'device.pong':
        break;
      default:
        break;
    }
  }

  void _maybeIdle() {
    if (_awaitingIdle && !player.isBusy && _ttsBuf.isEmpty) {
      _awaitingIdle = false;
      player.commitTurn();
      captionMode = false;
      _captionLive = false;
      if (state == ClientState.busy || state == ClientState.speaking) {
        _setState(ClientState.idle, status: '点按角色通话');
      }
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
