/** Pet-mode chrome: compact always-on composer + window fit. */

import { $ } from "./dom.js";
import { PREFS } from "./prefs.js";
import { fitPetWindow } from "./tauri.js";

let _fitTimer = null;
let _fitRunning = false;
let _lastFitW = 0;
let _lastFitH = 0;
let _fitQueued = false;

export function focusComposer() {
  const input = $("composerInput");
  requestAnimationFrame(() => input?.focus());
}

/** Hide everything except the pet character. */
export function isChromeCompact() {
  return document.documentElement.classList.contains("chrome-compact");
}

export function setChromeCompact(on) {
  const next = !!on;
  document.documentElement.classList.toggle("chrome-compact", next);
  try {
    localStorage.setItem(PREFS.chromeCompact, next ? "1" : "0");
  } catch (_) {}
  const pet = $("btnComposerPet");
  if (pet) {
    const hint = next
      ? "点按说话；右键恢复界面；拖动移动"
      : "点按说话；长按聚焦输入；右键只留人物；拖动移动";
    pet.title = hint;
    pet.setAttribute("aria-label", hint);
  }
  void scheduleFitPetWindow({ immediate: true });
}

export function toggleChromeCompact() {
  setChromeCompact(!isChromeCompact());
}

export function loadChromeCompactPref() {
  try {
    setChromeCompact(localStorage.getItem(PREFS.chromeCompact) === "1");
  } catch (_) {
    setChromeCompact(false);
  }
}

export function syncStatusVisibility(mood) {
  const tag = $("statusTag");
  if (!tag) return;
  const hide = mood === "idle" || mood === "listen" || mood === "speak" || mood === "busy";
  tag.hidden = hide;
  tag.setAttribute("aria-hidden", hide ? "true" : "false");
}

/** Bounds of visible pet-stage children (ignores display:none / [hidden]). */
function visibleStageBounds(petStage) {
  let left = Infinity;
  let top = Infinity;
  let right = -Infinity;
  let bottom = -Infinity;
  let any = false;
  for (const el of petStage.children) {
    if (el.hidden) continue;
    const st = getComputedStyle(el);
    if (st.display === "none" || st.visibility === "hidden") continue;
    const r = el.getBoundingClientRect();
    if (r.width < 1 && r.height < 1) continue;
    any = true;
    left = Math.min(left, r.left);
    top = Math.min(top, r.top);
    right = Math.max(right, r.right);
    bottom = Math.max(bottom, r.bottom);
  }
  if (!any) return petStage.getBoundingClientRect();
  return {
    left,
    top,
    right,
    bottom,
    width: right - left,
    height: bottom - top,
  };
}

async function applyFitPetWindow() {
  const stage = $("stage");
  const petStage = stage?.querySelector(".pet-stage");
  if (!stage || !petStage) return;
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  const compact = isChromeCompact();
  const rect = visibleStageBounds(petStage);
  const minW = compact ? 148 : 240;
  const minH = compact ? 148 : 200;
  const w = Math.max(minW, Math.ceil(rect.width) + (compact ? 8 : 16));
  const h = Math.max(minH, Math.ceil(rect.height) + (compact ? 8 : 12));
  const grew = h > _lastFitH + 1 || w > _lastFitW + 1;
  // Skip tiny shrink/noise; always apply real growth so text isn't clipped.
  if (!grew && Math.abs(w - _lastFitW) < 2 && Math.abs(h - _lastFitH) < 2) return;
  if (!grew && h < _lastFitH - 1 && Math.abs(w - _lastFitW) < 2) {
    // Ignore 1–2px shrink flicker during caret/type; allow larger shrinks.
    if (_lastFitH - h < 8) return;
  }
  // Compact shrinks a lot — always apply so the sprite doesn't sit in a wide empty frame.
  if (compact || grew || Math.abs(w - _lastFitW) >= 2 || Math.abs(h - _lastFitH) >= 2) {
    _lastFitW = w;
    _lastFitH = h;
    await fitPetWindow(w, h);
  }
}

/**
 * @param {{ immediate?: boolean, debounceMs?: number }} [opts]
 * Typing should debounce; mood / show-hide can be immediate.
 */
export async function scheduleFitPetWindow(opts = {}) {
  const immediate = !!opts.immediate;
  const debounceMs = opts.debounceMs ?? (immediate ? 0 : 120);

  if (immediate && debounceMs <= 0) {
    if (_fitTimer) {
      clearTimeout(_fitTimer);
      _fitTimer = null;
    }
    if (_fitRunning) {
      _fitQueued = true;
      return;
    }
    _fitRunning = true;
    try {
      await applyFitPetWindow();
    } finally {
      _fitRunning = false;
      if (_fitQueued) {
        _fitQueued = false;
        void scheduleFitPetWindow({ immediate: true });
      }
    }
    return;
  }

  if (_fitTimer) clearTimeout(_fitTimer);
  _fitTimer = setTimeout(() => {
    _fitTimer = null;
    void scheduleFitPetWindow({ immediate: true });
  }, debounceMs);
}
