import { $ } from "./dom.js";

const BASE_WIDTH = 360;
const WIDTH_STEP = 160;
const WIDEN_AT_HEIGHT = 480;
export const MAX_REPLY_WIDTH = 960;

let currentPage = 0;
let pageCount = 1;
let previousTurn;

function showPage(page) {
  currentPage = Math.max(0, Math.min(pageCount - 1, page));
  $("petBubbleBody").style.transform = currentPage ? `translateX(-${currentPage * 100}%)` : "";
  $("petPagePrev").disabled = currentPage === 0;
  $("petPageNext").disabled = currentPage + 1 === pageCount;
  $("petPageCount").textContent = `${currentPage + 1} / ${pageCount}`;
}

export function layoutPetReply() {
  const bubble = $("petBubble");
  const body = $("petBubbleBody");
  if (!bubble.offsetWidth || $("petBubbleReply").hidden) return;

  if (previousTurn !== bubble.dataset.turnKey) currentPage = 0;
  previousTurn = bubble.dataset.turnKey;
  const viewport = body.parentElement;
  const limit = Math.min(MAX_REPLY_WIDTH, bubble.parentElement.clientWidth);
  const pages = $("petPages");
  pages.hidden = true;
  body.classList.remove("is-paged");
  viewport.style.height = "";
  bubble.style.width = "";
  bubble.style.removeProperty("--pet-bubble-max");

  // Measure actual wrapped text, including markdown, padding and the process line.
  let width = BASE_WIDTH;
  let clipped = body.offsetHeight > viewport.clientHeight + 1;
  while (width < limit && (clipped || bubble.offsetHeight > WIDEN_AT_HEIGHT)) {
    width = Math.min(width + WIDTH_STEP, limit);
    bubble.style.setProperty("--pet-bubble-max", width + "px");
    bubble.style.width = width + "px";
    clipped = body.offsetHeight > viewport.clientHeight + 1;
  }

  pageCount = 1;
  if (clipped && viewport.clientHeight > 0) {
    pages.hidden = false;
    // Reserve navigation space before fixing the column height.
    viewport.style.height = viewport.clientHeight + "px";
    body.classList.add("is-paged");
    pageCount = Math.max(1, Math.round(body.scrollWidth / Math.max(1, body.clientWidth)));
  }
  showPage(currentPage);
}

export function bindPetReplyLayout() {
  $("petPagePrev").onclick = () => showPage(currentPage - 1);
  $("petPageNext").onclick = () => showPage(currentPage + 1);
  window.addEventListener("resize", layoutPetReply);
  const observer = new ResizeObserver(layoutPetReply);
  observer.observe($("composerForm"));
  observer.observe(document.querySelector(".composer-pet-stack"));
  new MutationObserver(layoutPetReply).observe(document.documentElement, {
    attributes: true, attributeFilter: ["class"],
  });
}
