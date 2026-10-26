import type { JobResult } from "./types";
import { apiBase, isTauriHost } from "./runtimeBase";

export class ApiError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ApiError";
  }
}

type AdminApiProxyResult = {
  status: number;
  body: string;
};

type InvokeFn = (cmd: string, args?: Record<string, unknown>) => Promise<unknown>;

async function resolveInvoke(): Promise<InvokeFn | null> {
  for (let i = 0; i < 40; i++) {
    const fn = window.__TAURI__?.core?.invoke;
    if (typeof fn === "function") return fn.bind(window.__TAURI__!.core);
    await new Promise((r) => setTimeout(r, 50));
  }
  return null;
}

async function apiViaHost(
  path: string,
  options: RequestInit,
): Promise<Response> {
  const invoke = await resolveInvoke();
  if (!invoke) {
    throw new ApiError("桌宠宿主桥接未就绪（__TAURI__/admin_api）");
  }
  const method = (options.method || "GET").toUpperCase();
  let body: string | null = null;
  if (options.body != null) {
    body = typeof options.body === "string" ? options.body : String(options.body);
  }
  const result = (await invoke("admin_api", {
    method,
    path,
    body,
  })) as AdminApiProxyResult;
  return new Response(result.body, {
    status: result.status,
    headers: { "Content-Type": "application/json" },
  });
}

export async function api<T = JobResult>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const useHost = isTauriHost() || typeof window.__TAURI__ !== "undefined";
  const response = useHost
    ? await apiViaHost(path, options)
    : await fetch(`${apiBase()}${path}`, {
        headers: { "Content-Type": "application/json", ...(options.headers || {}) },
        ...options,
      });
  const payload = (await response.json().catch(() => ({}))) as JobResult & {
    ok?: boolean;
    detail?: string;
  };
  if (!response.ok || payload.ok === false) {
    throw new ApiError(payload.error || payload.detail || `请求失败 (${response.status})`);
  }
  return payload as T;
}

export async function waitJob(
  jobId: string,
  onProgress?: (message: string, percent: number) => void,
): Promise<JobResult> {
  while (true) {
    await new Promise((resolve) => setTimeout(resolve, 450));
    const job = await api<JobResult>(`/api/v1/jobs/${encodeURIComponent(jobId)}`);
    onProgress?.(job.message || "处理中", Math.round((job.progress || 0) * 100));
    if (job.state === "done") return job.result || job;
    if (job.state === "error" || job.state === "cancelled") {
      throw new ApiError(job.result?.error || job.message || "操作没有完成");
    }
  }
}

export async function submitAction(
  kind: string,
  id: string,
  action: string,
  onProgress?: (message: string, percent: number) => void,
): Promise<JobResult> {
  const result = await api(
    `/api/v1/modules/${encodeURIComponent(kind)}/${encodeURIComponent(id)}/${action}`,
    { method: "POST", body: "{}" },
  );
  if (!result.job_id) return result;
  return waitJob(result.job_id, onProgress);
}
