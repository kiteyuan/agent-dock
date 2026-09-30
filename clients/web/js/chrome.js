import { $ } from "./dom.js";
import { store, hooks } from "./store.js";
import { addAttachmentsFromFiles } from "./transcript.js";
import {
  connect,
  toggleTalk,
  startTalk,
  stopTalk,
  sendUserMessage,
  resetConversation,
} from "./session.js";

const PET_LONG_PRESS_MS = 550;
const HOLD_TALK_MS = 380;
const HOLD_CANCEL_PX = 56;
const PLACEHOLDER_IDLE = "发消息或按住说话";

function showSettingsMain() {
  $("settingsMain").hidden = false;
  $("settingsResetConfirm").hidden = true;
}

function showSettingsResetConfirm() {
  $("settingsMain").hidden = true;
  $("settingsResetConfirm").hidden = false;
}

function syncNewSessionButton() {
  const chrome = $("btnChromeNew");
  if (!chrome) return;
  chrome.disabled = !(
    store.sessionId &&
    store.ws &&
    store.ws.readyState === WebSocket.OPEN
  );
}

export function openSettings() {
  showSettingsMain();
  syncNewSessionButton();
  $("settings").showModal();
}

function openNewSessionConfirm() {
  if (!store.sessionId || !store.ws || store.ws.readyState !== WebSocket.OPEN) return;
  showSettingsResetConfirm();
  if (!$("settings").open) $("settings").showModal();
}

function startOrToggleMic() {
  if (!store.sessionId) return;
  toggleTalk().catch(() => {
    store.recording = false;
    store.starting = false;
    store.stopping = false;
  });
}

function bindPetGestures() {
  const pet = $("btnComposerPet");
  if (!pet) return;
  let longTimer = null;
  let longFired = false;

  const clearLong = () => {
    if (longTimer) {
      clearTimeout(longTimer);
      longTimer = null;
    }
  };

  pet.addEventListener("pointerdown", (e) => {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    longFired = false;
    clearLong();
    longTimer = setTimeout(() => {
      longTimer = null;
      longFired = true;
      openSettings();
    }, PET_LONG_PRESS_MS);
  });
  pet.addEventListener("pointerup", clearLong);
  pet.addEventListener("pointerleave", clearLong);
  pet.addEventListener("pointercancel", clearLong);
  pet.addEventListener("click", (e) => {
    e.preventDefault();
    if (longFired) {
      longFired = false;
      return;
    }
    startOrToggleMic();
  });
  pet.addEventListener("contextmenu", (e) => {
    e.preventDefault();
    clearLong();
    longFired = true;
    openSettings();
  });
}

function setHoldUi(active, willCancel) {
  const bar = $("composerForm");
  const input = $("composerInput");
  if (bar) {
    bar.classList.toggle("hold-talk", !!active);
    bar.classList.toggle("hold-cancel", !!(active && willCancel));
  }
  if (!input) return;
  if (!active) {
    if (!store.recording && $("stage")?.dataset.mood !== "listen") {
      input.placeholder = PLACEHOLDER_IDLE;
    }
    return;
  }
  input.placeholder = willCancel ? "松开取消" : "松开发送，上移取消";
}

function bindHoldToTalk() {
  const input = $("composerInput");
  if (!input) return;

  let timer = null;
  let holding = false;
  let willCancel = false;
  let startY = 0;
  let pointerId = null;

  const clearTimer = () => {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
  };

  const canBeginHold = () =>
    !!store.sessionId &&
    !!store.ws &&
    store.ws.readyState === WebSocket.OPEN &&
    !store.recording &&
    !store.starting &&
    !store.stopping &&
    !holding;

  const finishHold = async (cancel) => {
    if (!holding) return;
    holding = false;
    willCancel = false;
    pointerId = null;
    setHoldUi(false, false);
    try {
      await stopTalk({ discard: cancel });
    } catch (_) {
      store.recording = false;
      store.stopping = false;
    }
  };

  const onMove = (e) => {
    if (!holding || e.pointerId !== pointerId) return;
    const cancel = startY - e.clientY >= HOLD_CANCEL_PX;
    if (cancel !== willCancel) {
      willCancel = cancel;
      setHoldUi(true, willCancel);
    }
  };

  const onUp = (e) => {
    if (pointerId != null && e.pointerId !== pointerId) return;
    clearTimer();
    try {
      if (pointerId != null) input.releasePointerCapture(pointerId);
    } catch (_) {}
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", onUp);
    window.removeEventListener("pointercancel", onUp);
    if (holding) {
      e.preventDefault();
      finishHold(willCancel);
    }
    pointerId = null;
  };

  input.addEventListener("pointerdown", (e) => {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    // Keep normal text selection when input already has content (mouse).
    if (e.pointerType === "mouse" && input.value.trim()) return;
    if (!canBeginHold()) return;
    clearTimer();
    startY = e.clientY;
    pointerId = e.pointerId;
    willCancel = false;
    timer = setTimeout(async () => {
      timer = null;
      if (pointerId == null) return;
      if (
        !store.sessionId ||
        !store.ws ||
        store.ws.readyState !== WebSocket.OPEN ||
        store.recording ||
        store.starting ||
        store.stopping
      ) {
        return;
      }
      holding = true;
      try {
        input.setPointerCapture(pointerId);
      } catch (_) {}
      input.blur();
      setHoldUi(true, false);
      try {
        await startTalk();
        if (holding) setHoldUi(true, willCancel);
      } catch (_) {
        holding = false;
        setHoldUi(false, false);
      }
    }, HOLD_TALK_MS);
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
  });

  input.addEventListener("contextmenu", (e) => {
    if (holding || timer) e.preventDefault();
  });
}

export function bindChrome() {
  $("btnClose").onclick = () => {
    showSettingsMain();
    $("settings").close();
  };
  $("btnChromeNew").onclick = (e) => {
    e.preventDefault();
    openNewSessionConfirm();
  };
  $("btnResetCancel").onclick = (e) => {
    e.preventDefault();
    showSettingsMain();
  };
  $("btnResetConfirm").onclick = (e) => {
    e.preventDefault();
    showSettingsMain();
    $("settings").close();
    resetConversation();
  };
  $("btnSave").onclick = (e) => {
    e.preventDefault();
    showSettingsMain();
    $("settings").close();
    if (store.ws) store.ws.close();
    connect();
  };
  $("settings").addEventListener("close", showSettingsMain);

  bindPetGestures();
  bindHoldToTalk();

  $("btnAttach").onclick = () => {
    if ($("btnAttach").disabled) return;
    $("attachInput").click();
  };
  $("attachInput").addEventListener("change", (e) => {
    addAttachmentsFromFiles(e.target.files);
    e.target.value = "";
  });

  $("micBtn").addEventListener("click", (e) => {
    e.preventDefault();
    startOrToggleMic();
  });

  $("transcript").addEventListener("click", (e) => {
    if (e.target.closest(".msg-action")) return;
    const bubble = e.target.closest(".bubble.assistant.replayable");
    if (!bubble) return;
    e.preventDefault();
    if (hooks.toggleLastTts) hooks.toggleLastTts();
    else if (hooks.replayLastTts) hooks.replayLastTts();
  });

  $("composerForm").addEventListener("submit", (e) => {
    e.preventDefault();
    sendUserMessage($("composerInput").value);
  });

  $("composerInput").addEventListener("paste", (e) => {
    const items = e.clipboardData && e.clipboardData.items;
    if (!items) return;
    const files = [];
    for (const item of items) {
      if (item.type && item.type.startsWith("image/")) {
        const f = item.getAsFile();
        if (f) files.push(f);
      }
    }
    if (files.length) {
      e.preventDefault();
      addAttachmentsFromFiles(files);
    }
  });
}
