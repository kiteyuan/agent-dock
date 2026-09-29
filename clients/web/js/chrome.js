import { $ } from "./dom.js";
import { store, hooks } from "./store.js";
import { addAttachmentsFromFiles } from "./transcript.js";
import {
  connect,
  toggleTalk,
  sendUserMessage,
  resetConversation,
} from "./session.js";

const PET_LONG_PRESS_MS = 550;

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

  const header = $("chatHeader");
  if (header) {
    header.addEventListener("click", () => openSettings());
    header.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        openSettings();
      }
    });
  }

  bindPetGestures();

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
    const bubble = e.target.closest(".bubble.assistant.replayable");
    if (!bubble) return;
    e.preventDefault();
    if (hooks.replayLastTts) hooks.replayLastTts();
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
