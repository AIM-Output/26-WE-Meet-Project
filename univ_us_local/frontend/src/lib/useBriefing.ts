"use client";

import { useCallback, useEffect, useState } from "react";
import { useAppData } from "@/components/app/AppData";
import { api } from "./api";
import type { Briefing, BriefingToday } from "./briefing";

// C4 오늘 브리핑 — GET /api/briefing/today. 다시 부르는 때: /api/status 의 briefing.state·updatedAt 이 바뀔 때
// (서버가 08:00 에 만들었다 · 수집을 기다리다 만들었다 · 다시 만들었다 · 설정이 바뀌었다). 화면은 스냅샷을 그리기만 한다.

export function useBriefingToday() {
  const { status } = useAppData();
  const b = status?.briefing;
  const stamp = b ? `${b.state}|${b.updatedAt ?? ""}|${b.today?.date ?? ""}` : "";
  const [data, setData] = useState<BriefingToday | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    try {
      setData(await api.briefingToday());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void Promise.resolve().then(reload);
  }, [reload, stamp]);

  /** 다시 만들기 — 끝나면 그 스냅샷으로 바로 바꾼다 */
  const regenerate = useCallback(async (): Promise<Briefing> => {
    const next = await api.regenerateBriefing();
    setData((d) => (d ? { ...d, state: d.state === "off" ? "off" : "ready", briefing: next } : d));
    return next;
  }, []);

  return { data, error, loading, reload, regenerate };
}
