import { $ } from "./dom.js";
import { store, hooks } from "./store.js";
import { addAttachmentsFromFiles } from "./transcript.js";
import {
  connect,
  toggleTalk,
  sendUserMessage,
  resetConversation,
} from "./session.js";

function showSettingsMain() {
  $("settingsMain").hidden = false;
  $("settingsResetConfirm").hidden = true;
}

function showSettingsResetConfirm() {
  $("settingsMain").hidden = true;
  $("settingsResetConfirm").hidden = false;
}

export function openSettings() {
  closeSidebar();
  showSettingsMain();
  const chrome = $("btnChromeNew");
  if (chrome) {
    chrome.disabled = !(
      store.sessionId &&
      store.ws &&
      store.ws.readyState === WebSocket.OPEN
    );
  }
  $("settings").showModal();
}

function openNewSessionConfirm() {
  if (!store.sessionId || !store.ws || store.ws.readyState !== WebSocket.OPEN) return;
  closeSidebar();
  showSettingsResetConfirm();
  $("settings").showModal();
}

function openSidebar() {
  $("stage").classList.add("sidebar-open");
  const bd = $("sidebarBackdrop");
  if (bd) bd.hidden = false;
}

function closeSidebar() {
  $("stage").classList.remove("sidebar-open");
  const bd = $("sidebarBackdrop");
  if (bd) bd.hidden = true;
}

function toggleSidebar() {
  if ($("stage").classList.contains("sidebar-open")) closeSidebar();
  else openSidebar();
}

function startOrToggleMic() {
  if (!store.sessionId) {
    openSettings();
    return;
  }
  toggleTalk().catch(() => {
    store.recording = false;
    store.starting = false;
    store.stopping = false;
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
    $("settings").close();
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

  $("btnOpenChar").onclick = () => openSettings();
  $("btnComposerPet").onclick = (e) => {
    e.preventDefault();
    startOrToggleMic();
  };
  $("btnMenu").onclick = () => toggleSidebar();
  $("btnCloseSidebar").onclick = () => closeSidebar();
  $("sidebarBackdrop").onclick = () => closeSidebar();

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
