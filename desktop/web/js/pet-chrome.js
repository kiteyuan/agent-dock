/** Fixed canvas with bottom-pinned controls and room for wide replies. */
import { $ } from "./dom.js";
import { MAX_REPLY_WIDTH } from "./pet-reply-layout.js";
import { PREFS } from "./prefs.js";
import { fitPetWindow, setPetHitRects } from "./tauri.js";

const PET_WINDOW_HEIGHT = 700;
const HIT_PAD = 4;

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

export async function fitInitialPetWindow() {
  await fitPetWindow(MAX_REPLY_WIDTH + 24, PET_WINDOW_HEIGHT);
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
    pushRect(out, $("petBubble"));
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
