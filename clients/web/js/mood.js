import { $ } from "./dom.js";
import { forEachBot } from "./pets.js";
import { store, runSyncUi } from "./store.js";

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
  runSyncUi();
}

export function restoreComposerPlaceholder() {
  const input = $("composerInput");
  if (input) input.placeholder = "有问题，随便问";
}

export function enterIdle() {
  store.turnLocked = false;
  store.recording = false;
  restoreComposerPlaceholder();
  setMood("idle");
}

export function enterBusy() {
  store.turnLocked = true;
  setMood("busy");
}

export function enterListen() {
  const input = $("composerInput");
  if (input) {
    input.value = "";
    input.placeholder = "正在听…";
  }
  setMood("listen");
}

export function enterSpeak() {
  store.turnLocked = true;
  setMood("speak");
}

export function enterErr() {
  store.turnLocked = false;
  store.recording = false;
  setMood("err");
}

export function syncControls() {
  const mood = $("stage").dataset.mood;
  const online = !!store.sessionId;
  const listening = mood === "listen";
  const canType =
    online &&
    !!store.ws &&
    store.ws.readyState === WebSocket.OPEN &&
    mood !== "offline" &&
    mood !== "connecting" &&
    mood !== "err";

  const input = $("composerInput");
  if (input) input.disabled = !canType;
  const send = $("composerSend");
  if (send) send.disabled = !canType;
  const attach = $("btnAttach");
  if (attach) attach.disabled = !canType;

  const mic = $("micBtn");
  if (mic) {
    mic.disabled = !store.sessionId || store.starting || store.stopping;
    mic.classList.toggle("listen", listening);
    mic.setAttribute("aria-label", listening ? "结束录音" : "语音输入");
    mic.title = listening ? "结束录音" : "语音";
  }
  const pet = $("btnComposerPet");
  if (pet) {
    pet.classList.toggle("listen", listening);
    pet.setAttribute(
      "aria-label",
      listening ? "结束录音" : "语音输入（长按打开设置）"
    );
    pet.title = listening ? "结束录音" : "点按录音，长按打开设置";
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
  const canReplay =
    !!store.sessionId &&
    !store.turnLocked &&
    !store.ttsPlaying &&
    !store.recording &&
    store.lastTtsSegments.length > 0 &&
    !!last;
  document.querySelectorAll(".bubble.assistant").forEach((el) => {
    const isLast = last && el.dataset.id === last.id;
    el.classList.toggle("replayable", !!(canReplay && isLast));
    el.title = canReplay && isLast ? "点击重播" : "";
  });
}
