import type { ServiceItem } from "./types";

export function serviceText(service: ServiceItem): string {
  if (service.healthy) return service.detail || "正常";
  if (service.blocked_reason) return "未安装";
  return service.detail || "未就绪";
}

export function serviceTone(
  service: ServiceItem,
): "success" | "warning" | "error" {
  if (service.healthy) return "success";
  if (service.blocked_reason || service.expected === false) return "warning";
  return "error";
}
