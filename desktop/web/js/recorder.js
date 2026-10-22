import { store } from "./store.js";
import { encodeWav, resampleTo16k } from "./wav.js";

export function isMicActive() {
  return !!(
    store.recording ||
    store.recStream ||
    store.audioCtx ||
    store.processor
  );
}

export async function releaseMicHardware() {
  try {
    store.processor && store.processor.disconnect();
  } catch (_) {}
  try {
    store.sourceNode && store.sourceNode.disconnect();
  } catch (_) {}
  try {
    store.recStream && store.recStream.getTracks().forEach((t) => t.stop());
  } catch (_) {}
  const ctx = store.audioCtx;
  store.processor = null;
  store.sourceNode = null;
  store.recStream = null;
  store.audioCtx = null;
  if (ctx) {
    try {
      await Promise.race([
        ctx.close(),
        new Promise((r) => setTimeout(r, 400)),
      ]);
    } catch (_) {}
  }
}

/** Open mic and start collecting PCM. Caller sets store.recording = true. */
export async function openMic() {
  store.pcmChunks = [];
  if (!window.isSecureContext && !/^(localhost|127\.0\.0\.1)$/i.test(location.hostname)) {
    throw new Error(
      "Web UI 仅支持本机预览（http://127.0.0.1）。手机请用 Flutter 客户端。"
    );
  }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    throw new Error("此浏览器不支持麦克风录音");
  }
  store.recStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  store.audioCtx = new (window.AudioContext || window.webkitAudioContext)({
    sampleRate: 16000,
  });
  store.sourceNode = store.audioCtx.createMediaStreamSource(store.recStream);
  store.processor = store.audioCtx.createScriptProcessor(4096, 1, 1);
  const silent = store.audioCtx.createGain();
  silent.gain.value = 0;
  store.processor.onaudioprocess = (e) => {
    if (!store.recording) return;
    store.pcmChunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
  };
  store.sourceNode.connect(store.processor);
  store.processor.connect(silent);
  silent.connect(store.audioCtx.destination);
}

/** Merge buffered PCM → 16k WAV ArrayBuffer. Clears pcmChunks. */
export function takeWavBuffer() {
  const capturedRate = store.audioCtx ? store.audioCtx.sampleRate : 16000;
  const chunks = store.pcmChunks;
  store.pcmChunks = [];
  let n = 0;
  chunks.forEach((c) => (n += c.length));
  const merged = new Float32Array(n);
  let off = 0;
  for (const c of chunks) {
    merged.set(c, off);
    off += c.length;
  }
  return encodeWav(resampleTo16k(merged, capturedRate), 16000);
}

export function releaseMicSync() {
  try {
    store.processor && store.processor.disconnect();
  } catch (_) {}
  try {
    store.sourceNode && store.sourceNode.disconnect();
  } catch (_) {}
  try {
    store.recStream && store.recStream.getTracks().forEach((t) => t.stop());
  } catch (_) {}
  store.processor = null;
  store.sourceNode = null;
  store.recStream = null;
  if (store.audioCtx) {
    const ctx = store.audioCtx;
    store.audioCtx = null;
    try {
      ctx.close();
    } catch (_) {}
  }
  store.pcmChunks = [];
}
