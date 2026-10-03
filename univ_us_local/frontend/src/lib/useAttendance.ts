"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAppData } from "@/components/app/AppData";
import { useToast } from "@/components/ui/Toast";
import { api } from "./api";
import {
  applyPatch,
  LEVEL_RANK,
  type SessionPatch,
  type AttAlert,
  type AttCourse,
  type Attendance,
  type AttendanceOverview,
  type AttTotals,
  type CourseSettings,
  type Meeting,
  type TimetableImportState,
} from "./attendance";

// F3 출결 — /attendance 화면 데이터. 계산은 백엔드(바꾸는 요청이 다시 계산한 과목을 돌려준다)에서만 한다.
// 칩을 누르면 먼저 칸을 채우고(낙관적), 응답의 숫자로 막대·상태를 바꾼다. 실패하면 되돌리고 토스트(8-8).
// /api/status 의 attendance.updatedAt 이 바뀌면(다른 화면·캘린더에서 찍음, 시간표 가져오기 완료) 다시 부른다.

const msg = (e: unknown) => (e instanceof Error ? e.message : String(e));

/** 합계 — 서버 overview.totals 와 같은 모양. 과목 하나만 바뀐 응답을 합칠 때 다시 센다(규칙이 아니라 합산만). */
export function totalsOf(courses: AttCourse[]): AttTotals {
  const live = courses.filter((c) => !c.excluded);
  const risky = live
    .filter((c) => c.summary.level === "danger" || c.summary.level === "over")
    .sort((a, b) => LEVEL_RANK[b.summary.level!] - LEVEL_RANK[a.summary.level!]);
  const worst = live.reduce<AttCourse["summary"]["level"]>(
    (w, c) => (c.summary.level && (!w || LEVEL_RANK[c.summary.level] > LEVEL_RANK[w]) ? c.summary.level : w),
    null,
  );
  return {
    courses: live.length,
    withTimetable: live.filter((c) => c.timetable.meetings.length).length,
    needsTimetable: live.filter((c) => !c.timetable.meetings.length).map((c) => c.short),
    unchecked: live.reduce((n, c) => n + c.summary.uncheckedSessions, 0),
    risky: risky.map((c) => ({
      id: c.id,
      name: c.short,
      level: c.summary.level!,
      levelLabel: c.summary.levelLabel,
      remaining: c.summary.remaining,
      spareSessions: c.summary.spareSessions,
    })),
    caution: live.filter((c) => c.summary.level === "caution").map((c) => c.short),
    worstLevel: worst,
    worstLabel: worst ? { safe: "안전", caution: "주의", danger: "위험", over: "초과" }[worst] : "—",
    sessions: live.reduce((n, c) => n + c.sessions.length, 0),
  };
}

export function useAttendance(semester?: string) {
  const toast = useToast();
  const { status: appStatus, refresh: refreshApp } = useAppData();
  const [data, setData] = useState<AttendanceOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const semId = data?.semester.id; // 보고 있는 학기 — 바꾸는 요청이 이 학기로 간다
  const have = useRef<string | null | undefined>(undefined); // 화면이 가진 데이터의 updatedAt

  const showAlerts = useCallback(
    (alerts: AttAlert[] | undefined) => {
      for (const a of alerts ?? []) toast(`${a.title} — ${a.body}`, { tone: a.level === "caution" ? "default" : "error", duration: 8000 });
    },
    [toast],
  );

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const o = await api.attendance(semester);
      setData(o);
      have.current = o.updatedAt;
      setError(null);
      showAlerts(o.alerts);
    } catch (e) {
      setError(msg(e));
    } finally {
      setBusy(false);
    }
  }, [semester, showAlerts]);

  useEffect(() => {
    void Promise.resolve().then(load);
  }, [load]);

  // 도장(stamp)이 바뀐 때만 본다 — 내가 방금 받은 값(have)과 같으면 다시 부르지 않는다(칩 하나에 요청 한 번)
  const stamp = appStatus?.attendance?.updatedAt;
  const lastStamp = useRef<string | null | undefined>(undefined);
  useEffect(() => {
    if (stamp === undefined) return;
    if (lastStamp.current !== undefined && stamp !== lastStamp.current && stamp !== have.current) void Promise.resolve().then(load);
    lastStamp.current = stamp;
  }, [stamp, load]);

  /** 서버가 다시 계산한 과목들로 바꾼다 (캘린더·타일도 바뀌므로 AppData 도) */
  const accept = useCallback(
    (courses: AttCourse[], updatedAt: string | null | undefined, alerts?: AttAlert[]) => {
      setData((d) => {
        if (!d) return d;
        const byId = new Map(courses.map((c) => [c.id, c]));
        const known = new Set(d.courses.map((c) => c.id));
        const next = [...d.courses.map((c) => byId.get(c.id) ?? c), ...courses.filter((c) => !known.has(c.id))];
        return { ...d, courses: next, totals: totalsOf(next), updatedAt: updatedAt ?? d.updatedAt };
      });
      if (updatedAt) have.current = updatedAt;
      showAlerts(alerts);
      void refreshApp();
    },
    [refreshApp, showAlerts],
  );

  const patchLocal = useCallback((courseId: string, fn: (c: AttCourse) => AttCourse) => {
    let before: AttendanceOverview | null = null;
    setData((d) => {
      before = d;
      return d ? { ...d, courses: d.courses.map((c) => (c.id === courseId ? fn(c) : c)) } : d;
    });
    return () => setData(before);
  }, []);

  /** 칩 한 번 — 출결 · 휴강 · 휴강 풀고 출결 (AttendanceChips 가 만든 patch 그대로) */
  const mark = useCallback(
    async (courseId: string, sessionId: string, patch: SessionPatch) => {
      const undo = patchLocal(courseId, (c) => applyPatch(c, sessionId, patch));
      try {
        const r = await api.patchSession(sessionId, patch);
        accept([r.course], r.updatedAt, r.alerts);
        return true;
      } catch (e) {
        undo();
        toast(`저장하지 못했습니다: ${msg(e)}`, { tone: "error" });
        return false;
      }
    },
    [patchLocal, accept, toast],
  );

  const setMemo = useCallback(
    async (sessionId: string, memo: string) => {
      try {
        const r = await api.patchSession(sessionId, { memo });
        accept([r.course], r.updatedAt);
      } catch (e) {
        toast(`메모를 저장하지 못했습니다: ${msg(e)}`, { tone: "error" });
      }
    },
    [accept, toast],
  );

  const bulk = useCallback(
    async (items: { id: string; attendance: Attendance }[]) => {
      try {
        const r = await api.bulkAttendance(items);
        accept(r.courses, r.updatedAt, r.alerts);
        return r;
      } catch (e) {
        toast(`저장하지 못했습니다: ${msg(e)}`, { tone: "error" });
        return null;
      }
    },
    [accept, toast],
  );

  const addMakeup = useCallback(
    async (body: { courseId: string; date: string; periods: number[]; memo?: string }) => {
      try {
        const r = await api.addMakeup(body, semId);
        accept([r.course], r.updatedAt, r.alerts);
        return true;
      } catch (e) {
        toast(`보강을 추가하지 못했습니다: ${msg(e)}`, { tone: "error" });
        return false;
      }
    },
    [accept, toast, semId],
  );

  const deleteMakeup = useCallback(
    async (id: string) => {
      try {
        const r = await api.deleteMakeup(id);
        accept([r.course], r.updatedAt);
      } catch (e) {
        toast(`지우지 못했습니다: ${msg(e)}`, { tone: "error" });
      }
    },
    [accept, toast],
  );

  const patchCourse = useCallback(
    async (
      id: string,
      body: Partial<CourseSettings> & { adjust?: { absent?: number; late?: number }; excluded?: boolean; name?: string; code?: string; section?: string },
    ) => {
      try {
        const r = await api.patchAttCourse(id, body, semId);
        accept([r.course], r.updatedAt, r.alerts);
        return true;
      } catch (e) {
        toast(`저장하지 못했습니다: ${msg(e)}`, { tone: "error" });
        return false;
      }
    },
    [accept, toast, semId],
  );

  const saveTimetable = useCallback(
    async (courses: { courseId: string; meetings: Meeting[] }[], validFrom?: string | null) => {
      try {
        const r = await api.putTimetable({ semester: semId, validFrom, courses });
        accept(r.courses, r.updatedAt, r.alerts);
        return r.generated;
      } catch (e) {
        toast(`시간표를 저장하지 못했습니다: ${msg(e)}`, { tone: "error" });
        return null;
      }
    },
    [accept, toast, semId],
  );

  const revertTimetable = useCallback(
    async (courseId: string) => {
      try {
        const r = await api.revertTimetable(courseId, semId);
        accept(r.courses, undefined);
        toast("자동으로 찾은 시간표로 되돌렸습니다", { tone: "success" });
      } catch (e) {
        toast(`되돌리지 못했습니다: ${msg(e)}`, { tone: "error" });
      }
    },
    [accept, toast, semId],
  );

  const addCourse = useCallback(
    async (body: { name: string; code?: string; section?: string; meetings?: Meeting[] }) => {
      try {
        const r = await api.addAttCourse(body, semId);
        accept([r.course], undefined);
        return true;
      } catch (e) {
        toast(`과목을 추가하지 못했습니다: ${msg(e)}`, { tone: "error" });
        return false;
      }
    },
    [accept, toast, semId],
  );

  const deleteCourse = useCallback(
    async (id: string) => {
      try {
        await api.deleteAttCourse(id, semId);
        await load();
        void refreshApp();
      } catch (e) {
        toast(`지우지 못했습니다: ${msg(e)}`, { tone: "error" });
      }
    },
    [load, refreshApp, toast, semId],
  );

  const setSemester = useCallback(
    async (body: { start?: string | null; end?: string | null; holidays?: { date: string; name: string }[] }) => {
      if (!data) return false;
      try {
        await api.putAttSemester({ semester: data.semester.id, ...body });
        await load();
        void refreshApp();
        return true;
      } catch (e) {
        toast(`저장하지 못했습니다: ${msg(e)}`, { tone: "error" });
        return false;
      }
    },
    [data, load, refreshApp, toast],
  );

  const savePeriods = useCallback(
    async (body: Parameters<typeof api.putPeriods>[0] | null) => {
      try {
        if (body) await api.putPeriods(body);
        else await api.resetPeriods();
        await load();
        void refreshApp();
        return true;
      } catch (e) {
        toast(`교시 시각을 저장하지 못했습니다: ${msg(e)}`, { tone: "error" });
        return false;
      }
    },
    [load, refreshApp, toast],
  );

  return {
    data,
    error,
    loading: data === null && !error,
    busy,
    reload: load,
    mark,
    setMemo,
    bulk,
    addMakeup,
    deleteMakeup,
    patchCourse,
    saveTimetable,
    revertTimetable,
    addCourse,
    deleteCourse,
    setSemester,
    savePeriods,
  };
}

export type AttendanceApi = ReturnType<typeof useAttendance>;

/** 시간표 자동으로 가져오기 (F3-R02) — 학사정보시스템 시간표 조회(로그인 불필요)를 백엔드가 돈다. 과목당 1.5초. */
export function useTimetableImport(onDone: () => Promise<void> | void) {
  const toast = useToast();
  const { status: appStatus } = useAppData();
  const [state, setState] = useState<TimetableImportState | null>(null);
  const alive = useRef(true);
  useEffect(
    () => () => {
      alive.current = false;
    },
    [],
  );

  const start = useCallback(
    async (semester?: string) => {
      try {
        let st = await api.startTimetableImport(semester);
        if (alive.current) setState(st);
        if (st.error && !st.running) {
          toast(st.error, { tone: "error" });
          return;
        }
        if (st.alreadyRunning) toast("시간표를 이미 가져오는 중입니다");
        for (let i = 0; i < 120 && st.running; i++) {
          await new Promise((res) => setTimeout(res, 1500));
          st = await api.timetableImportState();
          if (alive.current) setState(st);
        }
        await onDone();
        const r = st.result;
        if (st.ok && r) {
          const parts = [`${r.found}/${r.total}과목을 찾았습니다`];
          if (r.kept.length) parts.push(`내가 고친 ${r.kept.length}과목은 그대로 두었습니다`);
          if (r.missing.length + r.errors.length) parts.push(`못 찾은 ${r.missing.length + r.errors.length}과목은 직접 넣어 주세요`);
          toast(parts.join(" · "), { tone: r.missing.length + r.errors.length ? "default" : "success", duration: 7000 });
        } else if (st.error) toast(st.error, { tone: "error" });
      } catch (e) {
        toast(`시간표를 가져오지 못했습니다: ${msg(e)}`, { tone: "error" });
      }
    },
    [onDone, toast],
  );

  const running = !!state?.running || !!appStatus?.attendance?.import?.running;
  return { state, running, start };
}
