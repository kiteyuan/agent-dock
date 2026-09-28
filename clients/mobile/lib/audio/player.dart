import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:audioplayers/audioplayers.dart';
import 'package:path_provider/path_provider.dart';

class TtsSegment {
  TtsSegment({required this.bytes, this.text = ''});
  final Uint8List bytes;
  final String text;
}

/// Queue sentence-level TTS blobs and play sequentially (web-aligned).
class TtsPlayer {
  final AudioPlayer _player = AudioPlayer();
  final List<TtsSegment> _queue = [];
  List<TtsSegment> lastTurn = [];
  final List<TtsSegment> _turnBuf = [];
  bool _playing = false;
  void Function()? onBecameIdle;
  void Function()? onQueueChanged;

  bool get isBusy => _playing || _queue.isNotEmpty;

  void beginTurn() {
    _turnBuf.clear();
    onQueueChanged?.call();
  }

  void enqueue(TtsSegment seg) {
    if (seg.bytes.isEmpty) return;
    _queue.add(seg);
    _turnBuf.add(seg);
    onQueueChanged?.call();
    unawaited(_pump());
  }

  void clear({bool keepLast = false}) {
    _queue.clear();
    if (!keepLast) {
      // leave lastTurn as-is for replay
    }
    unawaited(_player.stop());
    _playing = false;
    onQueueChanged?.call();
  }

  void commitTurn() {
    if (_turnBuf.isNotEmpty) {
      lastTurn = List<TtsSegment>.from(_turnBuf);
      _turnBuf.clear();
      onQueueChanged?.call();
    }
  }

  Future<void> replayLast() async {
    if (lastTurn.isEmpty || isBusy) return;
    for (final seg in lastTurn) {
      _queue.add(seg);
    }
    onQueueChanged?.call();
    await _pump();
  }

  Future<void> _pump() async {
    if (_playing) return;
    _playing = true;
    onQueueChanged?.call();
    try {
      while (_queue.isNotEmpty) {
        final seg = _queue.removeAt(0);
        final dir = await getTemporaryDirectory();
        final isWav = seg.bytes.length >= 4 &&
            seg.bytes[0] == 0x52 &&
            seg.bytes[1] == 0x49;
        final path =
            '${dir.path}/tts_${DateTime.now().millisecondsSinceEpoch}.${isWav ? 'wav' : 'mp3'}';
        final file = File(path);
        await file.writeAsBytes(seg.bytes, flush: true);
        try {
          final done = Completer<void>();
          late StreamSubscription sub;
          sub = _player.onPlayerComplete.listen((_) {
            if (!done.isCompleted) done.complete();
          });
          await _player.play(DeviceFileSource(path));
          await done.future.timeout(
            const Duration(minutes: 2),
            onTimeout: () {},
          );
          await sub.cancel();
        } finally {
          try {
            await file.delete();
          } catch (_) {}
        }
      }
    } finally {
      _playing = false;
      onBecameIdle?.call();
      onQueueChanged?.call();
    }
  }

  Future<void> dispose() async {
    clear();
    await _player.dispose();
  }
}
