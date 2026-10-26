/** Thin helpers for Tauri host APIs (no-ops in browser fallback). */

export function isTauri() {
  return typeof window !== "undefined" && !!window.__TAURI__;
}

export async function invoke(cmd, args = {}) {
  const fn = window.__TAURI__?.core?.invoke;
  if (typeof fn !== "function") return null;
  return fn(cmd, args);
}

/** Native OS window drag (smooth). Transparent Win windows may show a wireframe while dragging. */
export async function startWindowDrag() {
  const getWin = window.__TAURI__?.window?.getCurrentWindow;
  if (typeof getWin !== "function") return false;
  try {
    await getWin().startDragging();
    return true;
  } catch (_) {
    return false;
  }
}

export async function readLocalDeviceToken() {
  try {
    const token = await invoke("local_device_token");
    return typeof token === "string" && token ? token : null;
  } catch (_) {
    return null;
  }
}

export async function secureDeviceTokenGet() {
  try {
    const token = await invoke("secure_device_token_get");
    return typeof token === "string" && token ? token : null;
  } catch (_) {
    return null;
  }
}

export async function secureDeviceTokenSet(token) {
  await invoke("secure_device_token_set", { token: String(token || "") });
}

export async function secureDeviceTokenClear() {
  await invoke("secure_device_token_clear");
}

export async function fitPetWindow(width, height) {
  try {
    await invoke("fit_pet_window", { width, height });
  } catch (_) {}
}

/** Open the bundled console window (Tauri). Browser-pet fallback uses Runtime /admin/. */
export async function openAdminPanel() {
  if (isTauri()) {
    try {
      await invoke("open_admin_panel");
      return true;
    } catch (err) {
      console.warn("open_admin_panel failed", err);
      return false;
    }
  }
  try {
    window.open("http://127.0.0.1:8766/admin/", "agentdock-admin");
    return true;
  } catch (_) {
    return false;
  }
}
