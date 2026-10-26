/** API / asset bases for Admin UI.

Browser Admin (served from Runtime at /admin/) uses same-origin relative paths.
Desk-pet console window is a Tauri App page; it must call Runtime over loopback HTTP.
*/

declare global {
  interface Window {
    __TAURI__?: unknown;
    __AGENTDOCK_API_BASE__?: string;
  }
}

export function apiBase(): string {
  if (typeof window === "undefined") return "";
  const override = String(window.__AGENTDOCK_API_BASE__ || "").trim().replace(/\/$/, "");
  if (override) return override;
  if (window.__TAURI__) return "http://127.0.0.1:8766";
  return "";
}

export function assetUrl(path: string): string {
  const rel = path.replace(/^\//, "");
  const base = import.meta.env.BASE_URL || "/";
  if (base.endsWith("/")) return `${base}${rel}`;
  return `${base}/${rel}`;
}
