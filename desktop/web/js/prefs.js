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

/** Persist device tokens only for loopback hosts (cleartext localStorage). */
export function isLoopbackWsUrl(url) {
  try {
    const u = new URL(String(url || "").trim());
    const h = (u.hostname || "").toLowerCase();
    return h === "127.0.0.1" || h === "localhost" || h === "::1";
  } catch {
    return false;
  }
}

export function loadConnectionPrefs(urlEl, tokenEl) {
  const saved = localStorage.getItem(PREFS.url) || "";
  const url = saved || defaultWsUrl();
  if (urlEl) urlEl.value = url;
  if (tokenEl) {
    tokenEl.value = isLoopbackWsUrl(url)
      ? localStorage.getItem(PREFS.token) || ""
      : "";
  }
}

export function saveConnectionPrefs(url, token) {
  const trimmed = String(url || "").trim();
  localStorage.setItem(PREFS.url, trimmed);
  if (isLoopbackWsUrl(trimmed)) {
    localStorage.setItem(PREFS.token, String(token || ""));
  } else {
    // LAN / remote: keep token in the form for this session only.
    localStorage.removeItem(PREFS.token);
  }
}
