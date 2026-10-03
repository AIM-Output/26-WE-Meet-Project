"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAppData } from "@/components/app/AppData";
import { useToast } from "@/components/ui/Toast";
import { api } from "./api";
import type { CourseInput, CoursePatch, CertState, GradImportState, GraduationStatus } from "./graduation";

// F2 졸업요건 — /graduation 화면 데이터. 계산은 백엔드(POST·PATCH 가 다시 계산한 status 를 돌려준다)에서만 한다.
// /api/status 의 graduation.updatedAt 이 바뀌면(프로필 변경·가져오기 완료) 다시 부른다(Frontend-Route 6-9 규칙).

const msg = (e: unknown) => (e instanceof Error ? e.message : String(e));

export function useGraduation(track: string) {
  const toast = useToast();
  const { status: appStatus, refresh: refreshApp } = useAppData();
  const [data, setData] = useState<GraduationStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false); // 갱신 중 — 이전 숫자를 두고 얇은 진행 표시

  const load = useCallback(async () => {
    setBusy(true);
    try {
      setData(await api.graduation(track));
      setError(null);
    } catch (e) {
      setError(msg(e));
    } finally {
      setBusy(false);
    }
  }, [track]);

  useEffect(() => {
    void Promise.resolve().then(load);
  }, [load]);

  const stamp = appStatus?.graduation?.updatedAt;
  const seen = useRef<string | null | undefined>(undefined);
  useEffect(() => {
    if (stamp === undefined) return;
    if (seen.current !== undefined && seen.current !== stamp && stamp !== data?.updatedAt) void Promise.resolve().then(load);
    seen.current = stamp;
  }, [stamp, data?.updatedAt, load]);

  /** 서버가 다시 계산한 결과로 바꾼다 (타일 숫자도 바뀌므로 /api/status 도) */
  const accept = useCallback(
    (s: GraduationStatus) => {
      setData(s);
      seen.current = s.updatedAt;
      void refreshApp();
    },
    [refreshApp],
  );

  const patchCourse = useCallback(
    async (id: string, body: CoursePatch) => {
      const before = data;
      if (body.area !== undefined || body.excluded !== undefined)
        setData((d) =>
          d
            ? {
                ...d,
                courses: d.courses.map((c) =>
                  c.id !== id
                    ? c
                    : {
                        ...c,
                        ...(body.area !== undefined ? { area: body.area, areaSetBy: body.area ? "user" : c.areaSetBy } : {}),
                        ...(body.excluded !== undefined ? { excludedByUser: body.excluded, excluded: body.excluded || (!!c.excludedReason && !c.excludedByUser) } : {}),
                      },
                ),
              }
            : d,
        );
      try {
        const r = await api.patchGradCourse(id, body, track);
        accept(r.status);
        return r;
      } catch (e) {
        setData(before);
        toast(`저장하지 못했습니다: ${msg(e)}`, { tone: "error" });
        return null;
      }
    },
    [data, track, accept, toast],
  );

  const addCourse = useCallback(
    async (body: CourseInput) => {
      try {
        const r = await api.addGradCourse(body, track);
        accept(r.status);
        return r.id;
      } catch (e) {
        toast(`추가하지 못했습니다: ${msg(e)}`, { tone: "error" });
        return null;
      }
    },
    [track, accept, toast],
  );

  const deleteCourse = useCallback(
    async (id: string) => {
      try {
        await api.deleteGradCourse(id);
        await load();
        void refreshApp();
        return true;
      } catch (e) {
        toast(`지우지 못했습니다: ${msg(e)}`, { tone: "error" });
        return false;
      }
    },
    [load, refreshApp, toast],
  );

  const setCert = useCallback(
    async (key: string, body: { state?: CertState; memo?: string }) => {
      setData((d) => (d ? { ...d, certifications: d.certifications.map((c) => (c.key === key ? { ...c, ...body } : c)) } : d));
      try {
        await api.setCert(key, body);
        await load();
        void refreshApp();
      } catch (e) {
        toast(`저장하지 못했습니다: ${msg(e)}`, { tone: "error" });
        void load();
      }
    },
    [load, refreshApp, toast],
  );

  return { data, error, loading: data === null && !error, busy, reload: load, patchCourse, addCourse, deleteCourse, setCert };
}

/** 학사정보시스템 기이수성적 가져오기 (F2-R01·R02) — C3_Login_agent 의 로그인 세션으로 로컬에서 돈다. */
export function useGradImport(onDone: () => Promise<void> | void) {
  const toast = useToast();
  const { status: appStatus, refreshProfile, refresh } = useAppData();
  const [state, setState] = useState<GradImportState | null>(null);
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
        const r = await api.startGradImport(interactive);
        if ("conflict" in r) {
          setProblem({ message: r.conflict, needLogin: r.needLogin });
          return;
        }
        setState(r);
        if (interactive) toast("로그인 창이 열립니다 — 학교 계정으로 로그인하면 이어서 가져옵니다");
        else if (r.alreadyRunning) toast("이수 내역을 이미 가져오는 중입니다");
        let st = r;
        for (let i = 0; i < 400 && st.running; i++) {
          await new Promise((res) => setTimeout(res, 2000));
          st = await api.gradImportState();
          if (alive.current) setState(st);
        }
        if (st.ok) {
          await onDone();
          void Promise.all([refreshProfile(), refresh()]);
          const r2 = st.result;
          toast(
            r2 ? `이수 내역을 가져왔습니다 — ${r2.count}과목${r2.added ? ` (새로 ${r2.added})` : ""}${r2.profile?.changed?.length ? " · 평점·학점도 프로필에 반영" : ""}` : "이수 내역을 가져왔습니다",
            { tone: "success" },
          );
        } else if (st.needLogin) setProblem({ message: st.error ?? "학사정보시스템 로그인이 필요합니다", needLogin: true });
        else if (st.error) setProblem({ message: st.error, needLogin: false });
      } catch (e) {
        setProblem({ message: msg(e), needLogin: false });
      }
    },
    [onDone, refreshProfile, refresh, toast],
  );

  // 다른 화면(/settings/sources)에서 시작한 가져오기도 버튼을 막는다
  const running = !!state?.running || !!appStatus?.graduation?.import?.running;
  return { state, running, problem, start };
}
