import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { fileURLToPath } from "node:url";

const rootDir = path.dirname(fileURLToPath(import.meta.url));

/** Single Admin SPA → desk-pet App Dist only (not served by Runtime HTTP). */
export default defineConfig({
  plugins: [
    react(),
    {
      name: "strip-crossorigin",
      transformIndexHtml(html: string) {
        // WebView / custom protocols choke on module CORS; strip Vite's crossorigin attrs.
        return html.replace(/\s+crossorigin(?:=(?:"[^"]*"|'[^']*'|[^\s>]+))?/g, "");
      },
    },
  ],
  base: "./",
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8766",
    },
  },
  build: {
    outDir: path.resolve(rootDir, "../../../desktop/web/console"),
    emptyOutDir: true,
    assetsDir: "assets",
  },
});
