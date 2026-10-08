"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import { BookOpen, CalendarDays, Gauge, Plus, RefreshCw, Target, X } from "lucide-react";
import { Page, PageHeader, Section } from "@/components/ui/Layout";
import { Banner, EmptyState, ErrorPanel, SkeletonCards } from "@/components/ui/Feedback";
import { Chip, DdayChip, CourseChip } from "@/components/ui/Chip";
import { Modal } from "@/components/ui/Modal";
import { Tabs } from "@/components/ui/Tabs";
import { useToast } from "@/components/ui/Toast";
import { CourseExamsModal } from "@/components/exams/CourseExamsModal";
import { DifficultyModal } from "@/components/exams/DifficultyModal";
import { ExamCard } from "@/components/exams/ExamCard";
import { StudyMaterialsModal } from "@/components/exams/StudyMaterialsModal";
import { ExamForm } from "@/components/exams/ExamForm";
import { PlanOptions } from "@/components/exams/PlanOptions";
import { PlanPreviewPanel } from "@/components/exams/PlanPreview";
import { ProgressPanel } from "@/components/exams/ProgressPanel";
import { closeQuery, navigateQuery, useQueryParam, useQueryValue } from "@/lib/useQueryState";
import { useIsXl } from "@/lib/useMediaQuery";
import { useExamDetail, useExams, usePlanPreview } from "@/lib/useExams";
import { hm, isPrep, type Exam, type ExamDetail, type ExamInput, type ExamsOverview, type PlanDay, type PlanOptionsInput, type PlanPreview } from "@/lib/exams";
import { parseLocal } from "@/lib/dates";

// /exams — 시험 목록 + 오른쪽 패널(옵션 → 미리보기 → 진도). 페이지를 옮기지 않고 `?exam=&step=` 으로 이어진다(10-2).
// 미리보기와 등록을 나눈다 — 캘린더를 바꾸는 것은 `등록하기` 뿐이다 (F5 D3).
// 계산·판정·경고 문구는 전부 서버(F5_Test_agent)가 만든 값을 그대로 그린다 (F5-R26).

const STEPS = ["options", "preview", "progress"] as const;
type Step = (typeof STEPS)[number];

/** 미리보기 결과 → 다음 계산·등록에 쓸 옵션. 화면이 본 것과 등록되는 것이 어긋나지 않게. */
function optionsOf(p: PlanPreview): PlanOptionsInput {
  return {
    unit: p.unit,
    totalPages: p.totalPages,
    totalMinutes: p.totalMinutes,
    pageMinutes: p.pageMinutes,
    difficulty: p.difficulty,
    reviewDays: p.reviewDays,
    excludedDates: p.excludedDates,
    includeQuiz: p.includeQuiz,
    quizCount: p.quizCount,
    scopeWeeks: p.scopeWeeks,
    scopeMaterialIds: p.scopeMaterialIds,
    // 날짜 — 달력에서 고른 날이면 그 날들을, 아니면 학습일 수를 (남은 날 전부면 비워 둔다: 날이 지나도 자연스럽게 줄게)
    ...(p.studyDatesPicked
      ? { studyDates: p.studyDates, studyDays: null }
      : { studyDates: [], studyDays: p.studyDays && p.studyDays < p.studyPool ? p.studyDays : null }),
    // 날마다 정한 시간 — 학습일이 아닌 날의 값은 서버가 걸러 준 것으로 맞춘다
    dayMinutes: p.dayMinutes ?? {},
  };
}

export default function ExamsPage() {
  const examId = useQueryValue("exam");
  const editId = useQueryValue("edit");
  const adding = useQueryValue("new") === "exam";
  const setup = useQueryValue("setup");
  const studyId = useQueryValue("study");      // 자료 체크 창 (2026-10-06)
  const settingUp = setup === "courses";
  const [review, setReview] = useQueryParam("review", "0", ["0", "1"] as const);
  const [semester, setSemester] = useState<string | null>(null);
  const ex = useExams(semester);
  const { data, loading, error, busy } = ex;
  const isXl = useIsXl();
  const [pendingDelete, setPendingDelete] = useState<Exam | null>(null);

  const all = useMemo(() => (data ? [...data.exams, ...data.past] : []), [data]);
  // 발표는 계획 패널이 없다(준비 완료만) — 옛 링크로 열려도 패널을 띄우지 않는다
  const selected = all.find((e) => e.id === examId && !isPrep(e)) ?? null;
  const editing = all.find((e) => e.id === editId) ?? null;
  const list = review === "1" ? (data?.review ?? []) : (data?.exams ?? []);

  // 시험이 사라졌는데 패널이 열려 있으면 닫는다 (다른 창에서 지웠을 때)
  useEffect(() => {
    if (examId && data && !selected) closeQuery(["exam", "step"]);
  }, [examId, data, selected]);

  const submitExam = useCallback(
    async (body: ExamInput, id?: string) => (id ? ex.patchExam(id, body) : ex.addExam(body)),
    [ex],
  );

  return (
    <Page wide>
      <PageHeader
        icon={<Target />}
        title="시험·발표"
        subtitle={data ? `${data.semester.label} · 다가오는 시험·발표 ${data.counts.upcoming}건` : undefined}
        meta={
          data && data.semesters.length > 1 ? (
            <select
              className="field field-sm w-auto"
              aria-label="학기"
              value={semester ?? data.semester.id}
              onChange={(e) => setSemester(e.target.value)}
            >
              {data.semesters.map((s) => (
                <option key={s} value={s}>
                  {s.replace("-", "-")}학기
                </option>
              ))}
            </select>
          ) : undefined
        }
        actions={
          <>
            {/* 공부만 보는 캘린더 — F5_Test_agent/web 에 있는 페이지를 이 서버가 /study-calendar 로 준다 */}
            <a className="btn btn-sm" href="/study-calendar">
              <CalendarDays aria-hidden />
              공부 캘린더
            </a>
            <button type="button" className="btn btn-sm" onClick={() => navigateQuery({ setup: "difficulty" }, "push")}>
              <Gauge aria-hidden />
              난이도 시간 설정
            </button>
            <button type="button" className="btn btn-sm" onClick={() => void ex.sync()} disabled={busy}>
              <RefreshCw aria-hidden />
              공지에서 찾기
            </button>
            <button type="button" className="btn btn-primary btn-sm" onClick={() => navigateQuery({ new: "exam" }, "push")}>
              <Plus aria-hidden />
              시험·발표 추가
            </button>
          </>
        }
      />

      <div className="mb-5 space-y-3">
        {data && !data.source.eclass.available && (
          <Banner tone="info">e클래스 공지를 아직 받지 않았습니다 — 대시보드에서 e클래스 동기화를 한 번 하면 시험을 자동으로 찾습니다.</Banner>
        )}
        {data && data.counts.review > 0 && review !== "1" && (
          <Banner
            tone="warn"
            action={
              <button type="button" className="btn btn-sm" onClick={() => setReview("1")}>
                확인하러 가기
              </button>
            }
          >
            공지에서 찾은 시험 {data.counts.review}건 — 확인이 필요합니다
          </Banner>
        )}
        {data?.defaults?.hints.map((h) => (
          <Banner key={h} tone="neutral">
            {h}
          </Banner>
        ))}
        {data?.defaults && data.defaults.auto > 0 && review !== "1" && (
          <Banner
            tone="neutral"
            action={
              <button type="button" className="btn btn-sm" onClick={() => navigateQuery({ setup: "courses" }, "push")}>
                과목별 시험
              </button>
            }
          >
            임의 일정 {data.defaults.auto}건 — 일정이 아직 안 나온 시험은 학사일정 수업평가 기간
            {data.defaults.periods.midterm.window &&
              `(중간 ${data.defaults.periods.midterm.window[0].slice(5).replace("-", "/")}~${data.defaults.periods.midterm.window[1]
                .slice(5)
                .replace("-", "/")})`}{" "}
            안의 수업 요일로 잡아 두었습니다. 공지가 나오면 바뀝니다. 시험이 없는 과목은 끄세요.
          </Banner>
        )}
        {review === "1" && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setReview("0")}>
            ← 전체 시험으로
          </button>
        )}
        {data && data.today.blocks.length > 0 && <TodayStrip today={data.today} />}
      </div>

      {error ? (
        <ErrorPanel message={`시험·발표를 불러오지 못했습니다: ${error}`} onRetry={() => void ex.reload()} />
      ) : (
        <div className={`grid gap-5 ${selected && isXl ? "grid-cols-[minmax(0,1fr)_480px]" : ""}`}>
          <div className="space-y-3">
            {loading ? (
              <SkeletonCards count={3} />
            ) : list.length === 0 ? (
              <EmptyState
                icon={<Target />}
                title={review === "1" ? "확인이 필요한 시험이 없습니다" : "등록된 시험·발표가 없습니다"}
                action={
                  review === "1" ? undefined : (
                    <>
                      <button type="button" className="btn btn-sm" onClick={() => void ex.sync()} disabled={busy}>
                        <RefreshCw aria-hidden />
                        공지에서 찾기
                      </button>
                      <button type="button" className="btn btn-primary btn-sm" onClick={() => navigateQuery({ new: "exam" }, "push")}>
                        <Plus aria-hidden />
                        시험·발표 추가
                      </button>
                    </>
                  )
                }
              >
                {review === "1" ? "공지에서 찾은 시험을 모두 확인했습니다" : "e클래스 공지에서 자동으로 찾거나 직접 추가하세요"}
              </EmptyState>
            ) : (
              list.map((e) => (
                <ExamCard
                  key={e.id}
                  e={e}
                  active={e.id === examId}
                  busy={busy}
                  onConfirm={() => void ex.confirmExam(e.id)}
                  onReady={(r) => void ex.setReady(e.id, r)}
                  onEdit={() => navigateQuery({ edit: e.id }, "push")}
                  onDelete={() => setPendingDelete(e)}
                />
              ))
            )}

            {review !== "1" && data && data.past.length > 0 && (
              <details className="card px-4 py-3">
                <summary className="cursor-pointer text-[14px] font-semibold text-muted">지난 시험 {data.past.length}건</summary>
                <div className="mt-3 space-y-3">
                  {data.past.map((e) => (
                    <ExamCard
                      key={e.id}
                      e={e}
                      active={e.id === examId}
                      busy={busy}
                      onConfirm={() => void ex.confirmExam(e.id)}
                      onReady={(r) => void ex.setReady(e.id, r)}
                      onEdit={() => navigateQuery({ edit: e.id }, "push")}
                      onDelete={() => setPendingDelete(e)}
                    />
                  ))}
                </div>
              </details>
            )}
          </div>

          <AnimatePresence>
            {selected && isXl && (
              <motion.aside
                key={selected.id}
                initial={{ opacity: 0, x: 16 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 16 }}
                transition={{ type: "spring", bounce: 0, visualDuration: 0.25 }}
              >
                <div className="sticky top-[calc(var(--header-h)+16px)] max-h-[calc(100dvh-var(--header-h)-32px)] overflow-y-auto overscroll-contain rounded-2xl">
                  <PlanPanel exam={selected} data={data} ex={ex} />
                </div>
              </motion.aside>
            )}
          </AnimatePresence>
        </div>
      )}

      {/* 좁은 화면: 계획 단계는 전체 화면 시트로 (10-9) */}
      <Modal
        open={!!selected && !isXl}
        onClose={() => closeQuery(["exam", "step"])}
        title={selected ? `${selected.course} ${selected.typeLabel}` : ""}
        size="lg"
      >
        {selected && <PlanPanel exam={selected} data={data} ex={ex} bare />}
      </Modal>

      <StudyMaterialsModal
        examId={studyId}
        onClose={() => closeQuery(["study"])}
        onChanged={() => void ex.reload()}
        onReplan={(id) => navigateQuery({ study: null, exam: id, step: "options" }, "replace")}
      />

      <DifficultyModal
        open={setup === "difficulty"}
        rows={data?.difficulties ?? []}
        busy={busy}
        onClose={() => closeQuery(["setup"])}
        onSave={(v) => ex.saveDifficulty(v)}
      />

      <CourseExamsModal
        open={settingUp}
        rows={data?.courseSettings ?? []}
        periods={data?.defaults?.periods ?? null}
        hints={data?.defaults?.hints ?? []}
        busy={busy}
        loading={!data}
        onClose={() => closeQuery(["setup"])}
        onChange={(cid, body) => void ex.setCourseExams(cid, body)}
      />

      <ExamForm open={adding || !!editing} exam={editing} busy={busy} onClose={() => closeQuery([editing ? "edit" : "new"])} onSubmit={submitExam} />

      <Modal
        open={!!pendingDelete}
        onClose={() => setPendingDelete(null)}
        title="시험을 지울까요?"
        footer={
          <>
            <button type="button" className="btn" onClick={() => setPendingDelete(null)}>
              취소
            </button>
            <button
              type="button"
              className="btn btn-danger"
              disabled={busy}
              onClick={async () => {
                const e = pendingDelete;
                if (!e) return;
                if (await ex.deleteExam(e.id)) setPendingDelete(null);
              }}
            >
              지우기
            </button>
          </>
        }
      >
        {pendingDelete && (
          <div className="space-y-2 pt-1 text-[14px]">
            <p>
              <b className="font-semibold">
                {pendingDelete.course} {pendingDelete.typeLabel}
              </b>{" "}
              ({pendingDelete.date})
            </p>
            {pendingDelete.plan && <p className="text-muted">등록된 학습 계획과 캘린더의 학습 블록도 함께 지워집니다.</p>}
            {pendingDelete.source === "notice" && <p className="text-muted">공지에서 다시 찾아도 되살아나지 않습니다.</p>}
            {pendingDelete.isAuto && (
              <p className="text-muted">
                임의로 잡아 둔 일정입니다 — 지우면 이 과목은 {pendingDelete.typeLabel}을(를) 안 보는 것으로 둡니다(과목별 시험에서 다시 켤 수 있습니다).
                날짜만 틀렸다면 지우지 말고 ✏로 고치세요.
              </p>
            )}
          </div>
        )}
      </Modal>
    </Page>
  );
}

/** 오늘 공부 — 목록 위 한 줄 (F5-R36 · S09) */
function TodayStrip({ today }: { today: ExamsOverview["today"] }) {
  return (
    <div className="card flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
      <span className="flex items-center gap-1.5 text-[13px] font-bold text-study">
        <BookOpen className="size-4" aria-hidden />
        오늘 공부
      </span>
      {today.blocks.map((b) => (
        <span key={`${b.planId}:${b.examId}`} className="flex items-center gap-2">
          <CourseChip name={b.course} color={b.color} />
          <span className={`num text-[14px] ${b.done ? "text-faint line-through" : ""}`}>
            {b.kind === "review" ? "전체 복습" : `${b.pages}쪽`} · {hm(b.minutes)}
          </span>
        </span>
      ))}
      <span className="num ml-auto text-[13px] text-muted">
        합계 {today.totalPages > 0 && `${today.totalPages}쪽 · `}
        {hm(today.totalMinutes)}
        {today.remainingMinutes !== today.totalMinutes && ` · 남은 ${hm(today.remainingMinutes)}`}
      </span>
    </div>
  );
}

/* ---------------------------------------------------------------- 오른쪽 패널 (옵션 → 미리보기 → 진도) */

function PlanPanel({
  exam,
  data,
  ex,
  bare,
}: {
  exam: Exam;
  data: ExamsOverview | null;
  ex: ReturnType<typeof useExams>;
  bare?: boolean;
}) {
  const plan = exam.plan;
  const [step, setStep] = useQueryParam<Step>("step", plan ? "progress" : "options", STEPS);
  const { detail, loading, error, reload: reloadDetail } = useExamDetail(exam.id);

  const body = (
    <div className="space-y-4">
      <Tabs
        variant="pill"
        size="sm"
        label="계획 단계"
        value={step}
        onChange={(s) => setStep(s)}
        items={[
          { key: "options", label: "옵션" },
          { key: "preview", label: "미리보기" },
          { key: "progress", label: "진도", disabled: !plan },
        ]}
      />

      {exam.planStale?.message && <Banner tone="warn">{exam.planStale.message}</Banner>}

      {step === "progress" ? (
        plan ? (
          <ProgressPanel
            plan={plan}
            busy={ex.busy}
            onToggleDay={(d: PlanDay) => void ex.patchDay(plan.id, d.date, { done: !d.done }).then(() => reloadDetail())}
            onRebalance={() => setStep("preview")}
            onCancel={() =>
              void ex.cancelPlan(plan.id).then((ok) => {
                if (ok) setStep("options"); // 계획이 사라졌으니 '진도' 탭에 남겨 두지 않는다
                return reloadDetail();
              })
            }
          />
        ) : (
          <p className="py-6 text-center text-[14px] text-muted">아직 등록된 계획이 없습니다.</p>
        )
      ) : error ? (
        <ErrorPanel message={error} onRetry={() => void reloadDetail()} />
      ) : loading || !detail ? (
        <p className="py-6 text-center text-[14px] text-muted">불러오는 중…</p>
      ) : (
        // 시험이 바뀌면 옵션 상태를 다시 세운다 — key 로 마운트를 새로 해서 효과 안에서 setState 하지 않는다
        <PlanBody key={detail.id} exam={exam} detail={detail} data={data} ex={ex} step={step} setStep={setStep} reloadDetail={reloadDetail} />
      )}
    </div>
  );

  if (bare) return body;
  return (
    <Section
      title={`${exam.course} ${exam.typeLabel}`}
      action={
        <button type="button" className="btn btn-ghost btn-icon btn-sm" aria-label="패널 닫기" onClick={() => closeQuery(["exam", "step"])}>
          <X aria-hidden />
        </button>
      }
    >
      <p className="num -mt-2 mb-3 flex flex-wrap items-center gap-2 text-[13px] text-muted">
        <DdayChip date={parseLocal(exam.date)} />
        {exam.date.slice(5).replace("-", "/")}({exam.weekday}) {exam.timeUnknown ? "시각 미정" : exam.time}
        {exam.place && ` · ${exam.place}`}
        {exam.scope.autoNote && <Chip tone="study">{exam.scope.autoNote}</Chip>}
      </p>
      {body}
    </Section>
  );
}

/** 옵션 → 미리보기. 계산은 서버가 하고, 등록만 캘린더를 바꾼다 (F5 D3). */
function PlanBody({
  exam,
  detail,
  data,
  ex,
  step,
  setStep,
  reloadDetail,
}: {
  exam: Exam;
  detail: ExamDetail;
  data: ExamsOverview | null;
  ex: ReturnType<typeof useExams>;
  step: Step;
  setStep: (s: Step) => void;
  reloadDetail: () => Promise<void>;
}) {
  const toast = useToast();
  const router = useRouter();
  const pv = usePlanPreview();
  // 분량은 쪽수로만 받는다 (2026-10-01 — 시간(분) 단위를 뺐다)
  const [opts, setOpts] = useState<PlanOptionsInput>({ ...detail.options, unit: "pages" });
  const [registering, setRegistering] = useState(false);
  const plan = exam.plan;

  const calc = useCallback(
    async (next?: PlanOptionsInput) => {
      const p = await pv.calc(exam.id, next ?? opts);
      if (p) {
        setOpts(optionsOf(p)); // 본 것과 등록되는 것이 어긋나지 않게 미리보기가 쓴 값으로 맞춘다
        setStep("preview");
      }
    },
    [exam.id, opts, pv, setStep],
  );

  const rebalance = useCallback(async () => {
    if (!plan) return;
    const p = await pv.rebalance(plan.id);
    if (p) {
      setOpts(optionsOf(p));
    }
  }, [plan, pv]);

  // 미리보기 탭인데 계산 결과가 없으면 계산한다(딥링크·재조정 진입 포함).
  // setState 는 마이크로태스크로 미룬다 — 효과 본문에서 바로 부르지 않는다(useMaterials 와 같은 방식).
  // 계획이 이미 있으면 재조정으로 연다 — 완료분을 빼고 남은 날로 다시 나눈 표에 진도 요약이 붙는다.
  const needCalc = step === "preview" && !pv.preview && !pv.calculating && !pv.error;
  const hasPlan = !!plan;
  useEffect(() => {
    if (!needCalc) return;
    void Promise.resolve().then(() => (hasPlan ? rebalance() : calc()));
  }, [needCalc, hasPlan, calc, rebalance]);

  // 옵션 단계에서는 바꿀 때마다 조용히 다시 계산한다(저장하지 않는다) — 학습일 달력과 '하루 몇 쪽 · 몇 시간'이 바로 따라온다.
  // 타이머 콜백에서 부르므로 효과 본문에서 setState 하지 않는다.
  const previewCalc = pv.calc;
  useEffect(() => {
    if (step !== "options") return;
    const t = window.setTimeout(() => void previewCalc(exam.id, opts), 250);
    return () => window.clearTimeout(t);
  }, [step, opts, exam.id, previewCalc]);

  const change = (patch: PlanOptionsInput) => setOpts((o) => ({ ...o, ...patch }));

  const register = async () => {
    const p = pv.preview;
    if (!p) return;
    setRegistering(true);
    const saved = await ex.createPlan(exam.id, opts);
    setRegistering(false);
    if (saved) {
      // 계산 결과는 그대로 둔다 — 여기서 비우면 아래 자동 계산이 다시 돌아 step 을 미리보기로 되돌린다.
      // 남겨 두면 '미리보기' 탭에서 방금 등록한 것과 같은 표를 다시 볼 수 있다.
      await reloadDetail();
      setStep("progress");
      // F8-S01 — 계획 분량은 저녁(19~24시)에 들어갔다. 낮 공강에도 이 과목 공부 블록을 넣을지 이어서 묻는다
      toast("낮 공강에도 공부 블록을 넣을까요?", { action: { label: "공강에 배치하기", onClick: () => router.push("/?place=preview") }, duration: 8000 });
    }
  };

  if (step === "options") {
    return (
      <PlanOptions
        detail={detail}
        value={opts}
        preview={pv.preview}
        difficulties={data?.difficulties ?? []}
        calculating={pv.calculating}
        onChange={change}
        onCalc={() => void calc()}
      />
    );
  }
  if (pv.calculating && !pv.preview) return <p className="py-6 text-center text-[14px] text-muted">계산 중…</p>;
  if (pv.error) return <ErrorPanel message={pv.error} onRetry={() => void calc()} />;
  if (!pv.preview) return <p className="py-6 text-center text-[14px] text-muted">옵션을 정하고 계산하기를 누르세요.</p>;
  return (
    <PlanPreviewPanel
      preview={pv.preview}
      registering={registering || ex.busy}
      onAdjust={(apply) => {
        const next = { ...opts, ...apply };
        setOpts(next);
        void calc(next);
      }}
      onBack={() => setStep("options")}
      onRegister={() => void register()}
    />
  );
}
