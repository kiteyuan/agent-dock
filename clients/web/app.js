/**
 * AgentDock Web UI entry — ChatGPT-like chat shell (desktop preview).
 * Modules: protocol / prefs / recorder / tts / transcript / session / chrome.
 */
import { $ } from "./js/dom.js";
import { loadConnectionPrefs } from "./js/prefs.js";
import { store } from "./js/store.js";
import { bootPets } from "./js/pets.js";
import { setMood, syncControls } from "./js/mood.js";
import { loadMessages, renderTranscript, setAssistantText } from "./js/transcript.js";
import { connect, wireSessionHooks } from "./js/session.js";
import { bindChrome, openSettings } from "./js/chrome.js";

wireSessionHooks();
bindChrome();
loadConnectionPrefs($("url"), $("token"));
loadMessages();

(async () => {
  await bootPets();
  setMood("offline");
  renderTranscript();
  store.turnLocked = true;
  syncControls();

  const url = ($("url").value || "");
  if (url.includes("127.0.0.1") || url.includes("localhost")) {
    connect();
  } else {
    openSettings();
  }

  if (
    location.protocol === "http:" &&
    location.hostname !== "127.0.0.1" &&
    location.hostname !== "localhost"
  ) {
    store.activeAssistantId = null;
    setAssistantText("Web UI 仅作桌面预览。手机请用 Flutter 客户端（clients/mobile）。");
  }
})();
