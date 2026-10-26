import {
  isTauri,
  secureDeviceTokenClear,
  secureDeviceTokenGet,
  secureDeviceTokenSet,
} from "./tauri.js";

export const PREFS = {
  url: "ad_url",
  token: "ad_token",
  messages: "ad_messages",
  device: "ad_device_id",
  chromeCompact: "ad_chrome_compact",
};

export function defaultWsUrl() {
  return "ws://127.0.0.1:8765";
}

export function stableDeviceId() {
  let id = localStorage.getItem(PREFS.device) || "";
  // Migrate old web- preview ids to desktop- host pet ids.
  if (id.startsWith("web-")) {
    id = "desktop-" + id.slice(4);
    localStorage.setItem(PREFS.device, id);
  }
  if (!id) {
    id =
      "desktop-" +
      Math.random().toString(16).slice(2) +
      Date.now().toString(16).slice(-4);
    localStorage.setItem(PREFS.device, id);
  }
  return id;
}

/** Browser fallback: persist cleartext tokens only for loopback hosts. */
export function isLoopbackWsUrl(url) {
  try {
    const u = new URL(String(url || "").trim());
    const h = (u.hostname || "").toLowerCase();
    return h === "127.0.0.1" || h === "localhost" || h === "::1";
  } catch {
    return false;
  }
}

async function readStoredToken(url) {
  if (isTauri()) {
    const legacy = localStorage.getItem(PREFS.token) || "";
    if (legacy) {
      try {
        await secureDeviceTokenSet(legacy);
      } catch (_) {}
      localStorage.removeItem(PREFS.token);
    }
    try {
      return (await secureDeviceTokenGet()) || "";
    } catch (_) {
      return "";
    }
  }
  if (!isLoopbackWsUrl(url)) return "";
  return localStorage.getItem(PREFS.token) || "";
}

async function writeStoredToken(url, token) {
  const value = String(token || "");
  if (isTauri()) {
    localStorage.removeItem(PREFS.token);
    try {
      if (value) await secureDeviceTokenSet(value);
      else await secureDeviceTokenClear();
    } catch (_) {}
    return;
  }
  if (isLoopbackWsUrl(url)) {
    localStorage.setItem(PREFS.token, value);
  } else {
    localStorage.removeItem(PREFS.token);
  }
}

export async function loadConnectionPrefs(urlEl, tokenEl) {
  const saved = localStorage.getItem(PREFS.url) || "";
  const url = saved || defaultWsUrl();
  if (urlEl) urlEl.value = url;
  if (tokenEl) tokenEl.value = await readStoredToken(url);
}

export async function saveConnectionPrefs(url, token) {
  const trimmed = String(url || "").trim();
  localStorage.setItem(PREFS.url, trimmed);
  await writeStoredToken(trimmed, token);
}
