import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:image_picker/image_picker.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../pets/pet_catalog.dart';
import '../session/client_state.dart';
import '../session/device_session.dart';
import 'pixel_bot.dart';
import 'status_badge.dart';
import 'theme.dart';

class _PendingImage {
  _PendingImage({required this.bytes, required this.mime, required this.name});
  final Uint8List bytes;
  final String mime;
  final String name;
}

/// ChatGPT-like light chat shell (parity with clients/web).
class HomePage extends StatefulWidget {
  const HomePage({super.key, required this.session});

  final DeviceSession session;

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  late final TextEditingController _url;
  late final TextEditingController _token;
  late final TextEditingController _compose;
  final _chatScroll = ScrollController();
  final _composeFocus = FocusNode();
  final _picker = ImagePicker();
  final List<_PendingImage> _pendingImages = [];
  StreamSubscription? _sub;
  String _lastAppliedComposer = '';
  bool _stickChatBottom = true;
  bool _holdTalking = false;
  bool _holdWillCancel = false;
  int? _holdPointer;
  Offset? _holdStartGlobal;
  Timer? _holdTimer;

  static const _attachLimit = 4;
  static const _maxImageBytes = 4 * 1024 * 1024;
  static const _scrollStickPx = 80.0;
  static const _holdTalkMs = 380;
  static const _holdCancelPx = 56.0;

  DeviceSession get s => widget.session;

  @override
  void initState() {
    super.initState();
    _url = TextEditingController(text: s.url);
    _token = TextEditingController(text: s.token);
    _compose = TextEditingController();
    _chatScroll.addListener(_onChatScroll);
    _sub = s.changes.listen((_) {
      if (!mounted) return;
      _syncComposerFromSession();
      setState(() {});
      unawaited(_savePrefs());
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _scrollChatToBottomIfSticky();
      });
    });
    _loadPrefs().then((_) async {
      if (!mounted) return;
      if (s.url.contains('127.0.0.1') ||
          s.url.contains('192.168.') ||
          s.url.contains('100.')) {
        await s.connect();
      } else {
        await _openSettings();
      }
    });
  }

  void _onChatScroll() {
    if (!_chatScroll.hasClients) return;
    final pos = _chatScroll.position;
    _stickChatBottom =
        pos.maxScrollExtent - pos.pixels <= _scrollStickPx;
  }

  void _scrollChatToBottomIfSticky({bool force = false}) {
    if (!_chatScroll.hasClients) return;
    if (!force && !_stickChatBottom) return;
    _chatScroll.jumpTo(_chatScroll.position.maxScrollExtent);
  }

  void _syncComposerFromSession() {
    final draft = s.composerText;
    if (draft.isNotEmpty && draft != _lastAppliedComposer) {
      _lastAppliedComposer = draft;
      _compose.value = TextEditingValue(
        text: draft,
        selection: TextSelection.collapsed(offset: draft.length),
      );
      return;
    }
    if (draft.isEmpty && _lastAppliedComposer.isNotEmpty) {
      // Session cleared draft (new listen / STT committed to bubble).
      if (_compose.text == _lastAppliedComposer) {
        _compose.clear();
      }
      _lastAppliedComposer = '';
    }
  }

  Future<void> _loadPrefs() async {
    await PetCatalog.ensureLoaded();
    final p = await SharedPreferences.getInstance();
    s.url = p.getString('url') ?? s.url;
    s.token = p.getString('token') ?? '';
    s.loadMessagesJson(p.getString('messages'));
    final legacy = p.getString('reply') ?? '';
    if (s.messages.isEmpty && legacy.isNotEmpty) {
      s.messages.add(ChatMessage(
        id: 'legacy',
        role: ChatRole.assistant,
        text: legacy,
      ));
    }
    _url.text = s.url;
    _token.text = s.token;
    setState(() {});
  }

  Future<void> _savePrefs() async {
    final p = await SharedPreferences.getInstance();
    await p.setString('url', s.url);
    await p.setString('token', s.token);
    await p.setString('messages', s.encodeMessages());
  }

  Future<void> _confirmNewSession() async {
    if (s.sessionId == null) return;
    final ok = await showDialog<bool>(
      context: context,
      barrierColor: const Color(0x59000000),
      builder: (ctx) => _sheetDialog(
        title: '新开会话？',
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(
              '会清空本设备的 Agent 对话记忆与本地气泡。连接不用重连。',
              style: TextStyle(color: WebUiTheme.muted, fontSize: 13, height: 1.5),
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  child: _secondaryBtn('取消', () => Navigator.pop(ctx, false)),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: _primaryBtn('确定', () => Navigator.pop(ctx, true)),
                ),
              ],
            ),
          ],
        ),
      ),
    );
    if (ok == true) {
      await s.resetConversation();
      await _savePrefs();
    }
  }

  Future<void> _openSettings() async {
    _url.text = s.url;
    _token.text = s.token;
    final fieldBorder = OutlineInputBorder(
      borderRadius: BorderRadius.circular(WebUiTheme.radiusSm),
      borderSide: const BorderSide(color: WebUiTheme.line),
    );
    final online = s.sessionId != null;
    await showDialog<void>(
      context: context,
      barrierColor: const Color(0x59000000),
      builder: (ctx) => _sheetDialog(
        title: '连接',
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _label('Runtime WS'),
            TextField(
              controller: _url,
              style: const TextStyle(color: WebUiTheme.text, fontSize: 14),
              decoration: InputDecoration(
                isDense: true,
                hintText: 'ws://192.168.x.x:8765',
                hintStyle: const TextStyle(color: WebUiTheme.muted),
                border: fieldBorder,
                enabledBorder: fieldBorder,
                focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(WebUiTheme.radiusSm),
                  borderSide: const BorderSide(color: WebUiTheme.accent),
                ),
              ),
            ),
            const SizedBox(height: 10),
            _label('Token（可选）'),
            TextField(
              controller: _token,
              obscureText: true,
              style: const TextStyle(color: WebUiTheme.text, fontSize: 14),
              decoration: InputDecoration(
                isDense: true,
                border: fieldBorder,
                enabledBorder: fieldBorder,
                focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(WebUiTheme.radiusSm),
                  borderSide: const BorderSide(color: WebUiTheme.accent),
                ),
              ),
            ),
            const SizedBox(height: 14),
            Row(
              children: [
                Expanded(
                  child: _primaryBtn('保存并连接', () async {
                    s.url = _url.text.trim();
                    s.token = _token.text;
                    await _savePrefs();
                    if (ctx.mounted) Navigator.pop(ctx);
                    await s.connect();
                  }),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: _secondaryBtn('关闭', () => Navigator.pop(ctx)),
                ),
              ],
            ),
            const SizedBox(height: 14),
            const Divider(height: 1, thickness: 1, color: WebUiTheme.line),
            const SizedBox(height: 12),
            TextButton(
              onPressed: online
                  ? () async {
                      Navigator.pop(ctx);
                      await _confirmNewSession();
                    }
                  : null,
              style: TextButton.styleFrom(
                backgroundColor: WebUiTheme.panel,
                foregroundColor: WebUiTheme.text,
                disabledForegroundColor:
                    WebUiTheme.text.withValues(alpha: 0.35),
                disabledBackgroundColor: WebUiTheme.bgSoft.withValues(alpha: 0.5),
                side: const BorderSide(color: WebUiTheme.line),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(WebUiTheme.radiusSm),
                ),
                padding: const EdgeInsets.symmetric(vertical: 12),
              ),
              child: const Text(
                '新开会话',
                style: TextStyle(fontWeight: FontWeight.w600),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _sheetDialog({required String title, required Widget child}) {
    return Dialog(
      backgroundColor: WebUiTheme.panel,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: const BorderSide(color: WebUiTheme.line),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(18, 16, 18, 14),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(title,
                style: const TextStyle(
                    color: WebUiTheme.text,
                    fontSize: 17,
                    fontWeight: FontWeight.w600)),
            const SizedBox(height: 12),
            child,
          ],
        ),
      ),
    );
  }

  Widget _primaryBtn(String label, VoidCallback onPressed) => TextButton(
        style: TextButton.styleFrom(
          backgroundColor: WebUiTheme.accent,
          foregroundColor: Colors.white,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(WebUiTheme.radiusSm),
          ),
          padding: const EdgeInsets.symmetric(vertical: 12),
        ),
        onPressed: onPressed,
        child: Text(label),
      );

  Widget _secondaryBtn(String label, VoidCallback onPressed) => TextButton(
        style: TextButton.styleFrom(
          backgroundColor: WebUiTheme.bgSoft,
          foregroundColor: WebUiTheme.text,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(WebUiTheme.radiusSm),
          ),
          padding: const EdgeInsets.symmetric(vertical: 12),
        ),
        onPressed: onPressed,
        child: Text(label),
      );

  Widget _label(String t) => Padding(
        padding: const EdgeInsets.only(bottom: 4),
        child: Text(t,
            style: const TextStyle(color: WebUiTheme.muted, fontSize: 12)),
      );

  Future<void> _onTalk() async {
    final mic = await Permission.microphone.request();
    if (!mic.isGranted) {
      s.lastError = '需要麦克风权限';
      setState(() {});
      return;
    }
    await s.toggleTalk();
    await _savePrefs();
  }

  Future<void> _pickImages() async {
    if (!s.canComposeText) return;
    try {
      final room = _attachLimit - _pendingImages.length;
      if (room <= 0) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('最多附 $_attachLimit 张图片'),
            duration: const Duration(seconds: 2),
          ),
        );
        return;
      }
      final files = await _picker.pickMultiImage(limit: room);
      if (files.isEmpty) return;
      for (final f in files) {
        if (_pendingImages.length >= _attachLimit) break;
        final bytes = await f.readAsBytes();
        if (bytes.length > _maxImageBytes) {
          if (!mounted) return;
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('${f.name} 过大（上限 4MB）'),
              duration: const Duration(seconds: 2),
            ),
          );
          continue;
        }
        final mime = _mimeFromName(f.name, f.mimeType);
        if (!mime.startsWith('image/')) continue;
        _pendingImages.add(_PendingImage(
          bytes: bytes,
          mime: mime,
          name: f.name,
        ));
      }
      if (mounted) setState(() {});
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('选图失败：$e'),
          duration: const Duration(seconds: 2),
        ),
      );
    }
  }

  String _mimeFromName(String name, String? hinted) {
    final h = (hinted ?? '').trim().toLowerCase();
    if (h.startsWith('image/')) return h;
    final lower = name.toLowerCase();
    if (lower.endsWith('.jpg') || lower.endsWith('.jpeg')) return 'image/jpeg';
    if (lower.endsWith('.gif')) return 'image/gif';
    if (lower.endsWith('.webp')) return 'image/webp';
    if (lower.endsWith('.bmp')) return 'image/bmp';
    return 'image/png';
  }

  Future<void> _submitCompose() async {
    final text = _compose.text.trim();
    if ((text.isEmpty && _pendingImages.isEmpty) || !s.canComposeText) return;
    final pending = List<_PendingImage>.from(_pendingImages);
    _pendingImages.clear();
    _stickChatBottom = true;
    _compose.clear();
    setState(() {});
    final images = pending
        .map((p) => {
              'mime': p.mime,
              'data': base64Encode(p.bytes),
            })
        .toList();
    final previews = pending.map((p) => p.bytes).toList();
    await s.sendText(text, images: images, previewBytes: previews);
    await _savePrefs();
  }

  Future<void> _onMicPressed() async {
    if (s.state == ClientState.offline) {
      await s.connect();
      return;
    }
    if (s.state == ClientState.error && s.sessionId == null) {
      await s.connect();
      return;
    }
    if (!s.canToggleTalk) return;
    await _onTalk();
  }

  void _clearHoldTimer() {
    _holdTimer?.cancel();
    _holdTimer = null;
  }

  Future<void> _beginHoldTalk() async {
    if (_holdTalking || !mounted) return;
    if (s.sessionId == null) return;
    _holdTalking = true;
    _holdWillCancel = false;
    _composeFocus.unfocus();
    setState(() {});
    try {
      await s.beginHoldTalk();
    } catch (_) {
      _holdTalking = false;
      if (mounted) setState(() {});
    }
  }

  Future<void> _finishHoldTalk({required bool cancel}) async {
    if (!_holdTalking) return;
    _holdTalking = false;
    _holdWillCancel = false;
    _holdPointer = null;
    _holdStartGlobal = null;
    if (mounted) setState(() {});
    await s.endHoldTalk(cancel: cancel);
  }

  void _onComposePointerDown(PointerDownEvent e) {
    if (!s.canComposeText && s.sessionId == null) return;
    if (s.sessionId == null) return;
    if (_holdTalking || s.state == ClientState.listening) return;
    // Allow text selection when field already has content.
    if (_compose.text.trim().isNotEmpty) return;
    _clearHoldTimer();
    _holdPointer = e.pointer;
    _holdStartGlobal = e.position;
    _holdWillCancel = false;
    _holdTimer = Timer(const Duration(milliseconds: _holdTalkMs), () {
      _holdTimer = null;
      unawaited(_beginHoldTalk());
    });
  }

  void _onComposePointerMove(PointerMoveEvent e) {
    if (_holdPointer != e.pointer) return;
    if (!_holdTalking || _holdStartGlobal == null) return;
    final cancel = _holdStartGlobal!.dy - e.position.dy >= _holdCancelPx;
    if (cancel != _holdWillCancel) {
      _holdWillCancel = cancel;
      s.setHoldTalkHint(willCancel: cancel);
      setState(() {});
    }
  }

  void _onComposePointerUp(PointerUpEvent e) {
    if (_holdPointer != null && e.pointer != _holdPointer) return;
    _clearHoldTimer();
    if (_holdTalking) {
      unawaited(_finishHoldTalk(cancel: _holdWillCancel));
    }
    _holdPointer = null;
    _holdStartGlobal = null;
  }

  void _onComposePointerCancel(PointerCancelEvent e) {
    if (_holdPointer != null && e.pointer != _holdPointer) return;
    _clearHoldTimer();
    if (_holdTalking) {
      unawaited(_finishHoldTalk(cancel: true));
    }
    _holdPointer = null;
    _holdStartGlobal = null;
  }

  @override
  void dispose() {
    _clearHoldTimer();
    _sub?.cancel();
    _url.dispose();
    _token.dispose();
    _compose.dispose();
    _composeFocus.dispose();
    _chatScroll.removeListener(_onChatScroll);
    _chatScroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final screenW = MediaQuery.sizeOf(context).width;
    final online = s.sessionId != null;
    final canType = s.canComposeText;
    final listening = s.state == ClientState.listening;

    return Scaffold(
      backgroundColor: WebUiTheme.bg0,
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 720),
            child: Column(
              children: [
                Expanded(
                  child: Stack(
                    clipBehavior: Clip.none,
                    children: [
                      _buildTranscript(screenW),
                      Positioned(
                        left: 0,
                        right: 0,
                        bottom: 0,
                        child: _buildComposer(
                          online: online,
                          canType: canType,
                          listening: listening,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildTranscript(double screenW) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 10),
      child: Column(
        children: [
          Expanded(
            child: ListView.builder(
              controller: _chatScroll,
              padding: EdgeInsets.only(
                bottom: _pendingImages.isNotEmpty ? 220 : 160,
                top: 8,
              ),
              itemCount: s.messages.length + (s.processLine.isNotEmpty ? 1 : 0),
              itemBuilder: (ctx, i) {
                if (i >= s.messages.length) {
                  return Padding(
                    padding: const EdgeInsets.only(bottom: 14, left: 4),
                    child: Align(
                      alignment: Alignment.centerLeft,
                      child: Text(
                        s.processLine,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: WebUiTheme.muted,
                          fontSize: 13,
                          height: 1.45,
                        ),
                      ),
                    ),
                  );
                }
                final m = s.messages[i];
                final isUser = m.role == ChatRole.user;
                final isLastAssistant = !isUser &&
                    s.messages.lastIndexWhere((x) => x.role == ChatRole.assistant) ==
                        i;
                return Padding(
                  padding: const EdgeInsets.only(bottom: 14),
                  child: Column(
                    crossAxisAlignment: isUser
                        ? CrossAxisAlignment.end
                        : CrossAxisAlignment.start,
                    children: [
                      Align(
                        alignment: isUser
                            ? Alignment.centerRight
                            : Alignment.centerLeft,
                        child: Container(
                          constraints: BoxConstraints(
                            maxWidth:
                                isUser ? screenW * 0.78 : screenW * 0.95,
                          ),
                          padding: isUser
                              ? const EdgeInsets.symmetric(
                                  horizontal: 14, vertical: 10)
                              : const EdgeInsets.symmetric(
                                  horizontal: 4, vertical: 2),
                          decoration: isUser
                              ? BoxDecoration(
                                  color: WebUiTheme.bubbleUser,
                                  borderRadius: BorderRadius.circular(
                                      WebUiTheme.radius),
                                )
                              : null,
                          child: isUser
                              ? Column(
                                  crossAxisAlignment: CrossAxisAlignment.end,
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    if (m.imageBytes.isNotEmpty)
                                      Padding(
                                        padding: EdgeInsets.only(
                                          bottom: m.text.trim().isEmpty ? 0 : 8,
                                        ),
                                        child: Wrap(
                                          spacing: 6,
                                          runSpacing: 6,
                                          alignment: WrapAlignment.end,
                                          children: [
                                            for (final bytes in m.imageBytes)
                                              ClipRRect(
                                                borderRadius:
                                                    BorderRadius.circular(10),
                                                child: Image.memory(
                                                  bytes,
                                                  width: 120,
                                                  height: 120,
                                                  fit: BoxFit.cover,
                                                ),
                                              ),
                                          ],
                                        ),
                                      ),
                                    if (m.text.trim().isNotEmpty)
                                      Text(m.text, style: WebUiTheme.bubbleText),
                                  ],
                                )
                              : MarkdownBody(
                                  data: m.text,
                                  selectable: true,
                                  styleSheet: MarkdownStyleSheet.fromTheme(
                                    Theme.of(ctx),
                                  ).copyWith(
                                    p: WebUiTheme.bubbleText,
                                    a: WebUiTheme.bubbleText.copyWith(
                                      color: WebUiTheme.accent,
                                      decoration: TextDecoration.underline,
                                    ),
                                    code: WebUiTheme.bubbleText.copyWith(
                                      fontFamily: 'monospace',
                                      fontSize: 13.5,
                                      backgroundColor: WebUiTheme.bgSoft,
                                    ),
                                    codeblockDecoration: BoxDecoration(
                                      color: WebUiTheme.bgSoft,
                                      borderRadius: BorderRadius.circular(10),
                                      border: Border.all(color: WebUiTheme.line),
                                    ),
                                    blockquote: WebUiTheme.bubbleText.copyWith(
                                      color: WebUiTheme.muted,
                                    ),
                                  ),
                                ),
                        ),
                      ),
                      if (!isUser && m.text.trim().isNotEmpty)
                        Padding(
                          padding: const EdgeInsets.only(top: 4),
                          child: Row(
                            children: [
                              IconButton(
                                visualDensity: VisualDensity.compact,
                                iconSize: 18,
                                color: WebUiTheme.muted,
                                onPressed: () => copyText(m.text),
                                icon: const Icon(Icons.copy_outlined),
                                tooltip: '复制',
                              ),
                              if (isLastAssistant && s.canShowSpeakAction)
                                IconButton(
                                  visualDensity: VisualDensity.compact,
                                  iconSize: 18,
                                  color: s.isSpeakingTts
                                      ? const Color(0xFFEC4899)
                                      : WebUiTheme.muted,
                                  onPressed: () => s.toggleSpeakOrReplay(),
                                  icon: Icon(
                                    s.isSpeakingTts
                                        ? Icons.volume_up_rounded
                                        : Icons.volume_up_outlined,
                                  ),
                                  tooltip: s.isSpeakingTts ? '停止播报' : '播报',
                                ),
                            ],
                          ),
                        ),
                    ],
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildComposer({
    required bool online,
    required bool canType,
    required bool listening,
  }) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(10, 0, 10, 16),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              StatusBadge(state: s.state),
              GestureDetector(
                behavior: HitTestBehavior.translucent,
                onTap: online ? _onMicPressed : null,
                onLongPress: _openSettings,
                child: AnimatedScale(
                  scale: listening ? 1.04 : 1.0,
                  duration: const Duration(milliseconds: 180),
                  child: SizedBox(
                    width: 64,
                    height: 70,
                    child: PixelBot(
                      key: ValueKey('composer-${s.petId}-${s.petsEpoch}'),
                      mood: s.state,
                      petId: s.petId,
                    ),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          // Only the input shell is opaque — pet above stays clear over bubbles.
          Material(
            color: _holdTalking
                ? (_holdWillCancel
                    ? const Color(0xFFFEF2F2)
                    : const Color(0xFFEFF6FF))
                : WebUiTheme.bg0,
            elevation: 0,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(
                _pendingImages.isNotEmpty ? 22 : 999,
              ),
              side: BorderSide(
                color: _holdTalking
                    ? (_holdWillCancel
                        ? const Color(0xFFEF4444)
                        : WebUiTheme.accent)
                    : WebUiTheme.line,
              ),
            ),
            clipBehavior: Clip.antiAlias,
            child: Padding(
              padding: EdgeInsets.fromLTRB(
                6,
                _pendingImages.isNotEmpty ? 10 : 6,
                6,
                6,
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (_pendingImages.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.fromLTRB(4, 0, 4, 8),
                      child: SizedBox(
                        height: 56,
                        child: ListView.separated(
                          scrollDirection: Axis.horizontal,
                          itemCount: _pendingImages.length,
                          separatorBuilder: (_, __) => const SizedBox(width: 8),
                          itemBuilder: (ctx, i) {
                            final item = _pendingImages[i];
                            return Stack(
                              clipBehavior: Clip.none,
                              children: [
                                ClipRRect(
                                  borderRadius: BorderRadius.circular(12),
                                  child: Image.memory(
                                    item.bytes,
                                    width: 56,
                                    height: 56,
                                    fit: BoxFit.cover,
                                  ),
                                ),
                                Positioned(
                                  top: 2,
                                  right: 2,
                                  child: Material(
                                    color: const Color(0xB30F172A),
                                    shape: const CircleBorder(),
                                    child: InkWell(
                                      customBorder: const CircleBorder(),
                                      onTap: () => setState(() {
                                        _pendingImages.removeAt(i);
                                      }),
                                      child: const Padding(
                                        padding: EdgeInsets.all(2),
                                        child: Icon(
                                          Icons.close,
                                          size: 14,
                                          color: Colors.white,
                                        ),
                                      ),
                                    ),
                                  ),
                                ),
                              ],
                            );
                          },
                        ),
                      ),
                    ),
                  Row(
                    children: [
                      IconButton(
                        onPressed: canType ? _pickImages : null,
                        color: WebUiTheme.muted,
                        icon: const Icon(Icons.add_rounded),
                        tooltip: '添加图片',
                      ),
                      Expanded(
                        child: Listener(
                          onPointerDown: _onComposePointerDown,
                          onPointerMove: _onComposePointerMove,
                          onPointerUp: _onComposePointerUp,
                          onPointerCancel: _onComposePointerCancel,
                          child: TextField(
                            controller: _compose,
                            focusNode: _composeFocus,
                            enabled: canType && !_holdTalking,
                            minLines: 1,
                            maxLines: 4,
                            readOnly: _holdTalking,
                            style: TextStyle(
                              color: _holdTalking
                                  ? (_holdWillCancel
                                      ? const Color(0xFFEF4444)
                                      : WebUiTheme.accent)
                                  : WebUiTheme.text,
                              fontSize: 15,
                              fontWeight: _holdTalking
                                  ? FontWeight.w600
                                  : FontWeight.w400,
                            ),
                            textAlign: _holdTalking
                                ? TextAlign.center
                                : TextAlign.start,
                            textInputAction: TextInputAction.send,
                            onSubmitted: (_) => _submitCompose(),
                            decoration: InputDecoration(
                              isDense: true,
                              border: InputBorder.none,
                              hintText: s.composerHint,
                              hintStyle: TextStyle(
                                color: _holdTalking
                                    ? (_holdWillCancel
                                        ? const Color(0xFFEF4444)
                                        : WebUiTheme.accent)
                                    : WebUiTheme.muted,
                                fontWeight: _holdTalking
                                    ? FontWeight.w600
                                    : FontWeight.w400,
                              ),
                            ),
                          ),
                        ),
                      ),
                      IconButton(
                        onPressed: online ? _onMicPressed : null,
                        color: listening ? WebUiTheme.accent : WebUiTheme.muted,
                        icon: Icon(
                          listening
                              ? Icons.stop_rounded
                              : Icons.mic_none_rounded,
                        ),
                        tooltip: '语音',
                      ),
                      Material(
                        color: canType ? WebUiTheme.accent : WebUiTheme.bgSoft,
                        shape: const CircleBorder(),
                        child: InkWell(
                          customBorder: const CircleBorder(),
                          onTap: canType ? _submitCompose : null,
                          child: SizedBox(
                            width: 36,
                            height: 36,
                            child: Icon(
                              Icons.arrow_upward_rounded,
                              size: 20,
                              color: canType ? Colors.white : WebUiTheme.muted,
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
