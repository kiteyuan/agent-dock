import { $ } from "./dom.js";
import { AGENT, MSG, PROTOCOL_VERSION } from "./protocol.gen.js";
import { encodeMsg } from "./protocol.js";
import { stableDeviceId, saveConnectionPrefs } from "./prefs.js";
import { ensureHostAuth } from "./host-auth.js";
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
  clearPendingComposer,
  syncControls,
  syncReplayHint,
} from "./mood.js";
import {
  armDropRemoteTts,
  clearDropRemoteTts,
  stopTtsPlayback,
  pumpTts,
  replayLastTts,
  toggleLastTts,
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
  hooks.onMoodChanged = () => {
    renderTranscript();
  };
  hooks.replayLastTts = () => {
    replayLastTts();
    pump();
  };
  hooks.toggleLastTts = () => {
    toggleLastTts();
    pump();
  };
  store._pumpTts = pump;
}

function sendBinaryWav(wav) {
  const bytes = new Uint8Array(wav);
  store.ws.send(encodeMsg(MSG.AUDIO_START, { session_id: store.sessionId }));
  for (let i = 0; i < bytes.length; i += 4096) {
    store.ws.send(bytes.subarray(i, i + 4096));
  }
  store.ws.send(encodeMsg(MSG.AUDIO_END, { session_id: store.sessionId }));
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

  store.pendingUserText = "";
  enterBusy();
  store.ttsChunks = [];
  store.ttsPlayQueue = [];
  store.ttsPlaying = false;
  store.turnAwaitingIdle = false;
  store.turnTtsSegments = [];
  resetCaptionState();
  clearProcessLine();
  syncReplayHint();
  syncControls();
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
  store.agentRunning = false;
  store.pendingUserText = "";
  store.bubbleTurnKey = "";
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
    store.ws.send(encodeMsg(MSG.SESSION_CANCEL, { session_id: store.sessionId }));
  } catch (_) {}
  applyLocalCancel();
}

export async function sendUserMessage(raw) {
  const text = String(raw || "").trim();
  const pending = store.pendingAttach.slice();
  const previewUrls = pending.map((a) => a.url).filter(Boolean);
  if ((!text && !pending.length) || !store.ws || !store.sessionId) return;
  const mood = $("stage").dataset.mood;
  const speaking =
    mood === "speak" ||
    !!store.ttsPlaying ||
    store.ttsPlayQueue.length > 0;
  // Agent still running: stop-only. Speak/TTS can be barged-in like mic.
  if (store.agentRunning || (mood === "busy" && !speaking)) return;
  if (speaking || store.turnLocked) {
    try {
      store.ws.send(encodeMsg(MSG.SESSION_CANCEL, { session_id: store.sessionId }));
    } catch (_) {}
    armDropRemoteTts();
    stopTypewriter();
    resetCaptionState();
    store.turnLocked = false;
    store.agentRunning = false;
    store.turnAwaitingIdle = false;
    store.pendingUserText = "";
  }
  if (store.recording) {
    try {
      await stopTalk({ discard: true });
    } catch (_) {
      store.recording = false;
    }
  }
  armDropRemoteTts();
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
  store.pendingUserText = sendText;
  appendUserMessage(text || "", previewUrls);
  const input = $("composerInput");
  if (input) input.value = "";
  enterBusy();
  renderTranscript();
  syncControls();
  syncReplayHint();
  try {
    const payload = { session_id: store.sessionId, text: sendText };
    if (images.length) payload.images = images;
    store.ws.send(encodeMsg(MSG.USER_MESSAGE, payload));
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
  if (type === MSG.STT_FINAL) {
    clearDropRemoteTts();
    resetThinkingBuf();
    const t = String(payload.text || payload.content || "").trim();
    if (t) {
      store.pendingUserText = t;
      appendUserMessage(t);
    }
    enterBusy();
    renderTranscript();
    syncControls();
  } else if (type === AGENT.START) {
    clearDropRemoteTts();
    flushThinking(true);
    store.agentRunning = true;
    enterBusy();
    renderTranscript();
  } else if (type === AGENT.THINKING) {
    if (store.dropRemoteTts) return;
    store.agentRunning = true;
    const chunk = payload.content || payload.text || "";
    if (chunk) {
      store.thinkingBuf += String(chunk);
      flushThinking(false);
    }
    enterBusy();
  } else if (type === AGENT.TOOL_CALL || type === AGENT.TOOL_RESULT) {
    if (store.dropRemoteTts) return;
    store.agentRunning = true;
    flushThinking(true);
    const line = nativeProcessText(type, payload);
    if (line) showProcessLine(line);
    enterBusy();
  } else if (type === AGENT.MESSAGE) {
    if (store.dropRemoteTts) return;
    store.agentRunning = true;
    flushThinking(true);
    const t = (payload.content || payload.text || "").trim();
    if (t) appendAssistantChunk(t);
    enterBusy();
  } else if (type === MSG.TTS_START) {
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
  } else if (type === MSG.TTS_END) {
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
  } else if (type === AGENT.ERROR || type === MSG.ERROR) {
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
  } else if (type === AGENT.DONE || type === AGENT.CANCEL) {
    flushThinking(true);
    store.agentRunning = false;
    if (type === AGENT.CANCEL) {
      if (store.dropRemoteTts) {
        stopTtsPlayback();
        clearPendingComposer();
        syncControls();
        return;
      }
      applyLocalCancel();
    } else {
      if (store.dropRemoteTts || store.recording) return;
      finishTypewriter();
      clearPendingComposer();
      store.turnAwaitingIdle = true;
      renderTranscript();
      syncControls();
      maybeIdleAfterTurn(enterIdle, renderTranscript, clearProcessLine);
    }
  }
}

let _authRetry = false;

export function connect() {
  void connectAsync();
}

async function connectAsync() {
  await ensureHostAuth();
  await saveConnectionPrefs($("url").value, $("token").value);
  const url = $("url").value.trim();
  if (!url) return;
  setMood("connecting");
  store.turnLocked = true;
  syncControls();

  if (store.ws) {
    try {
      store.ws.onclose = null;
      store.ws.close();
    } catch (_) {}
    store.ws = null;
  }

  store.ws = new WebSocket(url);
  store.ws.binaryType = "arraybuffer";

  store.ws.onopen = () => {
    const payload = {
      device_id: stableDeviceId(),
      device_type: "desktop",
      protocol_version: PROTOCOL_VERSION,
    };
    const token = ($("token").value || "").trim();
    if (token) payload.token = token;
    store.ws.send(encodeMsg(MSG.DEVICE_HELLO, payload));
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
    if (m.type === MSG.SESSION_ACCEPT) {
      store.sessionId = p.session_id;
      clearDropRemoteTts();
      if (p.pet_id) applyPetFromRuntime(p.pet_id);
      if (Array.isArray(p.messages)) {
        applyServerMessages(p.messages);
      }
      enterIdle();
      syncControls();
      store.ws.send(encodeMsg(MSG.PETS_LIST));
      return;
    }
    if (m.type === MSG.SESSION_RESET_OK) {
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
    if (m.type === MSG.PETS_LIST_RESULT) {
      const applied = window.PixelBot.applyRemoteCatalog(p, $("url").value.trim());
      if (applied) {
        applyPetFromRuntime(p.default || applied.defaultId);
      }
      return;
    }
    if (m.type === MSG.ERROR) {
      const detail = String(p.detail || p.content || p.text || p.message || "").trim();
      const authFail = /token|auth|unauthor/i.test(detail);
      if (authFail && !_authRetry) {
        _authRetry = true;
        // Silent re-read host token — never open a config dialog.
        $("token").value = "";
        try {
          store.ws?.close();
        } catch (_) {}
        setTimeout(() => {
          connect();
          setTimeout(() => {
            _authRetry = false;
          }, 4000);
        }, 200);
        return;
      }
      // Host pet: keep auth noise out of the bubble.
      if (!authFail && detail) {
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
      store.ws.send(encodeMsg(MSG.SESSION_CANCEL, { session_id: store.sessionId }));
    } catch (_) {}
    applyLocalCancel();
  }
  clearMessages();
  resetThinkingBuf();
  resetCaptionState();
  try {
    store.ws.send(encodeMsg(MSG.SESSION_RESET, { session_id: store.sessionId }));
  } catch (_) {}
  enterIdle();
  syncReplayHint();
}
