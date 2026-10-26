import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { fileURLToPath } from "node:url";

const rootDir = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig(({ mode }) => {
  /** Desk-pet embeds this build as a native second window (not an external browser URL). */
  const forPet = mode === "pet";
  return {
    plugins: [react()],
    base: forPet ? "./" : "/admin/",
    server: {
      port: 5173,
      proxy: {
        "/api": "http://127.0.0.1:8766",
      },
    },
    build: {
      outDir: forPet
        ? path.resolve(rootDir, "../../../desktop/web/console")
        : path.resolve(rootDir, "../static"),
      emptyOutDir: true,
      assetsDir: "assets",
    },
  };
});
