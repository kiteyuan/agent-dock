export const PREFS = {
  url: "ad_url",
  token: "ad_token",
  messages: "ad_messages",
  device: "ad_device_id",
};

export function defaultWsUrl() {
  return "ws://127.0.0.1:8765";
}

export function stableDeviceId() {
  let id = localStorage.getItem(PREFS.device) || "";
  if (!id) {
    id = "web-" + Math.random().toString(16).slice(2) + Date.now().toString(16).slice(-4);
    localStorage.setItem(PREFS.device, id);
  }
  return id;
}

export function loadConnectionPrefs(urlEl, tokenEl) {
  const saved = localStorage.getItem(PREFS.url) || "";
  const url = saved || defaultWsUrl();
  if (urlEl) urlEl.value = url;
  if (tokenEl) tokenEl.value = localStorage.getItem(PREFS.token) || "";
}

export function saveConnectionPrefs(url, token) {
  localStorage.setItem(PREFS.url, String(url || "").trim());
  localStorage.setItem(PREFS.token, String(token || ""));
}
