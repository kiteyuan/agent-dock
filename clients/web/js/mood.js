import { $ } from "./dom.js";
import { forEachBot } from "./pets.js";
import { store, hooks, runSyncUi } from "./store.js";

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
  if (input) input.placeholder = "发消息或按住说话";
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
