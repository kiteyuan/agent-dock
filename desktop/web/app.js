/**
 * Host desktop pet — character only; auth is silent on localhost.
 */
import { $ } from "./js/dom.js";
import { loadConnectionPrefs } from "./js/prefs.js";
import { store } from "./js/store.js";
import { bootPets } from "./js/pets.js";
import { setMood, syncControls } from "./js/mood.js";
import { loadMessages, renderTranscript } from "./js/transcript.js";
import { connect, wireSessionHooks } from "./js/session.js";
import { bindChrome } from "./js/chrome.js";
import { ensureHostAuth } from "./js/host-auth.js";
import {
  scheduleFitPetWindow,
  loadChromeCompactPref,
  bindPetHitRects,
} from "./js/pet-chrome.js";

document.documentElement.classList.add("pet-mode");

wireSessionHooks();
bindChrome();
loadChromeCompactPref();
loadMessages();

(async () => {
  await loadConnectionPrefs($("url"), $("token"));
  await bootPets();
  setMood("offline");
  renderTranscript();
  store.turnLocked = true;
  syncControls();
  await scheduleFitPetWindow({ immediate: true, force: true });
  bindPetHitRects();

  const { local } = await ensureHostAuth();
  // Local host pet: always connect silently — never pop a config sheet.
  if (local) {
    connect();
    return;
  }
  // Remote URL saved: still try; advanced settings via Ctrl+Shift+,
  connect();
})();
