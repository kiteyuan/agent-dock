import { describe, expect, it } from "vitest";

import { displayPath, hardwareHint, itemState, missingLicenses } from "./moduleState";
import { serviceText, serviceTone } from "./serviceStatus";
import type { ModuleItem, ServiceItem } from "./types";

function mod(overrides: Partial<ModuleItem>): ModuleItem {
  return {
    id: "x",
    platform_compatible: true,
    installed: true,
    ...overrides,
  } as ModuleItem;
}

describe("itemState", () => {
  it("prioritises platform incompatibility", () => {
    expect(itemState("agent", mod({ platform_compatible: false, installed: false }))).toEqual({
      text: "不支持",
      tone: "error",
    });
  });

  it("asks for pending licenses before install", () => {
    const item = mod({
      installed: false,
      licenses: [{ requires_acceptance: true, accepted: false }],
    } as Partial<ModuleItem>);
    expect(itemState("tts", item).text).toBe("需确认");
    expect(missingLicenses(item)).toHaveLength(1);
  });

  it("flags unconfigured model agents", () => {
    const item = mod({ configuration: { mode: "model" }, configured: false } as Partial<ModuleItem>);
    expect(itemState("agent", item).text).toBe("未配置");
  });

  it("reports a stopped sidecar", () => {
    expect(itemState("stt", mod({ sidecar_id: "s", running: false })).text).toBe("未启动");
  });

  it("marks the selected engine as in use", () => {
    expect(itemState("tts", mod({ ready: true, selected: true }))).toEqual({
      text: "使用中",
      tone: "success",
    });
  });
});

describe("helpers", () => {
  it("shortens long paths to the last two segments", () => {
    expect(displayPath("C:\\a\\b\\c\\d")).toBe("…/c/d");
    expect(displayPath("a/b")).toBe("a/b");
  });

  it("prefers VRAM over RAM hints", () => {
    expect(hardwareHint(mod({ hardware: { min_vram_gb: 6, min_ram_gb: 16 } } as Partial<ModuleItem>))).toBe(
      "≥ 6 GB 显存",
    );
  });

  it("maps service health to text and tone", () => {
    const blocked = { healthy: false, blocked_reason: "missing" } as ServiceItem;
    expect(serviceText(blocked)).toBe("未安装");
    expect(serviceTone(blocked)).toBe("warning");
    expect(serviceTone({ healthy: false } as ServiceItem)).toBe("error");
  });
});
