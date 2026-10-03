"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAppData } from "@/components/app/AppData";
import { useToast } from "@/components/ui/Toast";
import { api } from "./api";
import { FIELD_LABEL, type DeptEntry, type ImportState, type MasterSummary } from "./profile";

// C2 프로필 — 서버(C2_Profile_agent)에 있고, AppDataProvider 가 한 번 불러 모든 화면이 나눠 쓴다.
export function useProfile() {
  const { profile: doc, profileError, updateProfile, refreshProfile } = useAppData();
  const p = doc?.profile ?? null;
  return {
    doc,
    profile: p,
    loading: doc === null && !profileError,
    error: profileError,
    update: updateProfile,
    refresh: refreshProfile,
    complete: !!doc?.complete,
    /** 항목 출처 칩 — 'auto'(학사시스템) · 'edited'(자동값을 내가 고침) · null */
    source: (key: string): "auto" | "edited" | null =>
      doc?.edited.includes(key) ? "edited" : doc?.filledBy[key] === "auto" ? "auto" : null,
  };
}

// 학과 마스터 — 한 번 받아 두고 같이 쓴다(600여 줄, 로컬 JSON 이라 네트워크 없이 뜬다 — Frontend-Route 5-2).
let masterCache: (MasterSummary & { entries: DeptEntry[] }) | null = null;
let masterPromise: Promise<MasterSummary & { entries: DeptEntry[] }> | null = null;

export function useDepartments() {
  const toast = useToast();
  const [data, setData] = useState(masterCache);
  const [error, setError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);

  const load = useCallback(async (force = false) => {
    try {
      if (force || !masterPromise) masterPromise = api.departments();
      masterCache = await masterPromise;
      setData(masterCache);
      setError(null);
    } catch (e) {
      masterPromise = null;
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    if (!masterCache) void Promise.resolve().then(() => load());
  }, [load]);

  /** 교육과정검색에서 다시 받기 (1분 남짓) — 끝날 때까지 2초마다 본다 */
  const sync = useCallback(async () => {
    setSyncing(true);
    try {
      await api.syncDepartments();
      for (let i = 0; i < 120; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        const st = await api.masterStatus();
        if (!st.sync.running) {
          if (st.sync.ok) {
            await load(true);
            toast(`학과 목록을 갱신했습니다 — ${st.sync.result?.count ?? st.count}곳`, { tone: "success" });
          } else toast(`학과 목록을 받지 못했습니다: ${st.sync.error ?? "알 수 없는 오류"} — 기존 목록을 계속 씁니다`, { tone: "error" });
          break;
        }
      }
    } catch (e) {
      toast(`학과 목록 갱신 실패: ${e instanceof Error ? e.message : String(e)}`, { tone: "error" });
    } finally {
      setSyncing(false);
    }
  }, [load, toast]);

  return { data, entries: data?.entries ?? [], error, syncing, sync, reload: () => load(true) };
}

// 학사정보시스템에서 가져오기 (C2-R04) — C3_Login_agent 의 로그인 세션으로 로컬에서 돈다.
export function useProfileImport() {
  const toast = useToast();
  const { refreshProfile, refresh, refreshAcademic } = useAppData();
  const [state, setState] = useState<ImportState | null>(null);
  const [problem, setProblem] = useState<{ message: string; needLogin: boolean } | null>(null);
  const alive = useRef(true);
  useEffect(
    () => () => {
      alive.current = false;
    },
    [],
  );

  const start = useCallback(
    async (interactive = false) => {
      setProblem(null);
      try {
        const r = await api.startImport(interactive);
        if ("conflict" in r) {
          setProblem({ message: r.conflict, needLogin: r.needLogin });
          return;
        }
        setState(r);
        if (interactive) toast("로그인 창이 열립니다 — 학교 계정으로 로그인하면 이어서 가져옵니다");
        let st = r;
        for (let i = 0; i < 400 && st.running; i++) {
          await new Promise((res) => setTimeout(res, 2000));
          st = await api.importState();
          if (alive.current) setState(st);
        }
        if (st.ok) {
          await refreshProfile();
          void Promise.all([refresh(), refreshAcademic()]);
          const got = st.result?.found.map((k) => FIELD_LABEL[k] ?? k) ?? [];
          const skipped = st.result?.skipped.map((k) => FIELD_LABEL[k] ?? k) ?? [];
          toast(`가져왔습니다 — ${got.join(" · ") || "새로 바뀐 항목 없음"}${skipped.length ? ` (내가 입력한 ${skipped.join("·")} 은(는) 그대로 둠)` : ""}`, {
            tone: "success",
          });
        } else if (st.needLogin) setProblem({ message: st.error ?? "학사정보시스템 로그인이 필요합니다", needLogin: true });
        else if (st.error) setProblem({ message: st.error, needLogin: false });
      } catch (e) {
        setProblem({ message: e instanceof Error ? e.message : String(e), needLogin: false });
      }
    },
    [refreshProfile, refresh, refreshAcademic, toast],
  );

  return { state, running: !!state?.running, problem, start };
}
