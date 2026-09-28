import 'package:flutter/material.dart';

/// ChatGPT-like light shell — tokens aligned with clients/web/styles.css
abstract final class WebUiTheme {
  static const bg0 = Color(0xFFFFFFFF);
  static const bgSoft = Color(0xFFF7F7F8);
  static const text = Color(0xFF0D0D0D);
  static const muted = Color(0xFF8E8EA0);
  static const accent = Color(0xFF1A73E8);
  static const accentHover = Color(0xFF1557B0);
  static const panel = Color(0xFFFFFFFF);
  static const line = Color(0xFFE5E5E5);
  static const bubbleUser = Color(0xFFE8F0FE);
  static const bubbleAssistant = Color(0x00000000);

  static const radius = 18.0;
  static const radiusSm = 10.0;

  static const uiText = TextStyle(
    color: text,
    fontSize: 13,
    height: 1.35,
  );

  static const bubbleText = TextStyle(
    color: text,
    fontSize: 15.5,
    height: 1.55,
  );

  static const replyText = bubbleText;
}
