import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../session/client_state.dart';
import 'theme.dart';

/// ChatGPT-like status pill in the top chrome.
class StatusBadge extends StatelessWidget {
  const StatusBadge({super.key, required this.state});

  final ClientState state;

  static String labelFor(ClientState s) => switch (s) {
        ClientState.offline => '未连接',
        ClientState.connecting => '连接中…',
        ClientState.idle => '在线',
        ClientState.listening => '听着…',
        ClientState.busy => '处理中…',
        ClientState.speaking => '播报中',
        ClientState.error => '出错了',
      };

  static Color dotFor(ClientState s) => switch (s) {
        ClientState.idle || ClientState.speaking => const Color(0xFF34A853),
        ClientState.listening => WebUiTheme.accent,
        ClientState.busy => const Color(0xFFF9AB00),
        ClientState.connecting => const Color(0xFFA142F4),
        ClientState.error => const Color(0xFFEA4335),
        ClientState.offline => const Color(0xFF9AA0A6),
      };

  @override
  Widget build(BuildContext context) {
    final pulse = state == ClientState.listening ||
        state == ClientState.busy ||
        state == ClientState.speaking ||
        state == ClientState.connecting ||
        state == ClientState.error;

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        _Dot(color: dotFor(state), pulse: pulse),
        const SizedBox(width: 6),
        Flexible(
          child: Text(
            labelFor(state),
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              color: state == ClientState.idle
                  ? WebUiTheme.text
                  : state == ClientState.listening
                      ? WebUiTheme.accent
                      : WebUiTheme.muted,
              fontSize: 13,
              fontWeight: FontWeight.w500,
              height: 1.2,
            ),
          ),
        ),
      ],
    );
  }
}

class _Dot extends StatefulWidget {
  const _Dot({required this.color, required this.pulse});
  final Color color;
  final bool pulse;

  @override
  State<_Dot> createState() => _DotState();
}

class _DotState extends State<_Dot> with SingleTickerProviderStateMixin {
  late final AnimationController _c;

  @override
  void initState() {
    super.initState();
    _c = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 700),
    );
    if (widget.pulse) _c.repeat(reverse: true);
  }

  @override
  void didUpdateWidget(covariant _Dot oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.pulse && !_c.isAnimating) {
      _c.repeat(reverse: true);
    } else if (!widget.pulse && _c.isAnimating) {
      _c.stop();
      _c.value = 1;
    }
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _c,
      builder: (context, child) {
        final t = widget.pulse ? 0.45 + 0.55 * _c.value : 1.0;
        return Opacity(opacity: t, child: child);
      },
      child: Container(
        width: 7,
        height: 7,
        decoration: BoxDecoration(color: widget.color, shape: BoxShape.circle),
      ),
    );
  }
}

/// Tiny helper used by HomePage copy action.
Future<void> copyText(String text) async {
  await Clipboard.setData(ClipboardData(text: text));
}
