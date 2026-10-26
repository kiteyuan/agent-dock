import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';

/// Record 16 kHz mono WAV for Runtime STT (same as host desk pet).
class WavRecorder {
  final AudioRecorder _rec = AudioRecorder();
  String? _path;

  Future<bool> hasPermission() => _rec.hasPermission();

  Future<void> start() async {
    if (!await _rec.hasPermission()) {
      throw StateError('麦克风权限被拒绝');
    }
    final dir = await getTemporaryDirectory();
    _path = '${dir.path}/agentdock_rec_${DateTime.now().millisecondsSinceEpoch}.wav';
    await _rec.start(
      const RecordConfig(
        encoder: AudioEncoder.wav,
        sampleRate: 16000,
        numChannels: 1,
        bitRate: 256000,
      ),
      path: _path!,
    );
  }

  /// Stops and returns WAV bytes (or null if empty/missing).
  Future<Uint8List?> stop() async {
    final path = await _rec.stop();
    final filePath = path ?? _path;
    _path = null;
    if (filePath == null) return null;
    final file = File(filePath);
    if (!await file.exists()) return null;
    final bytes = await file.readAsBytes();
    try {
      await file.delete();
    } catch (_) {}
    return bytes.isEmpty ? null : Uint8List.fromList(bytes);
  }

  Future<void> cancel() async {
    try {
      await _rec.cancel();
    } catch (_) {
      try {
        await _rec.stop();
      } catch (_) {}
    }
    _path = null;
  }

  Future<void> dispose() => _rec.dispose();
}
