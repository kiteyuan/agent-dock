// Builds the Admin console SPA into desktop/web/console (gitignored).
// Invoked by Tauri beforeDevCommand / beforeBuildCommand.
//   node scripts/build-console.mjs           # skip when output is newer than sources
//   node scripts/build-console.mjs --force   # always rebuild (release builds)
import { spawnSync } from "node:child_process";
import { existsSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const desktopDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const uiDir = path.resolve(desktopDir, "../runtime/admin/ui");
const outIndex = path.join(desktopDir, "web/console/index.html");
const force = process.argv.includes("--force");

function newestMtime(p) {
  if (!existsSync(p)) return 0;
  const st = statSync(p);
  if (!st.isDirectory()) return st.mtimeMs;
  let newest = st.mtimeMs;
  for (const name of readdirSync(p)) newest = Math.max(newest, newestMtime(path.join(p, name)));
  return newest;
}

function npm(args) {
  const res = spawnSync("npm", args, { cwd: uiDir, stdio: "inherit", shell: process.platform === "win32" });
  if (res.status !== 0) process.exit(res.status ?? 1);
}

if (!existsSync(path.join(uiDir, "node_modules"))) {
  npm(["ci", "--no-audit", "--no-fund"]);
}

const sources = ["src", "index.html", "public", "package-lock.json", "vite.config.ts"].map((p) => path.join(uiDir, p));
const fresh = existsSync(outIndex) && statSync(outIndex).mtimeMs >= Math.max(...sources.map(newestMtime));
if (fresh && !force) {
  console.log("[console] up to date — skip build");
} else {
  npm(["run", "build"]);
}
