import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../session/client_state.dart';
import 'theme.dart';

/// Pixel-border status tag (no fill, no dot — mood via border color).
/// Corners are stair-stepped (pixel soft-round), not CSS/Material radius.
class StatusBadge extends StatelessWidget {
  const StatusBadge({super.key, required this.state, this.onTap});

  final ClientState state;
  final VoidCallback? onTap;

  static String labelFor(ClientState s) => switch (s) {
        ClientState.offline => '未连接',
        ClientState.connecting => '连接中…',
        ClientState.idle => '在线',
        ClientState.listening => '听着…',
        ClientState.busy => '处理中…',
        ClientState.speaking => '播报中',
        ClientState.error => '出错了',
      };

  static Color borderFor(ClientState s) => switch (s) {
        ClientState.idle => const Color(0xFF22C55E),
        ClientState.speaking => const Color(0xFFEC4899),
        ClientState.listening => WebUiTheme.accent,
        ClientState.busy => const Color(0xFFF59E0B),
        ClientState.connecting => const Color(0xFFA78BFA),
        ClientState.error => const Color(0xFFEF4444),
        ClientState.offline => const Color(0xFF9AA0A6),
      };

  @override
  Widget build(BuildContext context) {
    final color = borderFor(state);
    final tag = CustomPaint(
      painter: _PixelTagBorderPainter(color: color, stroke: 2),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
        child: Text(
          labelFor(state),
          style: const TextStyle(
            color: WebUiTheme.text,
            fontSize: 11,
            fontWeight: FontWeight.w700,
            height: 1.2,
            letterSpacing: 0.4,
            fontFamily: 'Courier',
            fontFamilyFallback: [
              'Courier New',
              'Consolas',
              'monospace',
            ],
          ),
        ),
      ),
    );

    if (onTap == null) return tag;
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: tag,
    );
  }
}

/// Draws a 2px outline with 3px stair-step corners (8-bit soft round).
class _PixelTagBorderPainter extends CustomPainter {
  _PixelTagBorderPainter({required this.color, required this.stroke});

  final Color color;
  final double stroke;

  @override
  void paint(Canvas canvas, Size size) {
    final inset = stroke / 2;
    final s = 3.0; // step size for pixel corner
    final w = size.width;
    final h = size.height;
    final path = Path()
      ..moveTo(s, inset)
      ..lineTo(w - s, inset)
      ..lineTo(w - inset, s)
      ..lineTo(w - inset, h - s)
      ..lineTo(w - s, h - inset)
      ..lineTo(s, h - inset)
      ..lineTo(inset, h - s)
      ..lineTo(inset, s)
      ..close();

    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = stroke
      ..strokeJoin = StrokeJoin.miter
      ..isAntiAlias = false;
    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(covariant _PixelTagBorderPainter old) =>
      old.color != color || old.stroke != stroke;
}

/// Tiny helper used by HomePage copy action.
Future<void> copyText(String text) async {
  await Clipboard.setData(ClipboardData(text: text));
}
