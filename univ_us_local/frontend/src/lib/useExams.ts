"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAppData } from "@/components/app/AppData";
import { useToast } from "@/components/ui/Toast";
import { api } from "./api";
import type { Difficulty, ExamDetail, ExamInput, ExamsOverview, PlanOptionsInput, PlanPreview, StudyPlan } from "./exams";

// F5 시험 공부 일정 — /exams 화면 데이터. 계산·판정은 전부 서버(F5_Test_agent)가 만든 값을 그대로 쓴다.
// e클래스 수집(F6)이 끝나 /api/status 의 exams.updatedAt 이 바뀌면(새 공지에서 시험을 찾았다) 자동으로 다시 부른다.
//
// 캘린더를 바꾸는 것은 등록·완료 체크·옮기기·취소뿐이다 → 그때만 AppData(/api/events)를 다시 부른다.
// 미리보기(preview)·재조정(rebalance)은 계산만 하므로 아무것도 다시 부르지 않는다 (F5 D3 · 5절).

const msg = (e: unknown) => (e instanceof Error ? e.message : String(e));

export interface UseExams {
  data: ExamsOverview | null;
  loading: boolean;
  error: string | null;
  busy: boolean;
  reload: () => Promise<void>;
  /** e클래스 공지에서 시험 다시 찾기 (F5-R01) */
  sync: () => Promise<void>;
  addExam: (body: ExamInput) => Promise<boolean>;
  patchExam: (id: string, body: Partial<ExamInput> & { status?: "confirmed" | "review" }) => Promise<boolean>;
  /** 발표 준비 완료 체크·해제 (2026-10-06) */
  setReady: (id: string, ready: boolean) => Promise<boolean>;
  /** 확인 필요 카드의 '맞아요' — 승인만 한다 (F5-S02) */
  confirmExam: (id: string) => Promise<boolean>;
  deleteExam: (id: string) => Promise<boolean>;
  /** 과목별 시험 유무 — 끄면 임의 일정을 치우고, 켜면 바로 다시 잡는다 */
  setCourseExams: (courseId: string, body: { midterm?: boolean; final?: boolean }) => Promise<boolean>;
  /** 난이도 시간 설정 — 쪽당 분 */
  saveDifficulty: (values: Partial<Record<Difficulty, number | null>>) => Promise<boolean>;
  createPlan: (examId: string, options: PlanOptionsInput) => Promise<StudyPlan | null>;
  patchDay: (planId: string, date: string, body: { done?: boolean; date?: string }) => Promise<boolean>;
  cancelPlan: (planId: string) => Promise<boolean>;
}

export function useExams(semester?: string | null): UseExams {
  const toast = useToast();
  const { status, refresh } = useAppData();
  const [data, setData] = useState<ExamsOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const stamp = status?.exams?.updatedAt ?? null;
  const seen = useRef<string | null | undefined>(undefined);

  const load = useCallback(async () => {
    try {
      const d = await api.exams({ semester });
      setData(d);
      seen.current = d.updatedAt;
      setError(null);
    } catch (e) {
      setError(msg(e));
    } finally {
      setLoading(false);
    }
  }, [semester]);

  useEffect(() => {
    void Promise.resolve().then(load);
  }, [load]);

  // 다른 화면에서 e클래스 동기화가 끝났다 → 공지에서 새 시험을 찾았을 수 있다
  useEffect(() => {
    if (seen.current !== undefined && stamp !== seen.current) void Promise.resolve().then(load);
  }, [stamp, load]);

  /** 캘린더(/api/events)·타일까지 바뀌는 변경 뒤에 부른다 */
  const reloadAll = useCallback(async () => {
    await Promise.all([load(), refresh()]);
  }, [load, refresh]);

  const run = useCallback(
    async <T,>(fn: () => Promise<T>, fail: string): Promise<T | null> => {
      setBusy(true);
      try {
        return await fn();
      } catch (e) {
        toast(`${fail}: ${msg(e)}`, { tone: "error" });
        return null;
      } finally {
        setBusy(false);
      }
    },
    [toast],
  );

  const sync = useCallback(async () => {
    const out = await run(() => api.syncExams(), "공지를 읽지 못했습니다");
    if (!out) return;
    if (!out.available) {
      toast(out.error ?? "e클래스 공지를 읽을 수 없습니다 — 먼저 e클래스 동기화를 하세요", { tone: "error" });
      return;
    }
    await reloadAll();
    const found = out.new + out.updated;
    toast(
      found
        ? `공지 ${out.posts}건에서 시험 ${out.new}건을 찾았습니다${out.updated ? ` · ${out.updated}건 갱신` : ""}`
        : `공지 ${out.posts}건을 읽었습니다 — 새로 찾은 시험이 없습니다`,
      { tone: found ? "success" : undefined },
    );
    for (const p of out.postponed) {
      toast(`${p.course} ${p.typeLabel} 날짜가 ${p.from} → ${p.to} 로 바뀌었습니다 — 계획을 다시 만드세요`, { tone: "error" });
    }
    for (const p of out.confirmed ?? []) {
      // 임의로 잡아 둔 자리에 진짜 일정이 나왔다 — 연기가 아니다
      const moved = p.from !== p.to;
      toast(
        `${p.course} ${p.typeLabel} 일정이 나왔습니다: ${p.to}${p.time ? ` ${p.time}` : ""}${moved ? ` (임의 ${p.from} 대신)` : ""}${
          p.planned && moved ? " — 계획을 다시 만드세요" : ""
        }`,
        { tone: p.planned && moved ? "error" : "success" },
      );
    }
  }, [reloadAll, run, toast]);

  const addExam = useCallback(
    async (body: ExamInput) => {
      const out = await run(() => api.addExam(body), "시험을 넣지 못했습니다");
      if (!out) return false;
      await reloadAll();
      toast(`${out.exam.course} ${out.exam.typeLabel}을(를) 넣었습니다`, { tone: "success" });
      return true;
    },
    [reloadAll, run, toast],
  );

  const patchExam = useCallback(
    async (id: string, body: Partial<ExamInput> & { status?: "confirmed" | "review" }) => {
      const out = await run(() => api.patchExam(id, body), "저장하지 못했습니다");
      if (!out) return false;
      await reloadAll();
      // 범위·날짜가 바뀌면 등록된 계획의 전제가 달라진다 (F5 8절)
      if (out.exam.planStale) toast(out.exam.planStale.message, { tone: "error" });
      return true;
    },
    [reloadAll, run, toast],
  );

  const confirmExam = useCallback(
    async (id: string) => {
      const out = await run(() => api.patchExam(id, { status: "confirmed" }), "승인하지 못했습니다");
      if (!out) return false;
      await reloadAll();
      toast(`${out.exam.course} ${out.exam.typeLabel} — 확인했습니다`, { tone: "success" });
      return true;
    },
    [reloadAll, run, toast],
  );

  const setReady = useCallback(
    async (id: string, ready: boolean) => {
      const out = await run(() => api.setExamReady(id, ready), "저장하지 못했습니다");
      if (!out) return false;
      await load(); // 캘린더는 그대로다 — 목록만 다시 받는다
      toast(ready ? `${out.exam.course} ${out.exam.title} — 준비 완료` : `${out.exam.course} ${out.exam.title} — 준비 완료를 풀었습니다`, {
        tone: ready ? "success" : undefined,
      });
      return true;
    },
    [load, run, toast],
  );

  const deleteExam = useCallback(
    async (id: string) => {
      const out = await run(() => api.deleteExam(id), "지우지 못했습니다");
      if (!out) return false;
      await reloadAll();
      toast(out.note || `시험을 지웠습니다${out.plansRemoved ? ` (학습 계획 ${out.plansRemoved}개도 함께)` : ""}`);
      return true;
    },
    [reloadAll, run, toast],
  );

  const setCourseExams = useCallback(
    async (courseId: string, body: { midterm?: boolean; final?: boolean }) => {
      const out = await run(() => api.patchExamCourse(courseId, body), "바꾸지 못했습니다");
      if (!out) return false;
      await reloadAll();
      const made = out.created.map((x) => `${x.label} ${x.date.slice(5).replace("-", "/")}`);
      if (made.length) toast(`임의 일정을 잡았습니다 — ${made.join(", ")}`, { tone: "success" });
      else if (out.removed.length) toast(`${out.removed.map((x) => x.label).join(", ")} — 임의 일정을 치웠습니다`);
      return true;
    },
    [reloadAll, run, toast],
  );

  const saveDifficulty = useCallback(
    async (values: Partial<Record<Difficulty, number | null>>) => {
      const out = await run(() => api.putExamSettings(values), "저장하지 못했습니다");
      if (!out) return false;
      await load();
      toast(`난이도 시간: ${out.difficulties.map((d) => `${d.label} ${d.pageMinutes}분`).join(" · ")} (쪽당)`, { tone: "success" });
      return true;
    },
    [load, run, toast],
  );

  const createPlan = useCallback(
    async (examId: string, options: PlanOptionsInput) => {
      const out = await run(() => api.createPlan(examId, options), "등록하지 못했습니다");
      if (!out) return null;
      await reloadAll();
      // 공부 계획은 공부 캘린더에만 들어간다 — 그 페이지는 Next 라우트가 아니라 서버가 주는 페이지라 주소로 연다
      toast(out.message, { tone: "success", action: { label: "공부 캘린더 보기", onClick: () => window.location.assign(new URL("/study-calendar", window.location.origin).href) } });
      return out.plan;
    },
    [reloadAll, run, toast],
  );

  const patchDay = useCallback(
    async (planId: string, date: string, body: { done?: boolean; date?: string }) => {
      const out = await run(() => api.patchPlanDay(planId, date, body), "저장하지 못했습니다");
      if (!out) return false;
      await reloadAll();
      if (out.plan.state === "done") toast("이 계획을 다 끝냈습니다", { tone: "success" });
      return true;
    },
    [reloadAll, run, toast],
  );

  const cancelPlan = useCallback(
    async (planId: string) => {
      const out = await run(() => api.cancelPlan(planId), "취소하지 못했습니다");
      if (!out) return false;
      await reloadAll();
      toast(out.message);
      return true;
    },
    [reloadAll, run, toast],
  );

  return {
    data,
    loading,
    error,
    busy,
    reload: load,
    sync,
    addExam,
    patchExam,
    confirmExam,
    setReady,
    deleteExam,
    setCourseExams,
    saveDifficulty,
    createPlan,
    patchDay,
    cancelPlan,
  };
}

/** 시험 하나 — 계획 옵션 기본값과 범위 후보(주차·자료)까지 (F5-S04). 패널을 열 때만 부른다. */
export function useExamDetail(examId: string | null): { detail: ExamDetail | null; loading: boolean; error: string | null; reload: () => Promise<void> } {
  const [detail, setDetail] = useState<ExamDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!examId) {
      setDetail(null);
      return;
    }
    setLoading(true);
    try {
      setDetail(await api.exam(examId));
      setError(null);
    } catch (e) {
      setError(msg(e));
    } finally {
      setLoading(false);
    }
  }, [examId]);

  useEffect(() => {
    void Promise.resolve().then(load);
  }, [load]);

  return { detail, loading, error, reload: load };
}

/** 미리보기 — 옵션을 바꿀 때마다 서버에 계산을 맡긴다. **저장하지 않는다** (F5-R30). */
export function usePlanPreview(): {
  preview: PlanPreview | null;
  calculating: boolean;
  error: string | null;
  calc: (examId: string, options: PlanOptionsInput) => Promise<PlanPreview | null>;
  rebalance: (planId: string, options?: PlanOptionsInput) => Promise<PlanPreview | null>;
  clear: () => void;
} {
  const [preview, setPreview] = useState<PlanPreview | null>(null);
  const [calculating, setCalculating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const seq = useRef(0);

  const guard = useCallback(async (fn: () => Promise<PlanPreview>) => {
    const my = ++seq.current;
    setCalculating(true);
    setError(null);
    try {
      const p = await fn();
      if (my !== seq.current) return null; // 더 최근 계산이 있다 — 늦게 온 결과로 덮지 않는다
      setPreview(p);
      return p;
    } catch (e) {
      if (my === seq.current) {
        setError(msg(e));
        setPreview(null);
      }
      return null;
    } finally {
      if (my === seq.current) setCalculating(false);
    }
  }, []);

  return {
    preview,
    calculating,
    error,
    calc: useCallback((examId, options) => guard(() => api.previewPlan(examId, options)), [guard]),
    rebalance: useCallback((planId, options = {}) => guard(() => api.rebalancePlan(planId, options)), [guard]),
    clear: useCallback(() => {
      seq.current++;
      setPreview(null);
      setError(null);
    }, []),
  };
}
