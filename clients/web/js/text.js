/** Normalize newlines for reply storage — keeps markdown structure. */
export function normalizeReply(raw) {
  return String(raw || "")
    .replace(/\r\n/g, "\n")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .replace(/^\n+/, "")
    .replace(/\n+$/, "");
}

/** @deprecated Prefer normalizeReply for display; TTS stripping is on Runtime. */
export function plainText(raw) {
  return normalizeReply(raw);
}

export function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function inlineMarkdown(escaped) {
  let s = escaped;
  s = s.replace(/`([^`\n]+)`/g, '<code class="md-code">$1</code>');
  s = s.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/__([^_\n]+)__/g, "<strong>$1</strong>");
  s = s.replace(/\*([^*\n]+)\*/g, "<em>$1</em>");
  s = s.replace(/_([^_\n]+)_/g, "<em>$1</em>");
  s = s.replace(/~~([^~\n]+)~~/g, "<del>$1</del>");
  s = s.replace(
    /\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g,
    '<a class="md-link" href="$2" target="_blank" rel="noopener noreferrer">$1</a>'
  );
  return s;
}

/**
 * Safe subset markdown → HTML (escape first).
 * Covers: fences, inline code, bold/italic, links, headings, lists, quotes, hr.
 */
export function renderMarkdown(raw) {
  const src = normalizeReply(raw);
  if (!src) return "";

  const lines = src.split("\n");
  const out = [];
  let i = 0;
  let para = [];

  const flushPara = () => {
    if (!para.length) return;
    const body = inlineMarkdown(escapeHtml(para.join("\n"))).replace(/\n/g, "<br />");
    out.push(`<p class="md-p">${body}</p>`);
    para = [];
  };

  while (i < lines.length) {
    const line = lines[i];

    // Fenced code
    const fence = line.match(/^```([\w-]*)\s*$/);
    if (fence) {
      flushPara();
      i += 1;
      const codeLines = [];
      while (i < lines.length && !/^```\s*$/.test(lines[i])) {
        codeLines.push(lines[i]);
        i += 1;
      }
      if (i < lines.length) i += 1; // closing ```
      out.push(
        `<pre class="md-pre"><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`
      );
      continue;
    }

    if (/^\s*$/.test(line)) {
      flushPara();
      i += 1;
      continue;
    }

    if (/^(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      flushPara();
      out.push('<hr class="md-hr" />');
      i += 1;
      continue;
    }

    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      flushPara();
      const level = heading[1].length;
      out.push(
        `<h${level} class="md-h">${inlineMarkdown(escapeHtml(heading[2]))}</h${level}>`
      );
      i += 1;
      continue;
    }

    if (/^>\s?/.test(line)) {
      flushPara();
      const quote = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) {
        quote.push(lines[i].replace(/^>\s?/, ""));
        i += 1;
      }
      out.push(
        `<blockquote class="md-quote">${inlineMarkdown(escapeHtml(quote.join("\n"))).replace(/\n/g, "<br />")}</blockquote>`
      );
      continue;
    }

    if (/^\s*[-*+]\s+/.test(line)) {
      flushPara();
      const items = [];
      while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*+]\s+/, ""));
        i += 1;
      }
      out.push(
        `<ul class="md-list">${items
          .map((t) => `<li>${inlineMarkdown(escapeHtml(t))}</li>`)
          .join("")}</ul>`
      );
      continue;
    }

    if (/^\s*\d+\.\s+/.test(line)) {
      flushPara();
      const items = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*\d+\.\s+/, ""));
        i += 1;
      }
      out.push(
        `<ol class="md-list">${items
          .map((t) => `<li>${inlineMarkdown(escapeHtml(t))}</li>`)
          .join("")}</ol>`
      );
      continue;
    }

    para.push(line);
    i += 1;
  }
  flushPara();
  return out.join("");
}

export function captionSep(prev, next) {
  if (!prev) return "";
  const last = prev.slice(-1);
  if (/\s/.test(last)) return "";
  if (/[\u3000-\u303F\u4E00-\u9FFF\uFF00-\uFFEF。！？…」』）】#*`>\-]/.test(last)) {
    return "";
  }
  const first = String(next || "").slice(0, 1);
  if (!first || /[\n，。！？、；：…」』）】,.!?;:#*`>\-]/.test(first)) return "";
  return " ";
}

export function clipProcess(s, max = 72) {
  const t = String(s || "").replace(/\s+/g, " ").trim();
  if (t.length <= max) return t;
  return "…" + t.slice(-(max - 1));
}

/** Native payload text only — no invented labels. */
export function nativeProcessText(type, payload = {}) {
  const content = String(payload.content || payload.text || "").trim();
  if (content) return content;
  if (type === "agent.tool_call") {
    const tool = String(payload.tool || "").trim();
    const args = payload.args;
    if (args && typeof args === "object" && Object.keys(args).length) {
      try {
        const dumped = JSON.stringify(args);
        return tool ? `${tool} ${dumped}` : dumped;
      } catch (_) {
        return tool;
      }
    }
    return tool;
  }
  return "";
}
