import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../pets/pet_catalog.dart';
import '../session/client_state.dart';
import '../session/device_session.dart';
import 'pixel_bot.dart';
import 'status_badge.dart';
import 'theme.dart';

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
  StreamSubscription? _sub;
  String _lastAppliedComposer = '';

  DeviceSession get s => widget.session;

  @override
  void initState() {
    super.initState();
    _url = TextEditingController(text: s.url);
    _token = TextEditingController(text: s.token);
    _compose = TextEditingController();
    _sub = s.changes.listen((_) {
      if (!mounted) return;
      _syncComposerFromSession();
      setState(() {});
      unawaited(_savePrefs());
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (_chatScroll.hasClients) {
          _chatScroll.jumpTo(_chatScroll.position.maxScrollExtent);
        }
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

  Future<void> _submitCompose() async {
    final text = _compose.text.trim();
    if (text.isEmpty || !s.canComposeText) return;
    _compose.clear();
    await s.sendText(text);
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

  @override
  void dispose() {
    _sub?.cancel();
    _url.dispose();
    _token.dispose();
    _compose.dispose();
    _composeFocus.dispose();
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
      backgroundColor: WebUiTheme.bgSoft,
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 720),
            child: Column(
              children: [
                _buildHeader(online: online),
                Expanded(child: _buildTranscript(screenW)),
                _buildComposer(online: online, canType: canType, listening: listening),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildHeader({required bool online}) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 8, 8, 4),
      child: Row(
        children: [
          InkWell(
            onTap: _openSettings,
            borderRadius: BorderRadius.circular(12),
            child: Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: WebUiTheme.bg0,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: WebUiTheme.line),
              ),
              clipBehavior: Clip.antiAlias,
              child: PixelBot(
                key: ValueKey('hdr-${s.petId}-${s.petsEpoch}'),
                mood: s.state,
                petId: s.petId,
              ),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  '对话',
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                    color: WebUiTheme.text,
                  ),
                ),
                StatusBadge(state: s.state),
              ],
            ),
          ),
          PopupMenuButton<String>(
            icon: const Icon(Icons.more_horiz_rounded, color: WebUiTheme.muted),
            onSelected: (v) {
              if (v == 'new') _confirmNewSession();
            },
            itemBuilder: (_) => [
              PopupMenuItem(
                value: 'new',
                enabled: online,
                child: const Text('新开会话'),
              ),
            ],
          ),
        ],
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
              padding: const EdgeInsets.only(bottom: 12, top: 8),
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
                              ? Text(m.text, style: WebUiTheme.bubbleText)
                              : MarkdownBody(
                                  data: m.text,
                                  selectable: true,
                                  styleSheet: MarkdownStyleSheet.fromFlutterTheme(
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
                              if (isLastAssistant && s.canReplay)
                                IconButton(
                                  visualDensity: VisualDensity.compact,
                                  iconSize: 18,
                                  color: WebUiTheme.muted,
                                  onPressed: () => s.replayLast(),
                                  icon: const Icon(Icons.replay_rounded),
                                  tooltip: '重播',
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
      padding: const EdgeInsets.fromLTRB(10, 0, 10, 20),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: _onMicPressed,
            child: AnimatedScale(
              scale: listening ? 1.04 : 1.0,
              duration: const Duration(milliseconds: 180),
              child: SizedBox(
                width: 72,
                height: 78,
                child: PixelBot(
                  key: ValueKey('composer-${s.petId}-${s.petsEpoch}'),
                  mood: s.state,
                  petId: s.petId,
                ),
              ),
            ),
          ),
          const SizedBox(height: 4),
          Container(
            padding: const EdgeInsets.fromLTRB(6, 6, 6, 6),
            decoration: BoxDecoration(
              color: WebUiTheme.bg0,
              borderRadius: BorderRadius.circular(999),
              border: Border.all(color: WebUiTheme.line),
            ),
            child: Row(
              children: [
                IconButton(
                  onPressed: canType
                      ? () {
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(
                              content: Text(
                                  '移动端图片附件稍后接入；请先用桌面 Web 发送图片'),
                              duration: Duration(seconds: 2),
                            ),
                          );
                        }
                      : null,
                  color: WebUiTheme.muted,
                  icon: const Icon(Icons.add_rounded),
                  tooltip: '添加图片',
                ),
                Expanded(
                  child: TextField(
                    controller: _compose,
                    focusNode: _composeFocus,
                    enabled: canType,
                    minLines: 1,
                    maxLines: 4,
                    style: const TextStyle(
                        color: WebUiTheme.text, fontSize: 15),
                    textInputAction: TextInputAction.send,
                    onSubmitted: (_) => _submitCompose(),
                    decoration: InputDecoration(
                      isDense: true,
                      border: InputBorder.none,
                      hintText: s.composerHint,
                      hintStyle: const TextStyle(color: WebUiTheme.muted),
                    ),
                  ),
                ),
                IconButton(
                  onPressed: online ? _onMicPressed : _openSettings,
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
          ),
        ],
      ),
    );
  }
}
