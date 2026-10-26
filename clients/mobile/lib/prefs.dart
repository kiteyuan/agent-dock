/// Connection prefs helpers (align with desktop/web/js/prefs.js).

bool isLoopbackWsUrl(String url) {
  final trimmed = url.trim();
  if (trimmed.isEmpty) return false;
  try {
    final u = Uri.parse(trimmed);
    final h = u.host.toLowerCase();
    return h == '127.0.0.1' || h == 'localhost' || h == '::1';
  } catch (_) {
    return false;
  }
}
