import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';

class PetInfo {
  PetInfo({
    required this.id,
    required this.label,
    required this.sheet,
    this.url = '',
    this.remoteUrl,
  });

  final String id;
  final String label;
  final String sheet;
  final String url;
  String? remoteUrl;
}

/// Pets come only from Runtime `pets.list` → download → app cache.
/// No bundled offline sprites.
class PetCatalog {
  PetCatalog._();

  static final Map<String, PetInfo> pets = {};
  static String defaultId = '';
  static String? assetsBaseUrl;
  static int assetsPort = 8766;

  static Future<void> ensureLoaded() async {
    // Catalog arrives via applyRemoteCatalog after session.accept.
  }

  static void _applyList(dynamic list, String? defaultHint) {
    if (list is! List) return;
    final next = <String, PetInfo>{};
    for (final item in list) {
      if (item is! Map) continue;
      final id = '${item['id'] ?? ''}'.trim();
      if (id.isEmpty) continue;
      final sheet =
          '${item['sheet'] ?? '$id/spritesheet.webp'}'.replaceAll(RegExp(r'^/+'), '');
      final info = PetInfo(
        id: id,
        label: '${item['label'] ?? id}',
        sheet: sheet,
        url: '${item['url'] ?? ''}',
      );
      if (assetsBaseUrl != null && assetsBaseUrl!.isNotEmpty) {
        info.remoteUrl =
            '${assetsBaseUrl!.replaceAll(RegExp(r'/+$'), '')}/$sheet';
      }
      next[id] = info;
    }
    if (next.isEmpty) return;
    pets
      ..clear()
      ..addAll(next);
    final d = (defaultHint ?? '').trim();
    if (d.isNotEmpty && pets.containsKey(d)) {
      defaultId = d;
    } else if (pets.isNotEmpty) {
      defaultId = pets.keys.first;
    }
  }

  /// Derive http://<ws-host>:<assetsPort>/pets from the device WS URL.
  static String? baseFromWs(String? wsUrl, {int? port, String? serverBase}) {
    final p = port ?? assetsPort;
    final raw = (wsUrl ?? '').trim();
    if (raw.isEmpty) return serverBase;
    try {
      final httpUrl = raw.replaceFirst(RegExp(r'^ws', caseSensitive: false), 'http');
      final u = Uri.parse(httpUrl);
      if (u.host.isEmpty) return serverBase;
      return Uri(
        scheme: u.scheme.isEmpty ? 'http' : u.scheme,
        host: u.host,
        port: p,
        path: '/pets',
      ).toString().replaceAll(RegExp(r'/+$'), '');
    } catch (_) {
      return serverBase;
    }
  }

  /// Apply Runtime `pets.list.result`. Prefer base derived from [wsUrl].
  static Future<void> applyRemoteCatalog(
    Map<String, dynamic> payload, {
    String? wsUrl,
  }) async {
    final portRaw = payload['assets_port'];
    if (portRaw is num) assetsPort = portRaw.toInt();
    final serverBase = '${payload['base_url'] ?? ''}'.trim();
    assetsBaseUrl = baseFromWs(
          wsUrl,
          port: assetsPort,
          serverBase: serverBase.isEmpty ? null : serverBase,
        ) ??
        (serverBase.isEmpty ? null : serverBase);
    _applyList(payload['pets'], payload['default'] as String?);
  }

  static String resolveId(String? id) {
    if (id != null && pets.containsKey(id)) return id;
    if (defaultId.isNotEmpty && pets.containsKey(defaultId)) return defaultId;
    return pets.keys.isEmpty ? '' : pets.keys.first;
  }

  static Future<Directory> _cacheRoot() async {
    final support = await getApplicationSupportDirectory();
    final dir = Directory('${support.path}/pets');
    if (!await dir.exists()) await dir.create(recursive: true);
    return dir;
  }

  static Future<File> _cacheFile(String petId, String sheet) async {
    final root = await _cacheRoot();
    final safe = sheet.replaceAll('\\', '/');
    final file = File('${root.path}/$safe');
    final parent = file.parent;
    if (!await parent.exists()) await parent.create(recursive: true);
    return file;
  }

  /// Bytes for spritesheet: cache → download from Runtime. No bundle fallback.
  static Future<Uint8List> loadSheetBytes(String? petId) async {
    final id = resolveId(petId);
    if (id.isEmpty) {
      throw StateError('pet catalog empty — connect to Runtime first');
    }
    final pet = pets[id];
    if (pet == null) {
      throw StateError('unknown pet: $id');
    }

    final cached = await _cacheFile(id, pet.sheet);
    if (await cached.exists()) {
      return cached.readAsBytes();
    }

    final remote = pet.remoteUrl;
    if (remote == null || remote.isEmpty) {
      throw StateError('no remote URL for pet $id');
    }
    final bytes = await _download(remote);
    await cached.writeAsBytes(bytes, flush: true);
    return bytes;
  }

  static Future<Uint8List> _download(String url) async {
    final client = HttpClient();
    try {
      final req = await client.getUrl(Uri.parse(url));
      final res = await req.close();
      if (res.statusCode < 200 || res.statusCode >= 300) {
        throw HttpException('HTTP ${res.statusCode}', uri: Uri.parse(url));
      }
      return await consolidateHttpClientResponseBytes(res);
    } finally {
      client.close(force: true);
    }
  }
}
