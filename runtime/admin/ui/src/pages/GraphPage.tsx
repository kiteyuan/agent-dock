import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CloseOutlined } from "@ant-design/icons";
import { Button, Drawer, Empty, Flex, Spin, Typography } from "antd";
import MarkdownPreview from "@uiw/react-markdown-preview";
import { api } from "../api";
import { NotesGraphView, type GraphColors, type GraphNodeData } from "../graph/NotesGraphView";
import { useThemeMode } from "../themeRoot";

const { Title } = Typography;

type GraphPayload = {
  ok?: boolean;
  root?: string;
  nodes: GraphNodeData[];
  edges: Array<{ source: string; target: string }>;
  stats?: { notes?: number; placeholders?: number; links?: number };
};

type NoteDoc = {
  ok?: boolean;
  id?: string;
  title?: string;
  path?: string;
  exists?: boolean;
  content?: string;
  error?: string;
};

function themeColors(light: boolean): GraphColors {
  // Match Admin page chrome (`--bg`), not elevated white cards.
  return light
    ? {
        bg: "#f5f5f6",
        node: "#5c5c5c",
        ghost: "#b0b0b0",
        link: "#c8c8c8",
        label: "#141414",
        highlight: "#f07840",
        highlightLink: "#f07840",
      }
    : {
        bg: "#121212",
        node: "#a0a0a0",
        ghost: "#555555",
        link: "#3f3f3f",
        label: "#f2f2f2",
        highlight: "#f07840",
        highlightLink: "#f07840",
      };
}

/** Drop YAML frontmatter and a leading H1 that duplicates the drawer title. */
function previewMarkdown(raw: string, title?: string): string {
  let text = (raw || "").replace(/^\uFEFF/, "");
  text = text.replace(/^---[ \t]*\r?\n[\s\S]*?\r?\n---[ \t]*\r?\n?/, "");
  const heading = title?.trim();
  if (heading) {
    const escaped = heading.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    text = text.replace(new RegExp(`^#\\s+${escaped}\\s*(?:\\r?\\n)+`), "");
  }
  return text.trimStart();
}

export function GraphPage() {
  const { mode } = useThemeMode();
  const light = mode === "light";
  const shellRef = useRef<HTMLDivElement>(null);
  const hostRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<NotesGraphView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [payload, setPayload] = useState<GraphPayload | null>(null);
  const [selected, setSelected] = useState<GraphNodeData | null>(null);
  const [doc, setDoc] = useState<NoteDoc | null>(null);
  const [docLoading, setDocLoading] = useState(false);
  const [docError, setDocError] = useState<string | null>(null);

  const colors = themeColors(light);
  const empty = !loading && !error && (payload?.nodes.length || 0) === 0;
  const showGraph = !loading && !error && !empty;
  const previewSource = useMemo(
    () => previewMarkdown(doc?.content || "", selected?.title || doc?.title),
    [doc?.content, doc?.title, selected?.title],
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api<GraphPayload>("/api/v1/notes/graph");
      setPayload(data);
    } catch (err) {
      setPayload({ nodes: [], edges: [], stats: { notes: 0, links: 0 } });
      setError(err instanceof Error ? err.message : "图谱加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!selected) {
      setDoc(null);
      setDocError(null);
      setDocLoading(false);
      return;
    }
    if (selected.exists === false) {
      setDoc({
        ok: true,
        id: selected.id,
        title: selected.title,
        path: selected.path,
        exists: false,
        content: "",
      });
      setDocError(null);
      setDocLoading(false);
      return;
    }

    let cancelled = false;
    setDocLoading(true);
    setDocError(null);
    void api<NoteDoc>(`/api/v1/notes/doc?id=${encodeURIComponent(selected.id)}`)
      .then((payload) => {
        if (!cancelled) setDoc(payload);
      })
      .catch((err) => {
        if (!cancelled) {
          setDoc(null);
          setDocError(err instanceof Error ? err.message : "文档加载失败");
        }
      })
      .finally(() => {
        if (!cancelled) setDocLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selected]);

  useEffect(() => {
    const host = hostRef.current;
    const shell = shellRef.current;
    if (!host || !shell || !showGraph || !payload) return;

    const view = new NotesGraphView(host, colors);
    view.onSelect = setSelected;
    viewRef.current = view;

    const measure = () => {
      const r = shell.getBoundingClientRect();
      return {
        w: Math.max(320, Math.floor(r.width)),
        h: Math.max(320, Math.floor(r.height)),
      };
    };

    const { w, h } = measure();
    view.mount(w, h);
    view.setData(payload.nodes, payload.edges);

    const ro = new ResizeObserver(() => {
      const next = measure();
      view.resize(next.w, next.h);
    });
    ro.observe(shell);

    return () => {
      ro.disconnect();
      view.destroy();
      if (viewRef.current === view) viewRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showGraph, payload]);

  useEffect(() => {
    viewRef.current?.setColors(colors);
  }, [colors]);

  useEffect(() => {
    viewRef.current?.setPointerActive(!selected);
  }, [selected]);

  const closeDrawer = () => setSelected(null);

  return (
    <div className="page-stack graph-page" data-tour="page-graph">
      <div className="graph-shell" ref={shellRef}>
        <div
          className="graph-canvas-host"
          ref={hostRef}
          style={{ display: showGraph ? "block" : "none" }}
        />
        {loading ? (
          <Flex className="graph-overlay" align="center" justify="center">
            <Spin />
          </Flex>
        ) : error ? (
          <Flex className="graph-overlay" align="center" justify="center">
            <Empty description={error} />
          </Flex>
        ) : empty ? (
          <Flex className="graph-overlay" align="center" justify="center">
            <Empty description="notes 目录还没有 Markdown 笔记" />
          </Flex>
        ) : null}
      </div>

      <Drawer
        open={!!selected}
        onClose={closeDrawer}
        width={Math.min(560, typeof window !== "undefined" ? window.innerWidth - 24 : 560)}
        placement="left"
        closable={false}
        destroyOnClose
        mask
        maskClosable
        rootClassName="graph-doc-drawer"
        styles={{
          mask: { background: "rgba(0, 0, 0, 0.35)" },
        }}
        title={
          <div className="graph-doc-header">
            <Title level={5} className="graph-doc-title">
              {selected?.title || doc?.title || "笔记"}
            </Title>
            <Button type="text" size="small" icon={<CloseOutlined />} onClick={closeDrawer} />
          </div>
        }
      >
        {docLoading ? (
          <Flex align="center" justify="center" style={{ minHeight: 160 }}>
            <Spin />
          </Flex>
        ) : docError ? (
          <Empty description={docError} />
        ) : selected?.exists === false || doc?.exists === false ? (
          <Empty description="这是未落盘的占位节点，还没有对应 Markdown 文件" />
        ) : (
          <div className="graph-doc-body" data-color-mode={light ? "light" : "dark"}>
            <MarkdownPreview
              source={previewSource}
              style={{ background: "transparent", padding: 0 }}
            />
          </div>
        )}
      </Drawer>
    </div>
  );
}
