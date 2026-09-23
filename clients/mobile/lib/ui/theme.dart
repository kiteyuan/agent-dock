import 'package:flutter/material.dart';

/// Colors / layout tokens aligned with clients/web/styles.css
abstract final class WebUiTheme {
  static const bg0 = Color(0xFF0A0E12);
  static const text = Color(0xFFC8D0D8);
  static const muted = Color(0xFF6A7684);
  static const accent = Color(0xFF3ECF8E);
  static const panel = Color(0xFF0D1218);
  static const line = Color(0xFF243040);

  static const replySize = 24.0;
  static const replyLh = 1.25;
  /// Preferred visible lines; shrinks on short screens via [replyBoxHeightFor].
  static const replyLines = 6;
  static const replyLinesMin = 3;
  /// Reply box never takes more than this fraction of screen height.
  static const replyMaxScreenFraction = 0.22;

  static double get lineHeightPx => replySize * replyLh;

  static double get replyBoxHeight => lineHeightPx * replyLines;

  /// Screen-aware height: prefer [replyLines], never below [replyLinesMin],
  /// and never above [replyMaxScreenFraction] of the viewport.
  static double replyBoxHeightFor(double screenHeight) {
    final ideal = lineHeightPx * replyLines;
    final minH = lineHeightPx * replyLinesMin;
    final maxH = screenHeight * replyMaxScreenFraction;
    if (maxH <= minH) return minH;
    if (ideal <= maxH) return ideal;
    return maxH;
  }

  static const uiText = TextStyle(
    color: text,
    fontSize: 12,
    height: 1.25,
    fontFamily: 'monospace',
  );

  static const replyText = TextStyle(
    color: text,
    fontSize: replySize,
    height: replyLh,
    fontFamily: 'monospace',
  );
}
