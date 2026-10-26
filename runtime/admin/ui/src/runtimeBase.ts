/** API / asset bases for Admin UI.

Production: desk-pet console on loopback :8767 — `api()` uses allowlisted Tauri
`admin_api` invoke (no HTTP from the page). Vite `npm run dev` has no
`__TAURI__` and uses relative `/api` via the Vite proxy.
*/

declare global {
  interface Window {
    __TAURI__?: {
      core?: { invoke?: (cmd: string, args?: Record<string, unknown>) => Promise<unknown> };
    };
    __AGENTDOCK_API_BASE__?: string;
  }
}

export function isTauriHost(): boolean {
  return typeof window !== "undefined" && typeof window.__TAURI__?.core?.invoke === "function";
}

export function apiBase(): string {
  if (typeof window === "undefined") return "";
  const override = String(window.__AGENTDOCK_API_BASE__ || "").trim().replace(/\/$/, "");
  if (override) return override;
  return "";
}

export function assetUrl(path: string): string {
  const rel = path.replace(/^\//, "");
  const base = import.meta.env.BASE_URL || "/";
  if (base.endsWith("/")) return `${base}${rel}`;
  return `${base}/${rel}`;
}
