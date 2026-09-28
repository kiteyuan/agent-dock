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
  const label =
    (window.pixelBot &&
      window.pixelBot.listPets().find((p) => p.id === (id || window.pixelBot.getPet()))) ||
    null;
  const name = (label && label.label) || id || "AgentDock";
  if ($("charName")) $("charName").textContent = name;
}

export async function bootPets() {
  const canvases = ["spriteComposer", "spriteSidebar"]
    .map((id) => $(id))
    .filter(Boolean);
  store.bots = canvases.map((c) => window.PixelBot.createPixelBot(c, ""));
  window.pixelBot = store.bots[0] || null;
  await Promise.all(store.bots.map((b) => b.ready));
  store.bots.forEach((b) => b.start());
}
