/**
 * Pet window sizing — the OS window is a fixed, tall, transparent canvas.
 *
 * Resizing a WebView2 window is asynchronous: the HWND moves/grows first and the
 * page catches up a frame or more later, so anything that resizes on bubble open
 * makes the pet jump. Instead the window keeps one height (grow-only, for very
 * long replies), chrome is bottom-pinned by CSS, and the transparent area is
 * made click-through by reporting hit rects to Rust (`set_pet_hit_rects`).
 */

import { $ } from "./dom.js";
import { PREFS } from "./prefs.js";
import { fitPetWindow, setPetHitRects } from "./tauri.js";

/** Default canvas height — fits pet + composer + a typical bubble without resizing. */
const PET_WINDOW_MIN_H = 600;
const HIT_PAD = 4;

let _fitTimer = null;
let _fitRunning = false;
let _fitQueued = false;
let _fitQueuedForce = false;
let _fitWaiters = [];
let _lastFitW = 0;
let _lastFitH = 0;
/** Width locks after the first successful fit. */
let _widthLocked = false;

let _hitSuspended = false;
let _hitRaf = 0;
let _lastHitKey = "";

export function focusComposer() {
  const input = $("composerInput");
  requestAnimationFrame(() => input?.focus());
}

export function isChromeCompact() {
  return document.documentElement.classList.contains("chrome-compact");
}

function waitFrames(n = 2) {
  return new Promise((resolve) => {
    const step = () => {
      if (--n <= 0) resolve();
      else requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  });
}

/** Wait until the webview's innerHeight has caught up to a fit (or timeout). */
async function waitForInnerHeight(targetH, timeoutMs = 500) {
  const floor = Math.max(0, targetH - 16);
  const start = performance.now();
  while (performance.now() - start < timeoutMs) {
    if (window.innerHeight >= floor) return;
    await waitFrames(1);
  }
}

export function setChromeCompact(on) {
  const next = !!on;
  const root = document.documentElement;
  if (root.classList.contains("chrome-compact") === next) {
    return;
  }

  // CSS only — window size is untouched, so the bottom-pinned pet cannot move.
  if (next) root.classList.add("chrome-compact");
  else root.classList.remove("chrome-compact");

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
  scheduleHitRectSync();
}

export function toggleChromeCompact() {
  setChromeCompact(!isChromeCompact());
}

export function loadChromeCompactPref() {
  try {
    const want = localStorage.getItem(PREFS.chromeCompact) === "1";
    if (want) {
      document.documentElement.classList.add("chrome-compact");
    }
  } catch (_) {}
}

export function syncStatusVisibility(_mood) {
  const tag = $("statusTag");
  if (!tag) return;
  tag.hidden = true;
  tag.setAttribute("aria-hidden", "true");
}

function petBubbleMaxPx() {
  const raw = getComputedStyle(document.documentElement)
    .getPropertyValue("--pet-bubble-max")
    .trim();
  const n = parseFloat(raw);
  return Number.isFinite(n) && n > 0 ? n : 480;
}

/** Intrinsic content size — independent of the current window height. */
function chromeBounds(petStage) {
  const cs = getComputedStyle(petStage);
  const padX =
    (parseFloat(cs.paddingLeft) || 0) + (parseFloat(cs.paddingRight) || 0);
  const padY =
    (parseFloat(cs.paddingTop) || 0) + (parseFloat(cs.paddingBottom) || 0);
  const gap = parseFloat(cs.rowGap || cs.gap) || 0;

  let contentW = 0;
  let contentH = 0;
  let n = 0;
  for (const el of petStage.children) {
    if (el.hidden) continue;
    const st = getComputedStyle(el);
    if (st.display === "none") continue;
    const w = Math.max(el.offsetWidth, el.scrollWidth);
    const h = Math.max(el.offsetHeight, el.scrollHeight);
    if (w < 1 && h < 1) continue;
    contentW = Math.max(contentW, w);
    contentH += h;
    n += 1;
  }

  if (n === 0) {
    const r = petStage.getBoundingClientRect();
    return { width: r.width, height: r.height };
  }
  if (n > 1) contentH += gap * (n - 1);
  return { width: contentW + padX, height: contentH + padY };
}

function neededWindowHeight(petStage) {
  return Math.max(PET_WINDOW_MIN_H, Math.ceil(chromeBounds(petStage).height) + 12);
}

async function applyFitPetWindow(force = false) {
  const stage = $("stage");
  const petStage = stage?.querySelector(".pet-stage");
  if (!stage || !petStage) return;
  await waitFrames(2);

  let w = _lastFitW;
  if (!_widthLocked || _lastFitW <= 0) {
    const cardCap = Math.ceil(petBubbleMaxPx()) + 24;
    w = Math.max(Math.ceil(chromeBounds(petStage).width) + 16, cardCap);
    _widthLocked = true;
    // Height must be measured at the final width — a narrower window wraps the
    // bubble taller, and grow-only would keep that inflated height forever.
    if (Math.abs(window.innerWidth - w) > 2) {
      await fitPetWindow(w, Math.max(window.innerHeight, PET_WINDOW_MIN_H));
      const start = performance.now();
      while (Math.abs(window.innerWidth - w) > 2 && performance.now() - start < 500) {
        await waitFrames(1);
      }
      await waitFrames(1);
    }
  }
  // Grow-only: shrinking would resize on every bubble close, and the transparent
  // area is click-through anyway.
  const h = Math.max(neededWindowHeight(petStage), _lastFitH);

  if (!force && Math.abs(w - _lastFitW) < 2 && Math.abs(h - _lastFitH) < 2) {
    return;
  }
  _lastFitW = w;
  _lastFitH = h;
  await fitPetWindow(w, h);
  scheduleHitRectSync();
}

/**
 * @param {{ immediate?: boolean, debounceMs?: number, force?: boolean }} [opts]
 */
export async function scheduleFitPetWindow(opts = {}) {
  const force = !!opts.force;
  const immediate = !!opts.immediate || force;
  const debounceMs = opts.debounceMs ?? (immediate ? 0 : 100);

  if (!(immediate && debounceMs <= 0)) {
    if (_fitTimer) clearTimeout(_fitTimer);
    return new Promise((resolve) => {
      _fitTimer = setTimeout(() => {
        _fitTimer = null;
        void scheduleFitPetWindow({ immediate: true, force }).then(resolve);
      }, debounceMs);
    });
  }

  if (_fitTimer) {
    clearTimeout(_fitTimer);
    _fitTimer = null;
  }

  if (_fitRunning) {
    _fitQueued = true;
    _fitQueuedForce = _fitQueuedForce || force;
    return new Promise((resolve) => {
      _fitWaiters.push(resolve);
    });
  }

  _fitRunning = true;
  try {
    await applyFitPetWindow(force);
  } finally {
    _fitRunning = false;
    if (_fitQueued) {
      _fitQueued = false;
      const f = _fitQueuedForce;
      _fitQueuedForce = false;
      await scheduleFitPetWindow({ immediate: true, force: f });
    }
    const waiters = _fitWaiters.splice(0);
    for (const w of waiters) w();
  }
}

/** True when the chrome no longer fits the current (fixed) window height. */
export function contentNeedsWindowGrow() {
  const petStage = document.querySelector(".pet-stage");
  if (!petStage) return false;
  return neededWindowHeight(petStage) > window.innerHeight + 2;
}

/**
 * Rare path (very long reply): veil the bubble slot while the window grows so the
 * clipped frame isn't painted. The pet itself stays visible.
 */
export async function fitPetChromeGrowing() {
  const root = document.documentElement;
  root.classList.add("chrome-growing");
  try {
    await scheduleFitPetWindow({ immediate: true });
    await waitForInnerHeight(_lastFitH);
    await waitFrames(1);
  } finally {
    root.classList.remove("chrome-growing");
  }
}

// —— Click-through hit rects ——

function pushRect(out, el) {
  if (!el || el.hidden) return;
  const st = getComputedStyle(el);
  if (st.display === "none" || st.visibility === "hidden") return;
  const r = el.getBoundingClientRect();
  if (r.width < 1 || r.height < 1) return;
  out.push([
    Math.floor(r.left - HIT_PAD),
    Math.floor(r.top - HIT_PAD),
    Math.ceil(r.width + HIT_PAD * 2),
    Math.ceil(r.height + HIT_PAD * 2),
  ]);
}

function collectHitRects() {
  if (_hitSuspended || $("settings")?.open) return null;
  const root = document.documentElement;
  const out = [];
  pushRect(out, $("btnComposerPet"));
  if (!root.classList.contains("chrome-compact")) {
    pushRect(out, $("composerForm"));
    document.querySelectorAll(".pet-flank-btn").forEach((el) => pushRect(out, el));
    if (!root.classList.contains("chrome-growing")) pushRect(out, $("petBubble"));
  }
  return out;
}

function flushHitRects() {
  _hitRaf = 0;
  const rects = collectHitRects();
  const key = JSON.stringify(rects);
  if (key === _lastHitKey) return;
  _lastHitKey = key;
  void setPetHitRects(rects);
}

export function scheduleHitRectSync() {
  if (!_hitRaf) _hitRaf = requestAnimationFrame(flushHitRects);
}

/** Whole window clickable while dragging (the cursor can outrun the window). */
export function suspendPetHitThrough(on) {
  _hitSuspended = !!on;
  scheduleHitRectSync();
}

/** Keep hit rects in sync with layout; call once at boot. */
export function bindPetHitRects() {
  const stage = document.querySelector(".pet-stage");
  if (!stage) return;
  const ro = new ResizeObserver(scheduleHitRectSync);
  ro.observe(stage);
  for (const id of ["petBubble", "composerForm", "btnComposerPet"]) {
    const el = $(id);
    if (el) ro.observe(el);
  }
  const mo = new MutationObserver(scheduleHitRectSync);
  mo.observe(stage, { subtree: true, attributes: true, attributeFilter: ["hidden", "class"] });
  mo.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
  const settings = $("settings");
  if (settings) mo.observe(settings, { attributes: true, attributeFilter: ["open"] });
  window.addEventListener("resize", scheduleHitRectSync);
  scheduleHitRectSync();
}
