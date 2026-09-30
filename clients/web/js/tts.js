import { store } from "./store.js";
import { enterIdle, enterSpeak, setMood, syncReplayHint } from "./mood.js";

export function stopTtsPlayback() {
  store.ttsPlayQueue = [];
  store.ttsChunks = [];
  store.turnTtsSegments = [];
  store.turnAwaitingIdle = false;
  if (store.audioEl) {
    try {
      store.audioEl.pause();
    } catch (_) {}
  }
  store.ttsPlaying = false;
}

export function armDropRemoteTts() {
  store.dropRemoteTts = true;
  stopTtsPlayback();
}

export function clearDropRemoteTts() {
  store.dropRemoteTts = false;
}

export function maybeIdleAfterTurn(enterIdleFn, renderTranscript, clearProcessLine) {
  if (!store.turnAwaitingIdle) return;
  if (store.ttsPlaying || store.ttsPlayQueue.length || store.ttsChunks.length) {
    if (document.getElementById("stage")?.dataset.mood !== "speak") {
      setMood("speak");
    }
    syncReplayHint();
    return;
  }
  store.turnAwaitingIdle = false;
  if (store.turnTtsSegments.length) {
    store.lastTtsSegments = store.turnTtsSegments.slice();
    store.turnTtsSegments = [];
  }
  store.activeAssistantId = null;
  renderTranscript();
  clearProcessLine();
  if (store.sessionId) enterIdleFn();
  syncReplayHint();
}

function playTtsChunks(chunks) {
  return new Promise((resolve) => {
    if (!chunks || !chunks.length) {
      resolve();
      return;
    }
    let total = 0;
    chunks.forEach((c) => (total += c.length));
    const out = new Uint8Array(total);
    let o = 0;
    for (const c of chunks) {
      out.set(c, o);
      o += c.length;
    }
    const wav = out[0] === 0x52 && out[1] === 0x49;
    const blob = new Blob([out], { type: wav ? "audio/wav" : "audio/mpeg" });
    const url = URL.createObjectURL(blob);
    if (store.audioEl) {
      try {
        store.audioEl.pause();
      } catch (_) {}
    }
    store.audioEl = new Audio(url);
    enterSpeak();
    const done = () => {
      URL.revokeObjectURL(url);
      resolve();
    };
    store.audioEl.onended = done;
    store.audioEl.onerror = done;
    store.audioEl.play().catch(done);
  });
}

export function pumpTts(ctx) {
  if (store.ttsPlaying) return;
  if (!store.ttsPlayQueue.length) {
    maybeIdleAfterTurn(ctx.enterIdle, ctx.renderTranscript, ctx.clearProcessLine);
    syncReplayHint();
    return;
  }
  store.ttsPlaying = true;
  syncReplayHint();
  const item = store.ttsPlayQueue.shift();
  const chunks = item && item.chunks ? item.chunks : item;
  playTtsChunks(chunks).finally(() => {
    store.ttsPlaying = false;
    pumpTts(ctx);
  });
}

export function replayLastTts() {
  if (store.ttsPlaying || store.ttsPlayQueue.length || store.recording || store.starting) {
    return;
  }
  if (!store.lastTtsSegments.length) return;
  store.ttsPlayQueue = store.lastTtsSegments.map((s) => ({
    chunks: s.chunks,
    text: "",
  }));
  setMood("speak");
  if (store._pumpTts) store._pumpTts();
}

/**
 * End local/remote TTS. Preserve lastTtsSegments for replay.
 * Snapshot in-progress turn audio into lastTts before clearing.
 */
export function stopSpeakPlayback() {
  if (store.turnTtsSegments.length) {
    store.lastTtsSegments = store.turnTtsSegments.slice();
  }
  store.dropRemoteTts = true;
  store.ttsPlayQueue = [];
  store.ttsChunks = [];
  store.turnTtsSegments = [];
  store.turnAwaitingIdle = false;
  if (store.audioEl) {
    try {
      store.audioEl.pause();
    } catch (_) {}
  }
  store.ttsPlaying = false;
  if (store.sessionId) enterIdle();
  else setMood("offline");
  syncReplayHint();
}

/** Stop current playback, or replay last turn when idle. */
export function toggleLastTts() {
  const playing =
    store.ttsPlaying ||
    store.ttsPlayQueue.length > 0 ||
    document.getElementById("stage")?.dataset.mood === "speak";
  if (playing) {
    stopSpeakPlayback();
    return;
  }
  replayLastTts();
}
