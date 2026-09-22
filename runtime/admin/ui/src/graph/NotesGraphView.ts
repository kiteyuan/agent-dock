/**
 * Notes graph: d3-force + Canvas 2D, styled after Obsidian Graph View
 * (degree-sized nodes, hover neighbor highlight, muted labels/links).
 */

import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
  type Simulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from "d3-force";

export type GraphNodeData = {
  id: string;
  title: string;
  path: string;
  exists?: boolean;
};

export type GraphEdgeData = {
  source: string;
  target: string;
};

/** Palette aligned with Obsidian graph CSS tokens (fill / line / text / highlight). */
export type GraphColors = {
  bg: string;
  node: string;
  ghost: string;
  link: string;
  label: string;
  highlight: string;
  highlightLink: string;
};

type SimNode = GraphNodeData &
  SimulationNodeDatum & {
    degree: number;
    radius: number;
    labelHalf: number;
  };

type SimLink = SimulationLinkDatum<SimNode> & {
  source: string | SimNode;
  target: string | SimNode;
};

const LABEL_STACK =
  'Inter, "Segoe UI", "PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif';

function truncate(text: string, max = 18): string {
  const t = text.trim();
  return t.length <= max ? t : `${t.slice(0, max - 1)}…`;
}

function asNode(ref: string | SimNode): SimNode {
  return typeof ref === "object"
    ? ref
    : ({ id: ref, degree: 0, radius: 4, labelHalf: 20 } as SimNode);
}

function nodeRadius(degree: number, exists: boolean): number {
  const base = exists === false ? 3.5 : 4.5;
  return base + Math.sqrt(Math.max(degree, 0)) * 2.2;
}

function labelSize(degree: number): number {
  // Keep the size the user signed off on.
  return 14 + Math.min(6, Math.sqrt(Math.max(degree, 0)) * 1.5);
}

function labelHalfWidth(title: string, degree: number): number {
  const text = truncate(title || "");
  return Math.max(14, (text.length * labelSize(degree) * 0.55) / 2);
}

/** Spread-era collide: node + label footprint so the core cannot collapse. */
function collideRadius(d: SimNode): number {
  const labelH = labelSize(d.degree) * 1.25 + 8;
  return Math.max(
    d.radius + 18,
    d.labelHalf * 1.15 + 12,
    Math.hypot(d.labelHalf * 0.95, d.radius + labelH),
  );
}

function textFadeAlpha(scale: number, threshold = 0.55): number {
  if (scale >= threshold) return 1;
  return Math.max(0.35, scale / threshold);
}

export class NotesGraphView {
  private host: HTMLElement;
  private canvas: HTMLCanvasElement | null = null;
  private ctx: CanvasRenderingContext2D | null = null;
  private sim: Simulation<SimNode, SimLink> | null = null;
  private nodes: SimNode[] = [];
  private links: SimLink[] = [];
  private neighbors = new Map<string, Set<string>>();
  private colors: GraphColors;
  private width = 0;
  private height = 0;
  private dpr = 1;
  private scale = 1;
  private panX = 0;
  private panY = 0;
  private fitted = false;
  private destroyed = false;
  private hoverId: string | null = null;
  private panning = false;
  private panLast = { x: 0, y: 0 };
  private dragging: SimNode | null = null;
  private pendingDrag: SimNode | null = null;
  private dragOrigin = { x: 0, y: 0 };
  private raf = 0;
  private pointerActive = true;
  onSelect: ((node: GraphNodeData | null) => void) | null = null;

  constructor(host: HTMLElement, colors: GraphColors) {
    this.host = host;
    this.colors = colors;
  }

  mount(width: number, height: number): void {
    if (this.destroyed) return;
    this.width = width;
    this.height = height;
    this.dpr = Math.min(window.devicePixelRatio || 1, 2);

    const canvas = document.createElement("canvas");
    canvas.style.display = "block";
    canvas.style.width = "100%";
    canvas.style.height = "100%";
    canvas.style.touchAction = "none";
    canvas.style.cursor = "grab";
    this.host.replaceChildren(canvas);
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.resizeCanvas();
    this.bindViewport(canvas);
    this.loop();
  }

  setColors(colors: GraphColors) {
    this.colors = colors;
  }

  /** When false, ignore hover/pan/drag (e.g. while the doc drawer is open). */
  setPointerActive(active: boolean) {
    this.pointerActive = active;
    if (!active) {
      this.releaseDrag(false);
      this.hoverId = null;
      this.panning = false;
      if (this.canvas) this.canvas.style.cursor = "default";
    } else if (this.canvas) {
      this.canvas.style.cursor = "grab";
    }
  }

  private releaseDrag(keepSimCool = true) {
    if (this.dragging) {
      this.dragging.fx = null;
      this.dragging.fy = null;
      this.dragging = null;
      if (keepSimCool) this.sim?.alphaTarget(0);
    }
    this.pendingDrag = null;
  }

  setData(nodes: GraphNodeData[], edges: GraphEdgeData[]) {
    this.fitted = false;
    this.hoverId = null;

    const degree = new Map<string, number>();
    for (const n of nodes) degree.set(n.id, 0);
    for (const e of edges) {
      degree.set(e.source, (degree.get(e.source) || 0) + 1);
      degree.set(e.target, (degree.get(e.target) || 0) + 1);
    }

    this.neighbors = new Map();
    const addEdge = (a: string, b: string) => {
      if (!this.neighbors.has(a)) this.neighbors.set(a, new Set());
      if (!this.neighbors.has(b)) this.neighbors.set(b, new Set());
      this.neighbors.get(a)!.add(b);
      this.neighbors.get(b)!.add(a);
    };
    for (const e of edges) addEdge(e.source, e.target);

    this.nodes = nodes.map((n) => {
      const deg = degree.get(n.id) || 0;
      return {
        ...n,
        degree: deg,
        radius: nodeRadius(deg, n.exists !== false),
        labelHalf: labelHalfWidth(n.title || n.id, deg),
      };
    });
    this.links = edges.map((e) => ({ source: e.source, target: e.target }));

    // Restore the earlier "more open / outer-spread" force set (pre-tighten).
    this.sim?.stop();
    this.sim = forceSimulation<SimNode, SimLink>(this.nodes)
      .force(
        "link",
        forceLink<SimNode, SimLink>(this.links)
          .id((d) => d.id)
          .distance((d) => {
            const s = asNode(d.source);
            const t = asNode(d.target);
            return 110 + (s.labelHalf + t.labelHalf) * 0.55 + Math.sqrt(s.degree + t.degree) * 10;
          })
          .strength(0.28),
      )
      .force(
        "charge",
        forceManyBody<SimNode>()
          .strength((d) => -520 - d.degree * 55)
          .distanceMin(12)
          .distanceMax(900),
      )
      .force("center", forceCenter(0, 0).strength(0.08))
      // Leaves pull toward the core; hubs barely affected.
      .force(
        "x",
        forceX<SimNode>(0).strength((d) => 0.01 + 0.09 / (1 + d.degree)),
      )
      .force(
        "y",
        forceY<SimNode>(0).strength((d) => 0.01 + 0.09 / (1 + d.degree)),
      )
      .force(
        "collide",
        forceCollide<SimNode>()
          .radius(collideRadius)
          .strength(1)
          .iterations(6),
      )
      .velocityDecay(0.32)
      .alpha(1)
      .alphaDecay(0.016)
      .on("tick", () => {
        if (!this.fitted && (this.sim?.alpha() ?? 1) < 0.03) this.fitOnce();
      });

    for (let i = 0; i < 160; i++) this.sim.tick();
    this.fitOnce();
  }

  resize(width: number, height: number) {
    this.width = width;
    this.height = height;
    this.resizeCanvas();
    if (this.nodes.length) this.fitOnce(true);
  }

  destroy() {
    this.destroyed = true;
    this.sim?.stop();
    this.sim = null;
    if (this.raf) cancelAnimationFrame(this.raf);
    window.removeEventListener("pointermove", this.onPointerMove);
    window.removeEventListener("pointerup", this.onPointerUp);
    this.host.replaceChildren();
    this.canvas = null;
    this.ctx = null;
  }

  private resizeCanvas() {
    if (!this.canvas) return;
    this.canvas.width = Math.max(1, Math.floor(this.width * this.dpr));
    this.canvas.height = Math.max(1, Math.floor(this.height * this.dpr));
  }

  private loop = () => {
    if (this.destroyed) return;
    this.paint();
    this.raf = requestAnimationFrame(this.loop);
  };

  private focusId(): string | null {
    // Selection opens the doc drawer; only hover drives graph focus styling.
    return this.hoverId;
  }

  private isActive(id: string, focus: string | null): boolean {
    if (!focus) return true;
    if (id === focus) return true;
    return this.neighbors.get(focus)?.has(id) ?? false;
  }

  private paint() {
    const ctx = this.ctx;
    if (!ctx || !this.canvas) return;
    const { width: cssW, height: cssH, dpr, colors, scale } = this;
    const focus = this.focusId();

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = colors.bg;
    ctx.fillRect(0, 0, cssW, cssH);

    ctx.save();
    ctx.translate(this.panX, this.panY);
    ctx.scale(scale, scale);

    // Links — Obsidian fades non-related lines on hover
    for (const link of this.links) {
      const s = asNode(link.source);
      const t = asNode(link.target);
      if (s.x == null || s.y == null || t.x == null || t.y == null) continue;
      const related =
        !focus ||
        s.id === focus ||
        t.id === focus ||
        (this.neighbors.get(focus)?.has(s.id) && t.id === focus) ||
        (this.neighbors.get(focus)?.has(t.id) && s.id === focus) ||
        (s.id === focus && this.neighbors.get(focus)?.has(t.id)) ||
        (t.id === focus && this.neighbors.get(focus)?.has(s.id));
      const hi =
        !!focus &&
        ((s.id === focus && this.neighbors.get(focus)?.has(t.id)) ||
          (t.id === focus && this.neighbors.get(focus)?.has(s.id)));

      ctx.beginPath();
      ctx.moveTo(s.x, s.y);
      ctx.lineTo(t.x, t.y);
      ctx.strokeStyle = hi ? colors.highlightLink : colors.link;
      ctx.globalAlpha = focus ? (related && hi ? 0.9 : related ? 0.28 : 0.05) : 0.28;
      ctx.lineWidth = (hi ? 0.7 : 0.45) / scale;
      ctx.stroke();
    }
    ctx.globalAlpha = 1;

    for (const node of this.nodes) {
      if (node.x == null || node.y == null) continue;
      const active = this.isActive(node.id, focus);
      const r = node.radius;
      const unresolved = node.exists === false;
      const hovered = node.id === this.hoverId;

      ctx.beginPath();
      ctx.arc(node.x, node.y, r, 0, Math.PI * 2);
      ctx.fillStyle = hovered
        ? colors.highlight
        : unresolved
          ? colors.ghost
          : colors.node;
      ctx.globalAlpha = focus
        ? active
          ? hovered
            ? 1
            : 0.92
          : 0.12
        : unresolved
          ? 0.5
          : 0.95;
      ctx.fill();
    }

    // Every node keeps its label, always under the node (Obsidian-style world space).
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    const fade = textFadeAlpha(scale);
    for (const node of this.nodes) {
      if (node.x == null || node.y == null) continue;
      const active = this.isActive(node.id, focus);
      if (focus && !active) continue;

      const focused = node.id === this.hoverId;
      const fontPx = labelSize(node.degree);
      const text = truncate(node.title || node.id);
      const y0 = node.y + node.radius + 8;

      ctx.font = `500 ${fontPx}px ${LABEL_STACK}`;
      const baseA = focus ? (focused ? 1 : 0.95) : node.exists === false ? 0.75 : 1;
      ctx.globalAlpha = baseA * (focused ? 1 : fade);
      ctx.lineWidth = 2.5 / scale;
      ctx.strokeStyle = colors.bg;
      ctx.lineJoin = "round";
      ctx.strokeText(text, node.x, y0);
      ctx.fillStyle = colors.label;
      ctx.fillText(text, node.x, y0);
    }
    ctx.globalAlpha = 1;
    ctx.restore();
  }

  private select(node: SimNode | null) {
    this.onSelect?.(
      node
        ? { id: node.id, title: node.title, path: node.path, exists: node.exists }
        : null,
    );
  }

  private fitOnce(force = false) {
    if (this.fitted && !force) return;
    if (!this.nodes.length || this.width <= 0 || this.height <= 0) return;
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    for (const n of this.nodes) {
      if (n.x == null || n.y == null) continue;
      const pad = n.radius + n.labelHalf * 0.35 + 14;
      minX = Math.min(minX, n.x - pad);
      minY = Math.min(minY, n.y - pad);
      maxX = Math.max(maxX, n.x + pad);
      maxY = Math.max(maxY, n.y + pad);
    }
    if (!Number.isFinite(minX)) return;
    const bw = Math.max(maxX - minX, 40);
    const bh = Math.max(maxY - minY, 40);
    const pad = 48;
    const next = Math.min((this.width - pad * 2) / bw, (this.height - pad * 2) / bh, 2.2);
    const cx = (minX + maxX) / 2;
    const cy = (minY + maxY) / 2;
    this.scale = next;
    this.panX = this.width / 2 - cx * next;
    this.panY = this.height / 2 - cy * next;
    this.fitted = true;
  }

  private screenToWorld(clientX: number, clientY: number) {
    const rect = this.canvas!.getBoundingClientRect();
    return {
      x: (clientX - rect.left - this.panX) / this.scale,
      y: (clientY - rect.top - this.panY) / this.scale,
    };
  }

  private hitTest(clientX: number, clientY: number): SimNode | null {
    const { x, y } = this.screenToWorld(clientX, clientY);
    let best: SimNode | null = null;
    let bestD = Infinity;
    for (const n of this.nodes) {
      if (n.x == null || n.y == null) continue;
      const hit = n.radius + 6 / this.scale;
      const dx = n.x - x;
      const dy = n.y - y;
      const d = dx * dx + dy * dy;
      if (d <= hit * hit && d < bestD) {
        bestD = d;
        best = n;
      }
    }
    return best;
  }

  private bindViewport(canvas: HTMLCanvasElement) {
    canvas.addEventListener(
      "wheel",
      (ev) => {
        if (!this.pointerActive) return;
        ev.preventDefault();
        const rect = canvas.getBoundingClientRect();
        const mx = ev.clientX - rect.left;
        const my = ev.clientY - rect.top;
        const prev = this.scale;
        const next = Math.min(4, Math.max(0.12, prev * (ev.deltaY < 0 ? 1.08 : 0.92)));
        const wx = (mx - this.panX) / prev;
        const wy = (my - this.panY) / prev;
        this.scale = next;
        this.panX = mx - wx * next;
        this.panY = my - wy * next;
      },
      { passive: false },
    );

    canvas.addEventListener("pointerdown", (ev) => {
      if (!this.pointerActive) return;
      const hit = this.hitTest(ev.clientX, ev.clientY);
      if (hit) {
        // Click opens the doc; only start a drag after the pointer moves.
        this.pendingDrag = hit;
        this.dragOrigin = { x: ev.clientX, y: ev.clientY };
        this.select(hit);
        return;
      }
      this.panning = true;
      this.panLast = { x: ev.clientX, y: ev.clientY };
      this.select(null);
      canvas.style.cursor = "grabbing";
    });

    window.addEventListener("pointermove", this.onPointerMove);
    window.addEventListener("pointerup", this.onPointerUp);
  }

  private onPointerMove = (ev: PointerEvent) => {
    if (!this.pointerActive) return;
    if (this.pendingDrag && !this.dragging) {
      const dx = ev.clientX - this.dragOrigin.x;
      const dy = ev.clientY - this.dragOrigin.y;
      if (dx * dx + dy * dy > 25) {
        this.dragging = this.pendingDrag;
        this.pendingDrag = null;
        this.dragging.fx = this.dragging.x;
        this.dragging.fy = this.dragging.y;
        this.sim?.alphaTarget(0.18).restart();
        if (this.canvas) this.canvas.style.cursor = "grabbing";
      } else {
        return;
      }
    }
    if (this.dragging) {
      const w = this.screenToWorld(ev.clientX, ev.clientY);
      this.dragging.fx = w.x;
      this.dragging.fy = w.y;
      this.dragging.x = w.x;
      this.dragging.y = w.y;
      return;
    }
    if (this.panning) {
      const dx = ev.clientX - this.panLast.x;
      const dy = ev.clientY - this.panLast.y;
      this.panLast = { x: ev.clientX, y: ev.clientY };
      this.panX += dx;
      this.panY += dy;
      return;
    }
    const hit = this.hitTest(ev.clientX, ev.clientY);
    this.hoverId = hit?.id ?? null;
    if (this.canvas) this.canvas.style.cursor = hit ? "pointer" : "grab";
  };

  private onPointerUp = () => {
    this.releaseDrag(true);
    this.panning = false;
    if (this.canvas) {
      this.canvas.style.cursor = !this.pointerActive
        ? "default"
        : this.hoverId
          ? "pointer"
          : "grab";
    }
  };
}
