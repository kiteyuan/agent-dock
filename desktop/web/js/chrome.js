import { $ } from "./dom.js";
import { store, hooks } from "./store.js";
import {
  addAttachmentsFromFiles,
  setBubbleConfirm,
  clearBubbleConfirm,
} from "./transcript.js";
import {
  connect,
  toggleTalk,
  startTalk,
  stopTalk,
  sendUserMessage,
  resetConversation,
  cancelTurn,
} from "./session.js";
import {
  openAdminPanel,
  getPetWindowPos,
  setPetWindowPos,
  startWindowDrag,
  shutdownHost,
} from "./tauri.js";
import { focusComposer, toggleChromeCompact, suspendPetHitThrough } from "./pet-chrome.js";

const PET_LONG_PRESS_MS = 550;
const PET_DRAG_PX = 6;
const HOLD_TALK_MS = 380;
const HOLD_CANCEL_PX = 56;
const PLACEHOLDER_IDLE = "跟桌宠说…";

function sessionReady() {
  return !!(
    store.sessionId &&
    store.ws &&
    store.ws.readyState === WebSocket.OPEN
  );
}

function syncSessionActions() {
  const ready = sessionReady();
  for (const id of ["btnChromeNew", "btnFlankNew"]) {
    const el = $(id);
    if (el) el.disabled = !ready;
  }
  // Full host stop is always available on Tauri; browser fallback keeps it enabled too
  // so the confirm can explain the limitation.
  for (const id of ["btnChromeStopSvc", "btnFlankStopSvc"]) {
    const el = $(id);
    if (el) el.disabled = false;
  }
}

export function openSettings() {
  clearBubbleConfirm();
  $("settings").showModal();
}

function openNewSessionConfirm() {
  if (!sessionReady()) return;
  if ($("settings")?.open) $("settings").close();
  setBubbleConfirm({
    kind: "new-session",
    title: "新开会话？",
    hint: "清空本设备的 Agent 对话记忆与本地气泡。连接不用重连。",
    okLabel: "新开",
  });
}

function openShutdownConfirm() {
  if ($("settings")?.open) $("settings").close();
  setBubbleConfirm({
    kind: "shutdown",
    title: "关闭服务？",
    hint: "停止 Agent / 引擎，关闭 Runtime，并退出桌宠（等同 stop）。",
    okLabel: "关闭服务",
    danger: true,
  });
}

async function confirmBubbleAction() {
  const kind = store.bubbleConfirm?.kind;
  if (!kind) return;
  const okBtn = $("btnBubbleConfirmOk");
  const cancelBtn = $("btnBubbleConfirmCancel");
  if (okBtn) okBtn.disabled = true;
  if (cancelBtn) cancelBtn.disabled = true;
  try {
    if (kind === "new-session") {
      clearBubbleConfirm();
      resetConversation();
      return;
    }
    if (kind === "shutdown") {
      await shutdownHost();
      // Process should exit; if invoke returns, shutdown did not take the process down.
      clearBubbleConfirm();
    }
  } catch (err) {
    console.warn("bubble confirm failed", err);
    setBubbleConfirm({
      kind: "dismiss",
      title: "关闭失败",
      hint: err instanceof Error ? err.message : "请改用 scripts/stop.ps1",
      okLabel: "知道了",
      danger: true,
    });
  } finally {
    if (okBtn) okBtn.disabled = false;
    if (cancelBtn) cancelBtn.disabled = false;
    syncSessionActions();
  }
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
  let dragging = false;
  let startX = 0;
  let startY = 0;
  let originScreenX = 0;
  let originScreenY = 0;
  let originWinX = 0;
  let originWinY = 0;
  let dragPointerId = null;
  let useManual = true;
  let raf = 0;
  let latestScreenX = 0;
  let latestScreenY = 0;

  const clearLong = () => {
    if (longTimer) {
      clearTimeout(longTimer);
      longTimer = null;
    }
  };

  const endManualDrag = (e) => {
    if (raf) {
      cancelAnimationFrame(raf);
      raf = 0;
    }
    if (dragPointerId != null && e?.pointerId === dragPointerId) {
      try {
        pet.releasePointerCapture(dragPointerId);
      } catch (_) {}
    }
    dragPointerId = null;
    window.removeEventListener("pointermove", onDragMove);
    window.removeEventListener("pointerup", onDragUp);
    window.removeEventListener("pointercancel", onDragUp);
    suspendPetHitThrough(false);
  };

  const flushPos = () => {
    raf = 0;
    if (!dragging || !useManual) return;
    // Chromium screenX/Y are CSS px (same space as Tauri LogicalPosition).
    const x = originWinX + (latestScreenX - originScreenX);
    const y = originWinY + (latestScreenY - originScreenY);
    // Do not await — overlapping awaits made drag feel stuck.
    void setPetWindowPos(x, y);
  };

  const onDragMove = (e) => {
    if (!dragging || (dragPointerId != null && e.pointerId !== dragPointerId)) return;
    if (!useManual) return;
    latestScreenX = e.screenX;
    latestScreenY = e.screenY;
    if (!raf) raf = requestAnimationFrame(flushPos);
  };

  const onDragUp = (e) => {
    if (dragging && useManual) {
      latestScreenX = e.screenX;
      latestScreenY = e.screenY;
      flushPos();
    }
    endManualDrag(e);
  };

  pet.addEventListener("pointerdown", (e) => {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    longFired = false;
    dragging = false;
    startX = e.clientX;
    startY = e.clientY;
    originScreenX = e.screenX;
    originScreenY = e.screenY;
    latestScreenX = e.screenX;
    latestScreenY = e.screenY;
    dragPointerId = e.pointerId;
    clearLong();
    longTimer = setTimeout(() => {
      longTimer = null;
      if (dragging) return;
      longFired = true;
      focusComposer();
    }, PET_LONG_PRESS_MS);
  });

  pet.addEventListener("pointermove", (e) => {
    if (dragging || longFired) return;
    if (e.buttons === 0 && e.pointerType === "mouse") return;
    const dx = e.clientX - startX;
    const dy = e.clientY - startY;
    if (dx * dx + dy * dy < PET_DRAG_PX * PET_DRAG_PX) return;
    clearLong();
    dragging = true;
    suspendPetHitThrough(true);
    originScreenX = e.screenX;
    originScreenY = e.screenY;
    latestScreenX = e.screenX;
    latestScreenY = e.screenY;
    void (async () => {
      const pos = await getPetWindowPos();
      if (!pos) {
        useManual = false;
        void startWindowDrag();
        return;
      }
      useManual = true;
      originWinX = pos.x;
      originWinY = pos.y;
      // Re-anchor to current pointer so the await latency doesn't jump.
      originScreenX = e.screenX;
      originScreenY = e.screenY;
      latestScreenX = e.screenX;
      latestScreenY = e.screenY;
      try {
        pet.setPointerCapture(e.pointerId);
      } catch (_) {}
      window.addEventListener("pointermove", onDragMove);
      window.addEventListener("pointerup", onDragUp);
      window.addEventListener("pointercancel", onDragUp);
    })();
  });

  pet.addEventListener("pointerup", (e) => {
    clearLong();
    if (!dragging) endManualDrag(e);
  });
  pet.addEventListener("pointercancel", (e) => {
    clearLong();
    endManualDrag(e);
  });
  pet.addEventListener("click", (e) => {
    e.preventDefault();
    if (dragging) {
      dragging = false;
      return;
    }
    if (longFired) {
      longFired = false;
      return;
    }
    startOrToggleMic();
    pet.blur();
  });
  pet.addEventListener("contextmenu", (e) => {
    e.preventDefault();
    clearLong();
    longFired = true;
    toggleChromeCompact();
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
    !holding &&
    !store.bubbleConfirm;

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
    $("settings").close();
  };
  $("btnOpenAdmin")?.addEventListener("click", (e) => {
    e.preventDefault();
    void openAdminPanel();
  });
  $("btnFlankConsole")?.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    void openAdminPanel();
  });
  for (const id of ["btnChromeNew", "btnFlankNew"]) {
    $(id)?.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      openNewSessionConfirm();
    });
  }
  for (const id of ["btnChromeStopSvc", "btnFlankStopSvc"]) {
    $(id)?.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      openShutdownConfirm();
    });
  }

  $("btnBubbleConfirmCancel")?.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    clearBubbleConfirm();
  });
  $("btnBubbleConfirmOk")?.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (store.bubbleConfirm?.kind === "dismiss") {
      clearBubbleConfirm();
      return;
    }
    void confirmBubbleAction();
  });

  $("btnSave").onclick = (e) => {
    e.preventDefault();
    $("settings").close();
    if (store.ws) store.ws.close();
    connect();
  };

  bindPetGestures();
  bindHoldToTalk();
  syncSessionActions();

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

  $("btnStop")?.addEventListener("click", (e) => {
    e.preventDefault();
    cancelTurn();
  });

  $("btnBubbleMute")?.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (hooks.toggleLastTts) hooks.toggleLastTts();
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
    if (store.bubbleConfirm) return;
    sendUserMessage($("composerInput").value);
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && store.bubbleConfirm) {
      e.preventDefault();
      clearBubbleConfirm();
      return;
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      focusComposer();
    }
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === ",") {
      e.preventDefault();
      openSettings();
    }
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === "a") {
      e.preventDefault();
      void openAdminPanel();
    }
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
