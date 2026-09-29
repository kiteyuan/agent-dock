import { $ } from "./dom.js";
import { store } from "./store.js";

export function forEachBot(fn) {
  for (const b of store.bots) {
    try {
      fn(b);
    } catch (_) {}
  }
}

export function applyPetFromRuntime(defaultId) {
  const id = defaultId || "";
  forEachBot((b) => {
    if (id) b.setPet(id);
    b.reload();
  });
}

export async function bootPets() {
  const canvas = $("spriteComposer");
  store.bots = canvas ? [window.PixelBot.createPixelBot(canvas, "")] : [];
  window.pixelBot = store.bots[0] || null;
  await Promise.all(store.bots.map((b) => b.ready));
  store.bots.forEach((b) => b.start());
}
