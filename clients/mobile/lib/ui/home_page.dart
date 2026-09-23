import 'dart:async';

import 'package:flutter/material.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../session/client_state.dart';
import '../session/device_session.dart';
import 'pixel_bot.dart';
import 'pet_catalog.dart';
import 'status_badge.dart';
import 'theme.dart';

/// Layout aligned with clients/web: centered pet + multi-line reply;
/// tap talk / long-press settings; long-press reply for hidden text input.
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
  final _replyScroll = ScrollController();
  final _composeFocus = FocusNode();
  StreamSubscription? _sub;
  bool _holdOpenedSettings = false;
  Timer? _holdTimer;
  bool _composerOpen = false;

  DeviceSession get s => widget.session;

  @override
  void initState() {
    super.initState();
    _url = TextEditingController(text: s.url);
    _token = TextEditingController(text: s.token);
    _compose = TextEditingController();
    _sub = s.changes.listen((_) {
      if (!mounted) return;
      setState(() {});
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (_replyScroll.hasClients) {
          _replyScroll.jumpTo(_replyScroll.position.maxScrollExtent);
        }
      });
    });
    _loadPrefs().then((_) async {
      if (!mounted) return;
      if (s.url.contains('127.0.0.1') || s.url.contains('192.168.') || s.url.contains('100.')) {
        await s.connect();
      } else {
        await _openSettings();
      }
    });
  }

  Future<void> _loadPrefs() async {
    await PetCatalog.ensureLoaded();
    final p = await SharedPreferences.getInstance();
    s.url = p.getString('url') ?? s.url;
    s.token = p.getString('token') ?? '';
    final last = p.getString('reply') ?? '';
    if (last.isNotEmpty && s.replyText.isEmpty) s.replyText = last;
    _url.text = s.url;
    _token.text = s.token;
    setState(() {});
  }

  Future<void> _savePrefs() async {
    final p = await SharedPreferences.getInstance();
    await p.setString('url', s.url);
    await p.setString('token', s.token);
    await p.setString('reply', s.replyText);
  }

  Future<void> _openSettings() async {
    _url.text = s.url;
    _token.text = s.token;
    await showDialog<void>(
      context: context,
      barrierColor: Colors.black54,
      builder: (ctx) {
        var confirmingReset = false;
        return StatefulBuilder(
          builder: (ctx, setLocal) {
            final square = RoundedRectangleBorder(
              borderRadius: BorderRadius.zero,
              side: const BorderSide(color: WebUiTheme.line, width: 2),
            );
            Widget outlinedBtn({
              required String label,
              required VoidCallback? onPressed,
              Color? bg,
              Color? fg,
            }) {
              return TextButton(
                style: TextButton.styleFrom(
                  backgroundColor: bg ?? const Color(0xFF2A3340),
                  foregroundColor: fg ?? WebUiTheme.text,
                  shape: const RoundedRectangleBorder(borderRadius: BorderRadius.zero),
                  padding: const EdgeInsets.symmetric(vertical: 12),
                ),
                onPressed: onPressed,
                child: Text(label),
              );
            }

            if (confirmingReset) {
              return Dialog(
                backgroundColor: WebUiTheme.panel,
                shape: square,
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(16, 14, 16, 12),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const Text('新开会话？', style: TextStyle(color: WebUiTheme.text, fontSize: 16)),
                      const SizedBox(height: 8),
                      const Text(
                        '会清空本机与这台设备相关的 Agent 对话记忆。连接不用重连。',
                        style: TextStyle(color: WebUiTheme.muted, fontSize: 13, height: 1.4),
                      ),
                      const SizedBox(height: 14),
                      Row(
                        children: [
                          Expanded(
                            child: outlinedBtn(
                              label: '取消',
                              onPressed: () => setLocal(() => confirmingReset = false),
                            ),
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: outlinedBtn(
                              label: '确定',
                              bg: WebUiTheme.accent,
                              fg: const Color(0xFF04140C),
                              onPressed: () async {
                                if (ctx.mounted) Navigator.pop(ctx);
                                await s.resetConversation();
                                await _savePrefs();
                              },
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              );
            }

            return Dialog(
              backgroundColor: WebUiTheme.panel,
              shape: square,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 14, 16, 12),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Text('连接', style: TextStyle(color: WebUiTheme.text, fontSize: 16)),
                    const SizedBox(height: 10),
                    _label('Runtime WS'),
                    TextField(
                      controller: _url,
                      style: const TextStyle(color: WebUiTheme.text, fontSize: 13),
                      decoration: const InputDecoration(
                        isDense: true,
                        hintText: 'ws://192.168.x.x:8765',
                        hintStyle: TextStyle(color: WebUiTheme.muted),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.zero,
                          borderSide: BorderSide(color: WebUiTheme.line),
                        ),
                        enabledBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.zero,
                          borderSide: BorderSide(color: WebUiTheme.line),
                        ),
                      ),
                    ),
                    const SizedBox(height: 8),
                    _label('Token（可选）'),
                    TextField(
                      controller: _token,
                      obscureText: true,
                      style: const TextStyle(color: WebUiTheme.text, fontSize: 13),
                      decoration: const InputDecoration(
                        isDense: true,
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.zero,
                          borderSide: BorderSide(color: WebUiTheme.line),
                        ),
                        enabledBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.zero,
                          borderSide: BorderSide(color: WebUiTheme.line),
                        ),
                      ),
                    ),
                    const SizedBox(height: 14),
                    OutlinedButton(
                      style: OutlinedButton.styleFrom(
                        foregroundColor: WebUiTheme.text,
                        side: const BorderSide(color: WebUiTheme.line, width: 2),
                        shape: const RoundedRectangleBorder(borderRadius: BorderRadius.zero),
                        padding: const EdgeInsets.symmetric(vertical: 12),
                      ),
                      onPressed: s.sessionId == null
                          ? null
                          : () => setLocal(() => confirmingReset = true),
                      child: const Text('新开会话'),
                    ),
                    const SizedBox(height: 10),
                    Row(
                      children: [
                        Expanded(
                          child: outlinedBtn(
                            label: '保存并连接',
                            bg: WebUiTheme.accent,
                            fg: const Color(0xFF04140C),
                            onPressed: () async {
                              s.url = _url.text.trim();
                              s.token = _token.text;
                              await _savePrefs();
                              if (ctx.mounted) Navigator.pop(ctx);
                              await s.connect();
                            },
                          ),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: outlinedBtn(
                            label: '关闭',
                            onPressed: () => Navigator.pop(ctx),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            );
          },
        );
      },
    );
  }

  Widget _label(String t) => Padding(
        padding: const EdgeInsets.only(bottom: 4),
        child: Text(t, style: const TextStyle(color: WebUiTheme.muted, fontSize: 11)),
      );

  Future<void> _onTalk() async {
    if (_composerOpen) return;
    final mic = await Permission.microphone.request();
    if (!mic.isGranted) {
      s.lastError = '需要麦克风权限';
      setState(() {});
      return;
    }
    await s.toggleTalk();
    await _savePrefs();
  }

  Future<void> _openComposer() async {
    if (!s.canComposeText || _composerOpen) return;
    _compose.text = s.composePrefill;
    _compose.selection = TextSelection.collapsed(offset: _compose.text.length);
    setState(() => _composerOpen = true);
    await showModalBottomSheet<void>(
      context: context,
      backgroundColor: WebUiTheme.panel,
      barrierColor: Colors.black54,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.zero,
        side: BorderSide(color: WebUiTheme.line, width: 2),
      ),
      builder: (ctx) {
        final inset = MediaQuery.viewInsetsOf(ctx).bottom;
        return Padding(
          padding: EdgeInsets.fromLTRB(12, 10, 12, 10 + inset),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Expanded(
                child: TextField(
                  controller: _compose,
                  focusNode: _composeFocus,
                  autofocus: true,
                  minLines: 1,
                  maxLines: 4,
                  style: const TextStyle(color: WebUiTheme.text, fontSize: 14),
                  textInputAction: TextInputAction.send,
                  onSubmitted: (_) => _submitCompose(ctx),
                  decoration: const InputDecoration(
                    isDense: true,
                    hintText: '说点什么…',
                    hintStyle: TextStyle(color: WebUiTheme.muted),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.zero,
                      borderSide: BorderSide(color: WebUiTheme.line),
                    ),
                    enabledBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.zero,
                      borderSide: BorderSide(color: WebUiTheme.line),
                    ),
                    focusedBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.zero,
                      borderSide: BorderSide(color: WebUiTheme.accent),
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              TextButton(
                style: TextButton.styleFrom(
                  backgroundColor: WebUiTheme.accent,
                  foregroundColor: const Color(0xFF042016),
                  shape: const RoundedRectangleBorder(borderRadius: BorderRadius.zero),
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
                ),
                onPressed: () => _submitCompose(ctx),
                child: const Text('发送'),
              ),
            ],
          ),
        );
      },
    );
    if (mounted) setState(() => _composerOpen = false);
  }

  Future<void> _submitCompose(BuildContext sheetCtx) async {
    final text = _compose.text.trim();
    if (text.isEmpty) return;
    Navigator.pop(sheetCtx);
    await s.sendText(text);
    await _savePrefs();
  }

  void _onBotPointerDown() {
    _holdOpenedSettings = false;
    _holdTimer?.cancel();
    _holdTimer = Timer(const Duration(milliseconds: 550), () {
      _holdOpenedSettings = true;
      _openSettings();
    });
  }

  void _onBotPointerUp() {
    _holdTimer?.cancel();
    _holdTimer = null;
  }

  Future<void> _onBotTap() async {
    _holdTimer?.cancel();
    if (_composerOpen) return;
    if (_holdOpenedSettings) {
      _holdOpenedSettings = false;
      return;
    }
    if (s.state == ClientState.error || s.state == ClientState.offline) {
      await s.connect();
      return;
    }
    // Cancel does not need the microphone.
    if (s.state == ClientState.busy || s.state == ClientState.speaking) {
      await s.toggleTalk();
      return;
    }
    if (!s.canToggleTalk) return;
    await _onTalk();
  }

  @override
  void dispose() {
    _holdTimer?.cancel();
    _sub?.cancel();
    _url.dispose();
    _token.dispose();
    _compose.dispose();
    _composeFocus.dispose();
    _replyScroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final reply = s.replyText.trim().isEmpty ? '' : s.replyText;
    final screenH = MediaQuery.sizeOf(context).height;
    final screenW = MediaQuery.sizeOf(context).width;
    final replyH = WebUiTheme.replyBoxHeightFor(screenH);
    // Match clients/web `.sprite-wrap`: min(72vw, 280) × aspect, max-height ~52vh.
    final botW = (screenW * 0.72).clamp(0.0, 280.0);

    return Scaffold(
      backgroundColor: WebUiTheme.bg0,
      body: DecoratedBox(
        decoration: const BoxDecoration(
          color: WebUiTheme.bg0,
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [Color(0xEB121820), Color(0xFA0A0E12)],
          ),
        ),
        child: SafeArea(
          // Match clients/web `.stage` + `.stack`: center the (bot + reply) group.
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Padding(
                padding: const EdgeInsets.fromLTRB(12, 12, 12, 12),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        StatusBadge(state: s.state),
                        const SizedBox(height: 6),
                        Listener(
                          onPointerDown: (_) => _onBotPointerDown(),
                          onPointerUp: (_) => _onBotPointerUp(),
                          onPointerCancel: (_) => _onBotPointerUp(),
                          child: GestureDetector(
                            behavior: HitTestBehavior.opaque,
                            onTap: _onBotTap,
                            onLongPress: _openSettings,
                            child: ConstrainedBox(
                              constraints: BoxConstraints(
                                maxWidth: botW,
                                maxHeight: (screenH * 0.52).clamp(0.0, 380.0),
                              ),
                              child: PixelBot(
                                key: ValueKey('${s.petId}-${s.petsEpoch}'),
                                mood: s.state,
                                petId: s.petId,
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 16),
                    SizedBox(
                      height: replyH,
                      width: double.infinity,
                      child: GestureDetector(
                        behavior: HitTestBehavior.opaque,
                        onLongPress: () {
                          if (s.canComposeText) _openComposer();
                        },
                        onTap: s.canReplay
                            ? () async {
                                await s.replayLast();
                              }
                            : null,
                        child: SingleChildScrollView(
                          controller: _replyScroll,
                          physics: const ClampingScrollPhysics(),
                          child: Text.rich(
                            TextSpan(
                              children: [
                                TextSpan(
                                  text: reply.isEmpty ? '' : reply,
                                  style: WebUiTheme.replyText,
                                ),
                                if (s.state == ClientState.speaking ||
                                    s.state == ClientState.listening ||
                                    s.state == ClientState.busy ||
                                    (reply.isEmpty && s.state == ClientState.idle))
                                  WidgetSpan(
                                    alignment: PlaceholderAlignment.baseline,
                                    baseline: TextBaseline.alphabetic,
                                    child: _Caret(
                                      visible: reply.isEmpty ||
                                          s.state == ClientState.speaking ||
                                          s.state == ClientState.busy,
                                    ),
                                  ),
                              ],
                            ),
                            textAlign: TextAlign.left,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _Caret extends StatefulWidget {
  const _Caret({required this.visible});
  final bool visible;

  @override
  State<_Caret> createState() => _CaretState();
}

class _CaretState extends State<_Caret> with SingleTickerProviderStateMixin {
  late final AnimationController _c;

  @override
  void initState() {
    super.initState();
    _c = AnimationController(vsync: this, duration: const Duration(milliseconds: 900))
      ..repeat();
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.visible) return const SizedBox.shrink();
    return AnimatedBuilder(
      animation: _c,
      builder: (context, child) {
        final on = _c.value < 0.5;
        return Opacity(opacity: on ? 1 : 0, child: child);
      },
      child: Container(
        width: 6,
        height: 18,
        margin: const EdgeInsets.only(left: 1),
        color: WebUiTheme.accent,
      ),
    );
  }
}
