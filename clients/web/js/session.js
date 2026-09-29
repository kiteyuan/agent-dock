import { $ } from "./dom.js";
import { encodeMsg } from "./protocol.js";
import { stableDeviceId, saveConnectionPrefs } from "./prefs.js";
import { store, hooks } from "./store.js";
import { nativeProcessText } from "./text.js";
import { applyPetFromRuntime } from "./pets.js";
import {
  isMicActive,
  openMic,
  releaseMicHardware,
  releaseMicSync,
  takeWavBuffer,
} from "./recorder.js";
import {
  enterIdle,
  enterBusy,
  enterListen,
  enterSpeak,
  enterErr,
  setMood,
  restoreComposerPlaceholder,
  syncControls,
  syncReplayHint,
} from "./mood.js";
import {
  armDropRemoteTts,
  clearDropRemoteTts,
  stopTtsPlayback,
  pumpTts,
  replayLastTts,
  maybeIdleAfterTurn,
} from "./tts.js";
import {
  appendUserMessage,
  appendAssistantChunk,
  setAssistantText,
  finishTypewriter,
  stopTypewriter,
  clearMessages,
  clearProcessLine,
  showProcessLine,
  resetCaptionState,
  resetThinkingBuf,
  flushThinking,
  renderTranscript,
  renderAttachPreview,
  applyServerMessages,
} from "./transcript.js";

function pump() {
  pumpTts({ enterIdle, renderTranscript, clearProcessLine });
}

export function wireSessionHooks() {
  hooks.syncUi = syncControls;
  hooks.replayLastTts = () => {
    replayLastTts();
    pump();
  };
  store._pumpTts = pump;
}

function sendBinaryWav(wav) {
  const bytes = new Uint8Array(wav);
  store.ws.send(encodeMsg("audio.start", { session_id: store.sessionId }));
  for (let i = 0; i < bytes.length; i += 4096) {
    store.ws.send(bytes.subarray(i, i + 4096));
  }
  store.ws.send(encodeMsg("audio.end", { session_id: store.sessionId }));
}

export async function startTalk() {
  if (!store.ws || !store.sessionId || store.recording || store.starting || store.stopping) {
    return;
  }
  store.starting = true;
  syncControls();
  armDropRemoteTts();
  try {
    await openMic();
    store.recording = true;
    enterListen();
  } catch (err) {
    await releaseMicHardware();
    const detail =
      (err && err.message) ||
      (err && err.name === "NotAllowedError" ? "麦克风权限被拒绝" : "无法打开麦克风");
    store.activeAssistantId = null;
    setAssistantText(detail);
    enterErr();
    throw err;
  } finally {
    store.starting = false;
    syncControls();
  }
}

export async function stopTalk({ discard = false } = {}) {
  if (store.stopping) return;
  if (!isMicActive()) {
    if ($("stage").dataset.mood === "listen") {
      if (store.sessionId) enterIdle();
      else setMood("offline");
    }
    return;
  }

  store.stopping = true;
  store.recording = false;
  syncControls();
  if (!discard) enterBusy();
  else if (store.sessionId) setMood("busy");

  let wav = null;
  try {
    if (!discard) wav = takeWavBuffer();
    else store.pcmChunks = [];
    await releaseMicHardware();
  } finally {
    store.stopping = false;
    syncControls();
  }

  if (discard) {
    restoreComposerPlaceholder();
    if (store.sessionId) enterIdle();
    syncReplayHint();
    return;
  }

  enterBusy();
  store.ttsChunks = [];
  store.ttsPlayQueue = [];
  store.ttsPlaying = false;
  store.turnAwaitingIdle = false;
  store.turnTtsSegments = [];
  resetCaptionState();
  clearProcessLine();
  syncReplayHint();
  const input = $("composerInput");
  if (input) {
    input.value = "";
    input.placeholder = "识别中…";
  }
  if (!store.ws || !store.sessionId) {
    enterIdle();
    restoreComposerPlaceholder();
    return;
  }
  try {
    sendBinaryWav(wav);
  } catch (_) {
    restoreComposerPlaceholder();
    enterErr();
  }
}

export async function toggleTalk() {
  const wantStop =
    store.recording || isMicActive() || $("stage").dataset.mood === "listen";
  if (wantStop) {
    if (store.stopping) return;
    await stopTalk();
    return;
  }
  if (store.starting || store.stopping) return;
  const mood = $("stage").dataset.mood;
  if (mood === "busy") {
    cancelTurn();
    return;
  }
  if (mood === "speak" || store.ttsPlaying || store.ttsPlayQueue.length) {
    cancelTurn();
  }
  await startTalk();
}

export function applyLocalCancel() {
  store.recording = false;
  store.starting = false;
  store.stopping = false;
  resetThinkingBuf();
  clearProcessLine();
  armDropRemoteTts();
  stopTypewriter();
  resetCaptionState();
  store.turnAwaitingIdle = false;
  releaseMicSync();
  enterIdle();
  syncReplayHint();
}

export function cancelTurn() {
  if (!store.ws || !store.sessionId || store.starting) return;
  try {
    store.ws.send(encodeMsg("session.cancel", { session_id: store.sessionId }));
  } catch (_) {}
  applyLocalCancel();
}

export async function sendUserMessage(raw) {
  const text = String(raw || "").trim();
  const pending = store.pendingAttach.slice();
  const previewUrls = pending.map((a) => a.url).filter(Boolean);
  if ((!text && !pending.length) || !store.ws || !store.sessionId) return;
  if (store.recording) {
    try {
      await stopTalk({ discard: true });
    } catch (_) {
      store.recording = false;
    }
  }
  const mood = $("stage").dataset.mood;
  if (mood === "busy" || mood === "speak" || store.ttsPlaying || store.turnLocked) {
    try {
      store.ws.send(encodeMsg("session.cancel", { session_id: store.sessionId }));
    } catch (_) {}
    armDropRemoteTts();
  } else {
    armDropRemoteTts();
  }
  resetCaptionState();
  resetThinkingBuf();
  clearProcessLine();
  store.pendingAttach = [];
  renderAttachPreview();

  let images = [];
  try {
    images = await Promise.all(pending.map((a) => fileToImagePayload(a.file)));
    images = images.filter(Boolean);
  } catch (err) {
    enterErr();
    setAssistantText(`图片读取失败：${err?.message || err}`);
    enterIdle();
    syncReplayHint();
    return;
  }
  if (!text && !images.length) {
    enterIdle();
    return;
  }

  const sendText = text || (images.length ? `（发送了 ${images.length} 张图片）` : "");
  appendUserMessage(text || "", previewUrls);
  $("composerInput").value = "";
  enterBusy();
  syncReplayHint();
  try {
    const payload = { session_id: store.sessionId, text: sendText };
    if (images.length) payload.images = images;
    store.ws.send(encodeMsg("user.message", payload));
  } catch (_) {
    enterIdle();
  }
}

/** @param {File | undefined} file */
async function fileToImagePayload(file) {
  if (!file || !(file instanceof Blob)) return null;
  const maxBytes = 4 * 1024 * 1024;
  if (file.size > maxBytes) {
    throw new Error(`图片过大（上限 ${Math.round(maxBytes / 1024 / 1024)}MB）`);
  }
  const buf = await file.arrayBuffer();
  const bytes = new Uint8Array(buf);
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return {
    mime: file.type || "image/png",
    data: btoa(binary),
  };
}

function onEvent(type, payload = {}) {
  if (type === "stt.final") {
    clearDropRemoteTts();
    resetThinkingBuf();
    const t = String(payload.text || payload.content || "").trim();
    if (t) appendUserMessage(t);
    const input = $("composerInput");
    if (input) input.value = "";
    restoreComposerPlaceholder();
    enterBusy();
  } else if (type === "agent.start") {
    clearDropRemoteTts();
    flushThinking(true);
    enterBusy();
  } else if (type === "agent.thinking") {
    if (store.dropRemoteTts) return;
    const chunk = payload.content || payload.text || "";
    if (chunk) {
      store.thinkingBuf += String(chunk);
      flushThinking(false);
    }
    enterBusy();
  } else if (type === "agent.tool_call" || type === "agent.tool_result") {
    if (store.dropRemoteTts) return;
    flushThinking(true);
    const line = nativeProcessText(type, payload);
    if (line) showProcessLine(line);
    enterBusy();
  } else if (type === "agent.message") {
    if (store.dropRemoteTts) return;
    flushThinking(true);
    const t = (payload.content || payload.text || "").trim();
    if (t) appendAssistantChunk(t);
    enterBusy();
  } else if (type === "tts.start") {
    if (store.dropRemoteTts) return;
    clearProcessLine();
    store.ttsChunks = [];
    store.ttsPendingText = (payload.text || "").trim();
    if (
      !store.turnTtsSegments.length &&
      !store.ttsPlaying &&
      !store.ttsPlayQueue.length
    ) {
      store.lastTtsSegments = [];
      syncReplayHint();
    }
    enterSpeak();
  } else if (type === "tts.end") {
    if (store.dropRemoteTts) {
      store.ttsChunks = [];
      store.ttsPendingText = "";
      return;
    }
    if (store.ttsChunks.length) {
      const seg = { chunks: store.ttsChunks, text: store.ttsPendingText };
      store.ttsPlayQueue.push(seg);
      store.turnTtsSegments.push(seg);
      store.ttsChunks = [];
      store.ttsPendingText = "";
    }
    pump();
  } else if (type === "agent.error" || type === "error") {
    resetThinkingBuf();
    const detail = String(
      payload.detail || payload.content || payload.text || ""
    ).trim();
    if (detail) {
      store.activeAssistantId = null;
      setAssistantText(detail);
    }
    applyLocalCancel();
    enterErr();
  } else if (type === "agent.done" || type === "agent.cancel") {
    flushThinking(true);
    if (type === "agent.cancel") {
      if (store.dropRemoteTts) {
        stopTtsPlayback();
        return;
      }
      applyLocalCancel();
    } else {
      if (store.dropRemoteTts || store.recording) return;
      finishTypewriter();
      store.turnAwaitingIdle = true;
      maybeIdleAfterTurn(enterIdle, renderTranscript, clearProcessLine);
    }
  }
}

export function connect() {
  saveConnectionPrefs($("url").value, $("token").value);
  const url = $("url").value.trim();
  if (!url) return;
  setMood("connecting");
  store.turnLocked = true;
  syncControls();

  store.ws = new WebSocket(url);
  store.ws.binaryType = "arraybuffer";

  store.ws.onopen = () => {
    const payload = {
      device_id: stableDeviceId(),
      device_type: "web",
      protocol_version: "1.0",
    };
    const token = $("token").value;
    if (token) payload.token = token;
    store.ws.send(encodeMsg("device.hello", payload));
  };

  store.ws.onmessage = (ev) => {
    if (ev.data instanceof ArrayBuffer) {
      if (!store.dropRemoteTts) store.ttsChunks.push(new Uint8Array(ev.data));
      return;
    }
    let m;
    try {
      m = JSON.parse(ev.data);
    } catch (_) {
      return;
    }
    const p = m.payload || {};
    if (m.type === "session.accept") {
      store.sessionId = p.session_id;
      clearDropRemoteTts();
      if (p.pet_id) applyPetFromRuntime(p.pet_id);
      if (Array.isArray(p.messages)) {
        applyServerMessages(p.messages);
      }
      enterIdle();
      syncControls();
      store.ws.send(encodeMsg("pets.list"));
      return;
    }
    if (m.type === "session.reset.ok") {
      clearMessages();
      resetThinkingBuf();
      resetCaptionState();
      stopTtsPlayback();
      store.dropRemoteTts = false;
      store.turnTtsSegments = [];
      store.turnAwaitingIdle = false;
      store.lastTtsSegments = [];
      enterIdle();
      return;
    }
    if (m.type === "pets.list.result") {
      const applied = window.PixelBot.applyRemoteCatalog(p, $("url").value.trim());
      if (applied) {
        applyPetFromRuntime(p.default || applied.defaultId);
      }
      return;
    }
    if (m.type === "error") {
      const detail = String(p.detail || p.content || p.text || "").trim();
      if (detail) {
        store.activeAssistantId = null;
        setAssistantText(detail);
      }
      applyLocalCancel();
      enterErr();
      return;
    }
    onEvent(m.type, p);
  };

  store.ws.onclose = () => {
    store.sessionId = null;
    store.recording = false;
    store.turnLocked = true;
    setMood("offline");
    syncControls();
  };

  store.ws.onerror = () => enterErr();
}

export function resetConversation() {
  if (!store.ws || !store.sessionId || store.ws.readyState !== WebSocket.OPEN) return;
  if (store.recording) {
    stopTalk({ discard: true }).catch(() => {
      store.recording = false;
    });
  }
  if (store.turnLocked) {
    try {
      store.ws.send(encodeMsg("session.cancel", { session_id: store.sessionId }));
    } catch (_) {}
    applyLocalCancel();
  }
  clearMessages();
  resetThinkingBuf();
  resetCaptionState();
  try {
    store.ws.send(encodeMsg("session.reset", { session_id: store.sessionId }));
  } catch (_) {}
  enterIdle();
  syncReplayHint();
}
