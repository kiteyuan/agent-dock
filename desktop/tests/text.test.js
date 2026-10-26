import { describe, expect, it } from "vitest";

import { escapeHtml, normalizeReply, renderInlineMarkdown, renderMarkdown } from "../web/js/text.js";

describe("agent reply rendering is injection-safe", () => {
  const payloads = [
    "<script>alert(1)</script>",
    '<img src=x onerror="alert(1)">',
    "<svg onload=alert(1)>",
    '"><iframe src="https://evil.example">',
  ];

  for (const p of payloads) {
    it(`escapes raw HTML: ${p}`, () => {
      for (const out of [renderMarkdown(p), renderInlineMarkdown(p)]) {
        expect(out).not.toMatch(/<(script|img|svg|iframe)\b/i);
        expect(out).toContain("&lt;");
      }
    });
  }

  it("only links http(s) URLs", () => {
    expect(renderMarkdown("[x](javascript:alert(1))")).not.toContain("href=");
    expect(renderMarkdown("[x](data:text/html,hi)")).not.toContain("href=");
    const ok = renderMarkdown("[docs](https://example.com/a)");
    expect(ok).toContain('href="https://example.com/a"');
    expect(ok).toContain('rel="noopener noreferrer"');
  });

  it("cannot break out of the href attribute", () => {
    const out = renderMarkdown('[x](https://a.example/"onmouseover="alert(1))');
    expect(out).not.toMatch(/"\s*onmouseover=/);
  });
});

describe("text helpers", () => {
  it("escapes the HTML metacharacters", () => {
    expect(escapeHtml(`<a href="x">&</a>`)).toBe("&lt;a href=&quot;x&quot;&gt;&amp;&lt;/a&gt;");
  });

  it("normalizes newlines and trims blank edges", () => {
    expect(normalizeReply("\r\n\nhi  \n\n\n\nthere\n")).toBe("hi\n\nthere");
  });
});
