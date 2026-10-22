import { $ } from "./dom.js";
import { forEachBot } from "./pets.js";
import { store, hooks, runSyncUi } from "./store.js";
import {
  syncStatusVisibility,
  scheduleFitPetWindow,
  isChromeCompact,
} from "./pet-chrome.js";

const MOOD_LABELS = {
  idle: "在线",
  listen: "听着…",
  busy: "思考中…",
  speak: "说话中…",
  connecting: "连接中…",
  offline: "未连接",
  err: "出错了",
};

export function setMood(mood) {
  $("stage").dataset.mood = mood;
  forEachBot((b) => b.setMood(mood));
  const statusLabel = $("statusLabel");
  if (statusLabel) statusLabel.textContent = MOOD_LABELS[mood] || mood;
  syncStatusVisibility(mood);
  void scheduleFitPetWindow({ immediate: true });
  runSyncUi();
  if (hooks.onMoodChanged) hooks.onMoodChanged(mood);
}
export function restoreComposerPlaceholder() {
  const input = $("composerInput");
  if (input && !store.pendingUserText) input.placeholder = "跟桌宠说…";
}

export function enterIdle() {
  store.turnLocked = false;
  store.agentRunning = false;
  store.recording = false;
  store.pendingUserText = "";
  store.bubbleTurnKey = "";
  const input = $("composerInput");
  if (input) {
    input.readOnly = false;
    input.value = "";
    input.placeholder = "跟桌宠说…";
  }
  setMood("idle");
}

export function enterBusy() {
  store.turnLocked = true;
  if (!store.bubbleTurnKey) {
    store.bubbleTurnKey = "t" + Date.now().toString(16);
  }
  setMood("busy");
}

export function enterListen() {
  store.agentRunning = false;
  store.pendingUserText = "";
  store.bubbleTurnKey = "";
  const input = $("composerInput");
  if (input) {
    input.readOnly = false;
    input.value = "";
    if (!$("composerForm")?.classList.contains("hold-talk")) {
      input.placeholder = "正在听…";
    }
  }
  setMood("listen");
}

export function enterSpeak() {
  store.turnLocked = true;
  setMood("speak");
}

export function enterErr() {
  store.turnLocked = false;
  store.agentRunning = false;
  store.recording = false;
  store.pendingUserText = "";
  store.bubbleTurnKey = "";
  const input = $("composerInput");
  if (input) {
    input.readOnly = false;
    input.value = "";
    input.placeholder = "跟桌宠说…";
  }
  setMood("err");
}

/** Clear the in-flight user text from composer (after agent finishes). */
export function clearPendingComposer() {
  store.pendingUserText = "";
  const input = $("composerInput");
  if (input) {
    input.value = "";
    if (!input.readOnly) input.placeholder = "跟桌宠说…";
  }
}

/** Sync composer: idle = mic|input|attach|send; agent run = stop(left) + status placeholder. */
export function syncControls() {
  const mood = $("stage").dataset.mood;
  const online = !!store.sessionId;
  const listening = mood === "listen";
  // Stop ONLY while agent is executing (cancel task).
  const canCancel = !!store.agentRunning && !!store.sessionId;
  const speaking =
    mood === "speak" ||
    !!store.ttsPlaying ||
    store.ttsPlayQueue.length > 0;
  // Lock edit controls while waiting/busy or agent running (speak stays typable for barge-in).
  const processing = canCancel || mood === "busy";
  const canType =
    online &&
    !!store.ws &&
    store.ws.readyState === WebSocket.OPEN &&
    !processing &&
    mood !== "offline" &&
    mood !== "connecting" &&
    mood !== "err" &&
    mood !== "listen";

  const form = $("composerForm");
  if (form) {
    form.classList.toggle("is-processing", processing);
    form.classList.toggle("is-listening", listening);
    form.classList.toggle("can-cancel", canCancel);
  }

  const input = $("composerInput");
  if (input) {
    if (processing) {
      // User text lives in the reply bubble — composer only shows status copy.
      input.readOnly = true;
      input.disabled = false;
      input.value = "";
      input.placeholder =
        canCancel || store.pendingUserText ? "助手处理中…" : "识别中…";
    } else if (listening) {
      // Recording: mic + status only — no attach/send.
      input.readOnly = true;
      input.disabled = false;
      input.value = "";
      input.placeholder = "正在听…";
    } else if (speaking) {
      // Same as idle: type + Enter interrupts playback and sends (like mic barge-in).
      input.readOnly = false;
      input.disabled = false;
      if (!String(input.value || "").trim()) {
        input.placeholder = "助手回复中…";
      }
    } else {
      input.readOnly = false;
      input.disabled = !canType;
      if (!String(input.value || "").trim()) {
        input.placeholder = "跟桌宠说…";
      }
    }
  }

  const attach = $("btnAttach");
  const mic = $("micBtn");
  const send = $("composerSend");
  const stop = $("btnStop");
  // Agent run / recording: drop attach + send — they don't apply.
  // Speak: keep attach/send so user can barge-in with text.
  if (attach) {
    attach.hidden = processing || listening;
    attach.disabled = !(canType || speaking);
  }
  if (mic) {
    mic.hidden = processing;
    mic.disabled =
      !store.sessionId ||
      store.starting ||
      store.stopping ||
      processing;
    mic.classList.toggle("listen", listening);
    mic.setAttribute("aria-label", listening ? "结束录音" : "语音输入");
    mic.title = listening ? "结束录音" : "语音";
  }
  if (send) {
    send.hidden = processing || listening;
    send.disabled = !(canType || speaking);
  }
  if (stop) {
    // Idle / listen / speak: never show stop — only while agent handles the turn.
    const showStop = canCancel;
    stop.hidden = !showStop;
    stop.disabled = !showStop;
    stop.setAttribute("aria-hidden", showStop ? "false" : "true");
  }

  const pet = $("btnComposerPet");
  if (pet) {
    pet.classList.toggle("listen", listening);
    const compact = isChromeCompact();
    const idleHint = compact
      ? "点按说话；右键恢复界面；拖动移动"
      : "点按说话；长按聚焦输入；右键只留人物；拖动移动";
    pet.setAttribute("aria-label", listening ? "结束录音" : idleHint);
    pet.title = listening ? "结束录音" : idleHint;
  }

  const chrome = $("btnChromeNew");
  if (chrome) {
    chrome.disabled = !(
      store.sessionId &&
      store.ws &&
      store.ws.readyState === WebSocket.OPEN
    );
  }

  syncReplayHint();
}

export function syncReplayHint() {
  const last = [...store.messages].reverse().find((m) => m.role === "assistant");
  const playing =
    !!store.ttsPlaying ||
    store.ttsPlayQueue.length > 0 ||
    document.getElementById("stage")?.dataset.mood === "speak";
  const canReplay =
    !!store.sessionId &&
    !store.turnLocked &&
    !playing &&
    !store.recording &&
    store.lastTtsSegments.length > 0 &&
    !!last;
  document.querySelectorAll(".bubble.assistant").forEach((el) => {
    const isLast = last && el.dataset.id === last.id;
    el.classList.toggle("replayable", !!(canReplay && isLast));
    el.title = canReplay && isLast ? "点击播报" : "";
  });

  let btn = document.getElementById("btnMsgTts");
  const wrap = last
    ? document.querySelector(`.bubble.assistant[data-id="${last.id}"]`)?.closest(".bubble-wrap")
    : null;
  const actions = wrap?.querySelector(".msg-actions");
  const showBtn =
    !!last &&
    !!actions &&
    (store.lastTtsSegments.length > 0 || playing);

  if (!showBtn) {
    if (btn) btn.remove();
    actions?.classList.remove("has-playing");
    return;
  }

  if (!btn && actions) {
    btn = document.createElement("button");
    btn.type = "button";
    btn.className = "msg-action msg-tts";
    btn.id = "btnMsgTts";
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (hooks.toggleLastTts) hooks.toggleLastTts();
      else if (hooks.replayLastTts) hooks.replayLastTts();
    });
    actions.appendChild(btn);
  }
  if (!btn) return;

  btn.classList.toggle("playing", playing);
  actions.classList.toggle("has-playing", playing);
  btn.title = playing ? "停止播报" : "播报";
  btn.setAttribute("aria-label", btn.title);
  btn.innerHTML = "";
  const paths = playing
    ? '<path d="M11 5L6 9H2v6h4l5 4V5z"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>'
    : '<path d="M11 5L6 9H2v6h4l5 4V5z"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/>';
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "ico ico-sm");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.innerHTML = paths;
  btn.appendChild(svg);
}
