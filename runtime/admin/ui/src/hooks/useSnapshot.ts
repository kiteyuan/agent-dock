import { useCallback, useEffect, useRef, useState } from "react";
import { message } from "antd";
import { api } from "../api";
import type { Snapshot } from "../types";

export function useSnapshot() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [online, setOnline] = useState(false);
  const [loading, setLoading] = useState(true);
  const inFlight = useRef(false);
  const hasSnapshot = useRef(false);

  const refresh = useCallback(async (force = false) => {
    if (inFlight.current) return;
    if (!force && document.hidden) return;
    inFlight.current = true;
    try {
      const data = await api<Snapshot>(
        force ? "/api/v1/snapshot?discover=1" : "/api/v1/snapshot",
      );
      setSnapshot(data);
      hasSnapshot.current = true;
      setOnline(true);
    } catch (error) {
      setOnline(false);
      if (!hasSnapshot.current) {
        message.error(error instanceof Error ? error.message : "无法连接 Runtime");
      }
    } finally {
      setLoading(false);
      inFlight.current = false;
    }
  }, []);

  useEffect(() => {
    void refresh(true);
    const timer = window.setInterval(() => void refresh(), 3000);
    const onVisible = () => {
      if (!document.hidden) void refresh(true);
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [refresh]);

  return { snapshot, online, loading, refresh };
}
