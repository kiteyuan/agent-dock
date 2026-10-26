/** Thin helpers for Tauri host APIs (no-ops in browser fallback). */

export function isTauri() {
  return typeof window !== "undefined" && !!window.__TAURI__;
}

export async function invoke(cmd, args = {}) {
  const fn = window.__TAURI__?.core?.invoke;
  if (typeof fn !== "function") return null;
  return fn(cmd, args);
}

/** Logical outer position of the main pet window. */
export async function getPetWindowPos() {
  try {
    const p = await invoke("pet_window_pos");
    if (Array.isArray(p) && p.length >= 2) {
      return { x: Number(p[0]), y: Number(p[1]) };
    }
  } catch (_) {}
  return null;
}

/** Set logical outer position — fire-and-forget friendly for drag. */
export function setPetWindowPos(x, y) {
  return invoke("set_pet_window_pos", { x, y });
}

/** Legacy OS drag — may show a rectangular frame on transparent Win windows. */
export async function startWindowDrag() {
  try {
    await invoke("start_pet_drag");
    return true;
  } catch (_) {}
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

/** Interactive regions ([x, y, w, h] CSS px); `null` = whole window clickable. */
export async function setPetHitRects(rects) {
  try {
    await invoke("set_pet_hit_rects", { rects });
  } catch (_) {}
}

/** Open the App-bundled console window (Tauri). Browser-pet fallback cannot host Admin UI. */
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
  console.warn("Admin console requires the Tauri desk-pet window");
  return false;
}

/**
 * Full host stop (like scripts/stop.*): stop sidecars, kill Runtime, exit pet.
 */
export async function shutdownHost() {
  if (!isTauri()) {
    throw new Error("关闭服务需要 Tauri 桌宠（或运行 scripts/stop.ps1）");
  }
  await invoke("shutdown_host");
}
