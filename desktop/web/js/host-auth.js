/** Silent host auth — local pet should never ask the user for a device token. */

import { $ } from "./dom.js";
import { defaultWsUrl, saveConnectionPrefs } from "./prefs.js";
import { readLocalDeviceToken, isTauri } from "./tauri.js";

export function isLocalRuntimeUrl(url) {
  const u = String(url || "").trim().toLowerCase();
  return (
    u.includes("127.0.0.1") ||
    u.includes("localhost") ||
    u.includes("[::1]")
  );
}

/** Ensure URL + token fields are ready for a silent local connect. */
export async function ensureHostAuth() {
  const urlEl = $("url");
  const tokenEl = $("token");
  let url = (urlEl?.value || "").trim() || defaultWsUrl();
  if (urlEl) urlEl.value = url;

  let token = (tokenEl?.value || "").trim();
  if (!token && isTauri()) {
    token = (await readLocalDeviceToken()) || "";
  }
  if (tokenEl && token) tokenEl.value = token;
  if (token) saveConnectionPrefs(url, token);
  return { url, token, local: isLocalRuntimeUrl(url) };
}
