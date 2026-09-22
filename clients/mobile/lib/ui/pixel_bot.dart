import 'dart:async';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../session/client_state.dart';
import 'pet_catalog.dart';

/// Codex Pet atlas — same grid as clients/web/pixel-bot.js
class PixelBot extends StatefulWidget {
  const PixelBot({
    super.key,
    required this.mood,
    required this.petId,
  });

  final ClientState mood;
  final String petId;

  @override
  State<PixelBot> createState() => _PixelBotState();
}

class _PixelBotState extends State<PixelBot> {
  ui.Image? _sheet;
  int _tick = 0;
  Timer? _timer;

  static const cellW = PixelBotMetrics.cellW;
  static const cellH = PixelBotMetrics.cellH;

  static const _row = {
    'idle': 0,
    'waving': 3,
    'failed': 5,
    'waiting': 6,
    'review': 8,
  };

  static const _frames = {
    0: 6,
    1: 8,
    2: 8,
    3: 4,
    4: 5,
    5: 8,
    6: 6,
    7: 6,
    8: 6,
  };

  int _moodRow(ClientState m) {
    return switch (m) {
      ClientState.listening => _row['waiting']!,
      ClientState.busy || ClientState.connecting => _row['review']!,
      ClientState.speaking => _row['waving']!,
      ClientState.error || ClientState.offline => _row['failed']!,
      _ => _row['idle']!,
    };
  }

  @override
  void initState() {
    super.initState();
    _load(widget.petId);
    _timer = Timer.periodic(const Duration(milliseconds: 160), (_) {
      if (!mounted) return;
      setState(() => _tick++);
    });
  }

  @override
  void didUpdateWidget(covariant PixelBot oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.petId != widget.petId) {
      _tick = 0;
      _load(widget.petId);
    }
    if (oldWidget.mood != widget.mood) {
      _tick = 0;
    }
  }

  Future<void> _load(String petId) async {
    if (petId.trim().isEmpty) {
      if (!mounted) return;
      setState(() {
        _sheet?.dispose();
        _sheet = null;
      });
      return;
    }
    try {
      final bytes = await PetCatalog.loadSheetBytes(petId);
      final codec = await ui.instantiateImageCodec(bytes);
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
      debugPrint('PixelBot load failed: $e');
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
    final phase = (_tick % 2).toDouble();
    Widget sprite = CustomPaint(
      size: const Size(cellW, cellH),
      painter: _SheetPainter(
        sheet: _sheet,
        row: _moodRow(widget.mood),
        tick: _tick,
        frames: _frames,
      ),
    );

    if (widget.mood == ClientState.speaking) {
      sprite = Transform.translate(
        offset: Offset(0, -3 * phase),
        child: sprite,
      );
    } else if (widget.mood == ClientState.listening) {
      sprite = Transform.scale(
        scale: 1 + 0.03 * phase,
        child: sprite,
      );
    }

    return AspectRatio(
      aspectRatio: cellW / cellH,
      child: FittedBox(
        fit: BoxFit.contain,
        child: sprite,
      ),
    );
  }
}

class PixelBotMetrics {
  static const cellW = 192.0;
  static const cellH = 208.0;
}

class _SheetPainter extends CustomPainter {
  _SheetPainter({
    required this.sheet,
    required this.row,
    required this.tick,
    required this.frames,
  });

  final ui.Image? sheet;
  final int row;
  final int tick;
  final Map<int, int> frames;

  @override
  void paint(Canvas canvas, Size size) {
    final img = sheet;
    if (img == null) return;
    final n = frames[row] ?? 1;
    final col = tick % n;
    final src = Rect.fromLTWH(
      col * PixelBotMetrics.cellW,
      row * PixelBotMetrics.cellH,
      PixelBotMetrics.cellW,
      PixelBotMetrics.cellH,
    );
    final dst = Offset.zero & size;
    final paint = Paint()..filterQuality = FilterQuality.none;
    canvas.drawImageRect(img, src, dst, paint);
  }

  @override
  bool shouldRepaint(covariant _SheetPainter old) =>
      old.sheet != sheet || old.row != row || old.tick != tick;
}
