"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api } from "@/lib/api";
import type { CalEvent, Course, Status } from "@/lib/types";
import { useToast } from "@/components/ui/Toast";

// 모든 화면이 같이 보는 실제 데이터(e클래스 마감·내 일정·과목·동기화 상태).
// 동기화 버튼은 여러 화면에 있어도 실행은 하나 — /api/status 하나를 보고 함께 비활성된다(Frontend-Route 11-5).
// 폴링: 동기화 중 3초, 평소 60초. updated_at 이 바뀌었을 때만 일정을 다시 부른다.

interface AppData {
  events: CalEvent[];
  courses: Course[];
  status: Status | null;
  loading: boolean;
  error: string | null;
  syncing: boolean;
  courseColor: (idOrName: string) => string | undefined;
  refresh: () => Promise<void>;
  startSync: () => Promise<void>;
  setEvents: React.Dispatch<React.SetStateAction<CalEvent[]>>;
}

const Ctx = createContext<AppData | null>(null);

export function useAppData(): AppData {
  const v = useContext(Ctx);
  if (!v) throw new Error("AppDataProvider 가 없습니다");
  return v;
}

// sync.py 종료 코드 → 문구 (코드 의미는 eclass_agent/sync.py 머리 주석)
export function syncResultMessage(code: number | null): { text: string; ok: boolean } {
  switch (code) {
    case 0:
      return { text: "e클래스 동기화 완료", ok: true };
    case 2:
      return { text: "e클래스 로그인이 필요합니다 — eclass_agent 의 login.cmd 를 실행하세요", ok: false };
    case 3:
      return { text: "다른 동기화가 이미 진행 중이라 건너뛰었습니다", ok: true };
    case null:
      return { text: "동기화 종료 — sync.log 를 확인하세요", ok: false };
    default:
      return { text: `동기화 실패 (코드 ${code}) — sync.log 를 확인하세요`, ok: false };
  }
}

export function AppDataProvider({ children }: { children: ReactNode }) {
  const toast = useToast();
  const [events, setEvents] = useState<CalEvent[]>([]);
  const [courses, setCourses] = useState<Course[]>([]);
  const [status, setStatus] = useState<Status | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const lastUpdated = useRef<string | null | undefined>(undefined);

  const refresh = useCallback(async () => {
    try {
      const [ev, st, cs] = await Promise.all([api.events(), api.status(), api.courses()]);
      setEvents(ev);
      setStatus(st);
      setCourses(cs);
      lastUpdated.current = st.updated_at;
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void Promise.resolve().then(refresh);
  }, [refresh]);

  const running = !!status?.sync.running;
  useEffect(() => {
    const id = window.setInterval(
      async () => {
        try {
          const st = await api.status();
          const wasRunning = running;
          setStatus(st);
          setError(null);
          if (wasRunning && !st.sync.running) {
            await refresh();
            const r = syncResultMessage(st.sync.exit_code);
            toast(r.text, { tone: r.ok ? "success" : "error" });
          } else if (st.updated_at !== lastUpdated.current) {
            await refresh();
          }
        } catch (e) {
          setError(e instanceof Error ? e.message : String(e));
        }
      },
      running ? 3000 : 60_000,
    );
    return () => window.clearInterval(id);
  }, [running, refresh, toast]);

  const startSync = useCallback(async () => {
    try {
      const st = await api.startSync();
      setStatus((prev) => (prev ? { ...prev, sync: st } : prev));
      if (st.error) toast(st.error, { tone: "error" });
      else if (st.already_running)
        toast(st.source === "external" ? "예약 동기화가 이미 진행 중입니다 — 끝나면 알려드립니다" : "이미 동기화가 진행 중입니다");
      else toast("e클래스 동기화를 시작했습니다");
    } catch (e) {
      toast(`동기화를 시작하지 못했습니다: ${e instanceof Error ? e.message : String(e)}`, { tone: "error" });
    }
  }, [toast]);

  const colorMap = useMemo(() => {
    const m = new Map<string, string>();
    for (const c of courses) {
      m.set(c.id, c.color);
      m.set(c.short, c.color);
      m.set(c.name, c.color);
    }
    return m;
  }, [courses]);

  const courseColor = useCallback(
    (key: string) => colorMap.get(key) ?? [...colorMap.entries()].find(([k]) => k.startsWith(key.replace(/\[.*$/, "")))?.[1],
    [colorMap],
  );

  const value = useMemo<AppData>(
    () => ({ events, courses, status, loading, error, syncing: running, courseColor, refresh, startSync, setEvents }),
    [events, courses, status, loading, error, running, courseColor, refresh, startSync],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
