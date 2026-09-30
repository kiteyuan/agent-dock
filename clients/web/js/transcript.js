import { $ } from "./dom.js";
import { PREFS } from "./prefs.js";
import { store, LIMITS, hooks } from "./store.js";
import { normalizeReply, renderMarkdown, captionSep, clipProcess } from "./text.js";
import { syncReplayHint } from "./mood.js";

function nextMsgId() {
  return "m" + Math.random().toString(16).slice(2, 10) + Date.now().toString(16).slice(-3);
}

function iconSvg(name, extraClass = "") {
  const paths = {
    copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M8 16H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v2"/>',
    volume: '<path d="M11 5L6 9H2v6h4l5 4V5z"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/>',
    volumePlaying:
      '<path d="M11 5L6 9H2v6h4l5 4V5z"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>',
    close: '<path d="M6 6l12 12M18 6L6 18"/>',
  };
  const d = paths[name] || "";
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", `ico ${extraClass}`.trim());
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.innerHTML = d;
  return svg;
}

function isTtsActive() {
  return !!(
    store.ttsPlaying ||
    store.ttsPlayQueue.length ||
    document.getElementById("stage")?.dataset.mood === "speak"
  );
}

export function persistMessages() {
  try {
    const slim = store.messages.slice(-LIMITS.msg).map((m) => ({
      id: m.id,
      role: m.role,
      text: m.text,
    }));
    localStorage.setItem(PREFS.messages, JSON.stringify(slim));
  } catch (_) {}
}

export function loadMessages() {
  try {
    const raw = localStorage.getItem(PREFS.messages);
    if (!raw) return;
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return;
    store.messages = parsed
      .filter((m) => m && (m.role === "user" || m.role === "assistant") && typeof m.text === "string")
      .slice(-LIMITS.msg)
      .map((m) => ({
        id: m.id || nextMsgId(),
        role: m.role,
        text: m.text,
      }));
  } catch (_) {}
}

/** Replace local transcript with completed history from Runtime ``session.accept``. */
export function applyServerMessages(messages) {
  if (!Array.isArray(messages)) return;
  store.messages = messages
    .filter((m) => m && (m.role === "user" || m.role === "assistant") && typeof m.text === "string")
    .slice(-LIMITS.msg)
    .map((m) => ({
      id: m.id || nextMsgId(),
      role: m.role,
      text: String(m.text),
    }));
  store.activeAssistantId = null;
  persistMessages();
  renderTranscript();
  scrollTranscript({ force: true });
}

export function scrollTranscript({ force = false } = {}) {
  const box = $("transcript");
  if (!box) return;
  requestAnimationFrame(() => {
    if (!force && !isTranscriptNearBottom(box)) return;
    box.scrollTop = box.scrollHeight;
  });
}

export function isTranscriptNearBottom(box = $("transcript"), threshold = 80) {
  if (!box) return true;
  return box.scrollHeight - box.scrollTop - box.clientHeight < threshold;
}

export function clearProcessLine() {
  if (!store.processLineText) return;
  store.processLineText = "";
  const el = $("processLine");
  if (el) {
    const wrap = el.closest(".bubble-wrap");
    if (wrap) wrap.remove();
    else el.remove();
  }
}

export function showProcessLine(line) {
  if (store.assistantTurnText) return;
  const s = clipProcess(line, LIMITS.processMaxLen);
  if (!s) return;
  store.processLineText = s;
  const el = $("processLine");
  if (el) {
    el.textContent = s;
    scrollTranscript();
    return;
  }
  renderTranscript();
}

export function renderTranscript() {
  const box = $("transcript");
  if (!box) return;
  const stickBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 48;
  box.innerHTML = "";
  let lastAssistantId = null;
  for (let i = store.messages.length - 1; i >= 0; i--) {
    if (store.messages[i].role === "assistant") {
      lastAssistantId = store.messages[i].id;
      break;
    }
  }
  for (const m of store.messages) {
    const wrap = document.createElement("div");
    wrap.className = "bubble-wrap";
    wrap.style.display = "flex";
    wrap.style.flexDirection = "column";
    wrap.style.alignItems = m.role === "user" ? "flex-end" : "flex-start";
    wrap.style.width = "100%";

    const el = document.createElement("div");
    el.className = `bubble ${m.role}`;
    el.dataset.id = m.id;
    if (m.images && m.images.length) {
      const imgs = document.createElement("div");
      imgs.className = "bubble-images";
      for (const src of m.images) {
        const img = document.createElement("img");
        img.src = src;
        img.alt = "附件";
        imgs.appendChild(img);
      }
      el.appendChild(imgs);
    }
    if (m.text) {
      const textNode = document.createElement("div");
      textNode.className = m.role === "assistant" ? "md-body" : "";
      if (m.role === "assistant") {
        textNode.innerHTML = renderMarkdown(m.text);
      } else {
        textNode.textContent = m.text;
      }
      el.appendChild(textNode);
    } else if (!(m.images && m.images.length)) {
      el.textContent = "";
    }
    if (m.id === store.activeAssistantId && $("stage").dataset.mood === "busy") {
      el.classList.add("streaming");
      const caret = document.createElement("span");
      caret.className = "caret";
      el.appendChild(caret);
    }
    wrap.appendChild(el);

    if (m.role === "assistant" && m.text.trim()) {
      const actions = document.createElement("div");
      actions.className = "msg-actions";
      const copy = document.createElement("button");
      copy.type = "button";
      copy.className = "msg-action";
      copy.title = "复制";
      copy.appendChild(iconSvg("copy", "ico-sm"));
      copy.addEventListener("click", (e) => {
        e.stopPropagation();
        navigator.clipboard?.writeText(m.text).catch(() => {});
      });
      actions.appendChild(copy);
      const canSpeakBtn =
        m.id === lastAssistantId &&
        (store.lastTtsSegments.length > 0 || isTtsActive());
      if (canSpeakBtn) {
        const playing = isTtsActive();
        const speak = document.createElement("button");
        speak.type = "button";
        speak.className = "msg-action msg-tts" + (playing ? " playing" : "");
        speak.id = "btnMsgTts";
        speak.title = playing ? "停止播报" : "播报";
        speak.setAttribute("aria-label", speak.title);
        speak.appendChild(iconSvg(playing ? "volumePlaying" : "volume", "ico-sm"));
        speak.addEventListener("click", (e) => {
          e.stopPropagation();
          if (hooks.toggleLastTts) hooks.toggleLastTts();
        });
        actions.appendChild(speak);
        if (playing) actions.classList.add("has-playing");
      }
      wrap.appendChild(actions);
    }

    box.appendChild(wrap);
  }
  if (store.processLineText) {
    const procWrap = document.createElement("div");
    procWrap.className = "bubble-wrap";
    procWrap.style.display = "flex";
    procWrap.style.flexDirection = "column";
    procWrap.style.alignItems = "flex-start";
    procWrap.style.width = "100%";
    const proc = document.createElement("p");
    proc.id = "processLine";
    proc.className = "process-line";
    proc.textContent = store.processLineText;
    procWrap.appendChild(proc);
    box.appendChild(procWrap);
  }
  if (stickBottom || !store.messages.length) scrollTranscript({ force: stickBottom || !store.messages.length });
  syncReplayHint();
}

function updateBubbleDom(id, text, { typing = false } = {}) {
  let el = $("transcript").querySelector(`.bubble[data-id="${id}"]`);
  if (!el) {
    renderTranscript();
    el = $("transcript").querySelector(`.bubble[data-id="${id}"]`);
  }
  if (!el) return;
  const isAssistant = el.classList.contains("assistant");
  el.innerHTML = "";
  const body = document.createElement("div");
  if (isAssistant) {
    body.className = "md-body";
    body.innerHTML = renderMarkdown(text);
  } else {
    body.textContent = text;
  }
  el.appendChild(body);
  if (typing) {
    el.classList.add("streaming");
    const caret = document.createElement("span");
    caret.className = "caret";
    el.appendChild(caret);
  } else {
    el.classList.remove("streaming");
  }
  scrollTranscript();
  syncReplayHint();
}

export function stopTypewriter({ snap = false } = {}) {
  store.typeToken += 1;
  if (store.typeTimer) {
    clearInterval(store.typeTimer);
    store.typeTimer = null;
  }
  if (snap && store.activeAssistantId && store.assistantTurnText) {
    const msg = store.messages.find((m) => m.id === store.activeAssistantId);
    if (msg) {
      msg.text = store.assistantTurnText;
      persistMessages();
      updateBubbleDom(msg.id, msg.text, { typing: false });
    }
  }
}

function typeIntervalMs(behind) {
  if (behind > 60) return 10;
  if (behind > 24) return 16;
  return 22;
}

function charsThisTick(behind) {
  if (behind > 48) return 3;
  if (behind > 18) return 2;
  return 1;
}

function ensureTypewriterRunning() {
  if (store.typeTimer) return;
  const my = ++store.typeToken;
  const tick = () => {
    if (my !== store.typeToken) return;
    const id = store.activeAssistantId;
    const target = store.assistantTurnText;
    if (!id || !target) {
      stopTypewriter();
      return;
    }
    const msg = store.messages.find((m) => m.id === id);
    if (!msg) {
      stopTypewriter();
      return;
    }
    const cur = msg.text || "";
    if (cur.length >= target.length) {
      stopTypewriter();
      updateBubbleDom(id, target, { typing: false });
      return;
    }
    const behind = target.length - cur.length;
    const n = charsThisTick(behind);
    msg.text = target.slice(0, cur.length + n);
    updateBubbleDom(id, msg.text, { typing: true });
    // Retune interval when backlog changes a lot.
    if (store.typeTimer) {
      clearInterval(store.typeTimer);
      store.typeTimer = setInterval(tick, typeIntervalMs(behind - n));
    }
  };
  store.typeTimer = setInterval(tick, typeIntervalMs(store.assistantTurnText.length));
  tick();
}

export function clearMessages() {
  stopTypewriter();
  store.messages = [];
  store.activeAssistantId = null;
  store.assistantTurnText = "";
  persistMessages();
  renderTranscript();
  clearProcessLine();
}

export function appendUserMessage(text, images = []) {
  const t = String(text || "").trim();
  const imgs = Array.isArray(images) ? images.filter(Boolean) : [];
  if (!t && !imgs.length) return;
  stopTypewriter();
  store.activeAssistantId = null;
  store.messages.push({ id: nextMsgId(), role: "user", text: t, images: imgs });
  if (store.messages.length > LIMITS.msg) {
    store.messages = store.messages.slice(-LIMITS.msg);
  }
  persistMessages();
  renderTranscript();
  scrollTranscript({ force: true });
}

function ensureAssistantBubble() {
  if (store.activeAssistantId) {
    const existing = store.messages.find((m) => m.id === store.activeAssistantId);
    if (existing) return existing;
  }
  const id = nextMsgId();
  store.activeAssistantId = id;
  store.messages.push({ id, role: "assistant", text: "" });
  if (store.messages.length > LIMITS.msg) {
    store.messages = store.messages.slice(-LIMITS.msg);
  }
  persistMessages();
  renderTranscript();
  return store.messages.find((m) => m.id === id);
}

/** Immediate set (errors / local notices) — skips typewriter. */
export function setAssistantText(text) {
  stopTypewriter();
  const msg = ensureAssistantBubble();
  msg.text = normalizeReply(text);
  persistMessages();
  updateBubbleDom(msg.id, msg.text, { typing: false });
}

export function appendAssistantChunk(text) {
  const t = String(text || "").replace(/\r\n/g, "\n");
  if (!t.trim()) return;
  const sep = store.assistantTurnText
    ? captionSep(store.assistantTurnText, t)
    : "";
  const join = sep && t.startsWith("\n") ? "" : sep;
  store.assistantTurnText = store.assistantTurnText + join + t;
  ensureAssistantBubble();
  clearProcessLine();
  ensureTypewriterRunning();
}

export function resetCaptionState() {
  stopTypewriter();
  store.assistantTurnText = "";
  store.ttsPendingText = "";
}

/** Finish remaining typed chars at once (agent.done). */
export function finishTypewriter() {
  stopTypewriter({ snap: true });
}

export function resetThinkingBuf() {
  store.thinkingBuf = "";
  store.lastThinkingFlush = 0;
}

export function flushThinking(final = false) {
  const now = Date.now();
  if (!store.thinkingBuf) {
    if (final) resetThinkingBuf();
    return;
  }
  if (
    !final &&
    store.lastThinkingFlush &&
    now - store.lastThinkingFlush < LIMITS.thinkingMinMs
  ) {
    return;
  }
  const shown = clipProcess(store.thinkingBuf, LIMITS.processMaxLen);
  if (!shown) {
    if (final) resetThinkingBuf();
    return;
  }
  showProcessLine(shown);
  store.lastThinkingFlush = now;
  if (final) resetThinkingBuf();
}

export function renderAttachPreview() {
  const box = $("attachPreview");
  const bar = $("composerForm");
  if (!box) return;
  box.innerHTML = "";
  const has = store.pendingAttach.length > 0;
  if (!has) {
    box.hidden = true;
    bar?.classList.remove("has-attach");
    document.querySelector(".main")?.classList.remove("has-attach");
    return;
  }
  box.hidden = false;
  bar?.classList.add("has-attach");
  document.querySelector(".main")?.classList.add("has-attach");
  for (const item of store.pendingAttach) {
    const chip = document.createElement("div");
    chip.className = "attach-chip";
    const img = document.createElement("img");
    img.src = item.url;
    img.alt = "";
    const rm = document.createElement("button");
    rm.type = "button";
    rm.className = "attach-chip-remove";
    rm.setAttribute("aria-label", "移除");
    rm.appendChild(iconSvg("close"));
    rm.addEventListener("click", () => removeAttachment(item.id));
    chip.appendChild(img);
    chip.appendChild(rm);
    box.appendChild(chip);
  }
}

export function removeAttachment(id) {
  const idx = store.pendingAttach.findIndex((a) => a.id === id);
  if (idx < 0) return;
  const [item] = store.pendingAttach.splice(idx, 1);
  try {
    URL.revokeObjectURL(item.url);
  } catch (_) {}
  renderAttachPreview();
}

export function clearPendingAttach({ revoke = true } = {}) {
  if (revoke) {
    for (const item of store.pendingAttach) {
      try {
        URL.revokeObjectURL(item.url);
      } catch (_) {}
    }
  }
  store.pendingAttach = [];
  renderAttachPreview();
}

export function addAttachmentsFromFiles(fileList) {
  const files = [...(fileList || [])].filter((f) => f && f.type.startsWith("image/"));
  for (const file of files) {
    if (store.pendingAttach.length >= LIMITS.attach) break;
    store.pendingAttach.push({
      id: nextMsgId(),
      url: URL.createObjectURL(file),
      name: file.name || "image",
      file,
    });
  }
  renderAttachPreview();
}
