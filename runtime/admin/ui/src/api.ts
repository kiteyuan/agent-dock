import type { JobResult } from "./types";

export class ApiError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ApiError";
  }
}

export async function api<T = JobResult>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(path, {
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
