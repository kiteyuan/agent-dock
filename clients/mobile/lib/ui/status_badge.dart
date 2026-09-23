import 'dart:async';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../session/client_state.dart';

/// Pixel status glyphs above the pet — same sheet as clients/web/status-icons.png.
class StatusBadge extends StatefulWidget {
  const StatusBadge({super.key, required this.state});

  final ClientState state;

  static const assetPath = 'assets/status-icons.png';
  static const cell = 16.0;
  static const frames = 4;
  static const displaySize = 32.0;

  /// Row order must match scripts/generate_status_icons.py ROWS.
  static int rowFor(ClientState s) => switch (s) {
        ClientState.idle => 0,
        ClientState.listening => 1,
        ClientState.busy => 2,
        ClientState.speaking => 3,
        ClientState.connecting => 4,
        ClientState.offline => 5,
        ClientState.error => 6,
      };

  static Duration periodFor(ClientState s) => switch (s) {
        ClientState.idle => const Duration(milliseconds: 1400),
        ClientState.offline => const Duration(milliseconds: 1 << 30),
        ClientState.error => const Duration(milliseconds: 800),
        ClientState.busy => const Duration(milliseconds: 700),
        _ => const Duration(milliseconds: 550),
      };

  @override
  State<StatusBadge> createState() => _StatusBadgeState();
}

class _StatusBadgeState extends State<StatusBadge> {
  ui.Image? _sheet;
  int _tick = 0;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _load();
    _armTimer();
  }

  @override
  void didUpdateWidget(covariant StatusBadge oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.state != widget.state) {
      _tick = 0;
      _armTimer();
    }
  }

  void _armTimer() {
    _timer?.cancel();
    final period = StatusBadge.periodFor(widget.state);
    if (widget.state == ClientState.offline) return;
    final frameMs = (period.inMilliseconds / StatusBadge.frames).round().clamp(80, 400);
    _timer = Timer.periodic(Duration(milliseconds: frameMs), (_) {
      if (!mounted) return;
      setState(() => _tick++);
    });
  }

  Future<void> _load() async {
    try {
      final data = await rootBundle.load(StatusBadge.assetPath);
      final codec = await ui.instantiateImageCodec(data.buffer.asUint8List());
      final frame = await codec.getNextFrame();
      if (!mounted) {
        frame.image.dispose();
        return;
      }
      setState(() {
        _sheet?.dispose();
        _sheet = frame.image;
      });
    } catch (e) {
      debugPrint('StatusBadge load failed: $e');
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    _sheet?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final sheet = _sheet;
    final row = StatusBadge.rowFor(widget.state);
    final frame = widget.state == ClientState.offline
        ? 0
        : _tick % StatusBadge.frames;
    final opacity = widget.state == ClientState.idle ? 0.75 : 1.0;

    return SizedBox(
      height: 36,
      width: StatusBadge.displaySize,
      child: sheet == null
          ? const SizedBox.shrink()
          : Opacity(
              opacity: opacity,
              child: CustomPaint(
                size: const Size(StatusBadge.displaySize, StatusBadge.displaySize),
                painter: _StatusPainter(sheet: sheet, row: row, frame: frame),
              ),
            ),
    );
  }
}

class _StatusPainter extends CustomPainter {
  _StatusPainter({
    required this.sheet,
    required this.row,
    required this.frame,
  });

  final ui.Image sheet;
  final int row;
  final int frame;

  @override
  void paint(Canvas canvas, Size size) {
    const c = StatusBadge.cell;
    final src = Rect.fromLTWH(frame * c, row * c, c, c);
    final dst = Offset.zero & size;
    final paint = Paint()..filterQuality = FilterQuality.none;
    canvas.drawImageRect(sheet, src, dst, paint);
  }

  @override
  bool shouldRepaint(covariant _StatusPainter old) =>
      old.sheet != sheet || old.row != row || old.frame != frame;
}
