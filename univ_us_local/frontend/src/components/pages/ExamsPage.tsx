"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { CalendarPlus, ExternalLink, Plus, Target, TriangleAlert, X } from "lucide-react";
import { Page, PageHeader, Section } from "@/components/ui/Layout";
import { Banner, DemoNotice, EmptyState } from "@/components/ui/Feedback";
import { Chip, DdayChip, StatusBadge } from "@/components/ui/Chip";
import { ProgressBar } from "@/components/ui/Progress";
import { Modal } from "@/components/ui/Modal";
import { Tabs } from "@/components/ui/Tabs";
import { useToast } from "@/components/ui/Toast";
import { closeQuery, navigateQuery, useQueryParam, useQueryValue } from "@/lib/useQueryState";
import { useIsXl } from "@/lib/useMediaQuery";
import { demoExams, demoPlanPreview, type Exam } from "@/lib/demo";
import { daysUntil, fmtDateTime, fmtHours, fmtMD, parseLocal } from "@/lib/dates";

// /exams — 시험 목록 + 오른쪽 패널(옵션 → 미리보기 → 진도). 페이지를 옮기지 않고 `?exam=&step=` 으로 이어진다(10-2).
// 미리보기와 등록을 나눈다 — 캘린더를 바꾸는 것은 `등록하기` 뿐이다.

const STEPS = ["options", "preview", "progress"] as const;

export default function ExamsPage() {
  const examId = useQueryValue("exam");
  const [review, setReview] = useQueryParam("review", "0", ["0", "1"] as const);
  const [exams, setExams] = useState<Exam[]>(demoExams);
  const toReview = exams.filter((e) => e.status === "review");
  const list = review === "1" ? toReview : exams.filter((e) => e.status === "confirmed").sort((a, b) => a.date.localeCompare(b.date));
  const selected = exams.find((e) => e.id === examId) ?? null;
  const isXl = useIsXl();

  return (
    <Page wide>
      <PageHeader
        icon={<Target />}
        title="시험"
        actions={
          <button type="button" className="btn btn-primary btn-sm" onClick={() => navigateQuery({ new: "exam" }, "push")}>
            <Plus aria-hidden />
            시험 추가
          </button>
        }
      />
      <div className="mb-5 space-y-3">
        <DemoNotice what="시험·공부 계획" />
        {toReview.length > 0 && review !== "1" && (
          <Banner
            tone="warn"
            action={
              <button type="button" className="btn btn-sm" onClick={() => setReview("1")}>
                확인하러 가기
              </button>
            }
          >
            공지에서 찾은 시험 {toReview.length}건 — 확인이 필요합니다
          </Banner>
        )}
        {review === "1" && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setReview("0")}>
            ← 전체 시험으로
          </button>
        )}
      </div>

      <div className={`grid gap-5 ${selected && isXl ? "grid-cols-[minmax(0,1fr)_480px]" : ""}`}>
        <div className="space-y-3">
          {list.length === 0 ? (
            <EmptyState
              icon={<Target />}
              title="등록된 시험이 없습니다"
              action={
                <button type="button" className="btn btn-sm" onClick={() => navigateQuery({ new: "exam" }, "push")}>
                  <Plus aria-hidden />
                  시험 추가
                </button>
              }
            >
              공지에서 자동으로 찾거나 직접 추가하세요
            </EmptyState>
          ) : (
            list.map((e) => (
              <ExamCard
                key={e.id}
                e={e}
                active={e.id === examId}
                onConfirm={() => setExams((xs) => xs.map((x) => (x.id === e.id ? { ...x, status: "confirmed" } : x)))}
              />
            ))
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
              <div className="sticky top-[calc(var(--header-h)+16px)]">
                <PlanPanel exam={selected} />
              </div>
            </motion.aside>
          )}
        </AnimatePresence>
      </div>

      {/* 좁은 화면: 계획 단계는 시트로 */}
      <Modal open={!!selected && !isXl} onClose={() => closeQuery(["exam", "step"])} title={selected ? `${selected.course} ${selected.kind}` : ""} size="lg">
        {selected && <PlanPanel exam={selected} bare />}
      </Modal>
      <AddExamModal />
    </Page>
  );
}

function ExamCard({ e, active, onConfirm }: { e: Exam; active: boolean; onConfirm: () => void }) {
  const d = parseLocal(e.date);
  const n = daysUntil(d);
  return (
    <article className={`card p-4 md:p-5 ${active ? "border-primary ring-1 ring-primary" : ""}`}>
      <div className="flex flex-wrap items-start gap-4">
        <div className={`num grid w-16 flex-none place-items-center rounded-xl py-2 text-center ${n <= 7 ? "bg-accent-soft text-accent-text" : "bg-surface-3 text-muted"}`}>
          <span className="text-[20px] leading-tight font-bold">D-{Math.max(0, n)}</span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[16px] font-bold">{e.course}</h3>
            <Chip square>{e.kind}</Chip>
            {e.status === "review" && <StatusBadge tone="warn">확인 필요</StatusBadge>}
          </div>
          <p className="num mt-1 text-[14px] text-muted">
            {fmtDateTime(d)} · {e.room}
          </p>
          <p className="mt-1 text-[14px]">
            범위 {e.range ?? <span className="text-faint">미지정</span>} · 자료 {e.pages ? `${e.pages}쪽` : <span className="text-faint">—</span>}
          </p>
          {e.plan && (
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <div className="min-w-[160px] flex-1">
                <ProgressBar value={e.plan.done} max={e.plan.total} tone={e.plan.behindDays ? "accent" : "primary"} marker={0.55} label="공부 진도" />
              </div>
              <span className="num text-[13px] text-muted">
                진도 {e.plan.done}/{e.plan.total}쪽
              </span>
              {e.plan.behindDays > 0 && (
                <Chip tone="accent" icon={<TriangleAlert aria-hidden />}>
                  {e.plan.behindDays}일 밀림
                </Chip>
              )}
            </div>
          )}
        </div>
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-end gap-2 border-t border-border pt-3">
        {e.noticeUrl && (
          <a href={e.noticeUrl} target="_blank" rel="noopener noreferrer" className="mr-auto inline-flex items-center gap-1 text-[13px] font-semibold text-primary hover:underline">
            공지 원문 보기
            <ExternalLink className="size-3.5" aria-hidden />
          </a>
        )}
        {e.status === "review" ? (
          <button type="button" className="btn btn-primary btn-sm" onClick={onConfirm}>
            맞아요, 등록
          </button>
        ) : e.plan ? (
          <>
            <button type="button" className="btn btn-sm" onClick={() => navigateQuery({ exam: e.id, step: "preview" }, "push")}>
              재조정
            </button>
            <button type="button" className="btn btn-sm" onClick={() => navigateQuery({ exam: e.id, step: "progress" }, "push")}>
              진도
            </button>
          </>
        ) : (
          <button type="button" className="btn btn-primary btn-sm" onClick={() => navigateQuery({ exam: e.id, step: "options" }, "push")}>
            계획 만들기
          </button>
        )}
      </div>
    </article>
  );
}

function PlanPanel({ exam, bare }: { exam: Exam; bare?: boolean }) {
  const toast = useToast();
  const [step, setStep] = useQueryParam("step", exam.plan ? "progress" : "options", STEPS);
  const [excluded, setExcluded] = useState(["10/14", "10/19"]);
  const total = demoPlanPreview.reduce((s, x) => s + x.minutes, 0);
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
          { key: "progress", label: "진도", disabled: !exam.plan },
        ]}
      />
      {step === "options" && (
        <div className="space-y-3 text-[14px]">
          {[
            ["범위", exam.range ?? "직접 입력", exam.pages ? `자료 ${exam.pages}쪽 (자동)` : "쪽수를 직접 입력하세요"],
            ["난이도", "보통", "2.5분/쪽"],
            ["하루 상한", "4시간", "가용 시간 설정과 같은 값"],
            ["마무리 복습", "2일", ""],
          ].map(([k, v, h]) => (
            <div key={k} className="grid grid-cols-[88px_1fr] items-center gap-3">
              <span className="font-semibold text-muted">{k}</span>
              <span className="flex flex-wrap items-center gap-2">
                <select className="field field-sm w-auto" aria-label={k} defaultValue={v}>
                  <option>{v}</option>
                </select>
                {h && <span className="text-[12px] text-faint">{h}</span>}
              </span>
            </div>
          ))}
          <div className="grid grid-cols-[88px_1fr] items-start gap-3">
            <span className="pt-1 font-semibold text-muted">제외일</span>
            <span className="flex flex-wrap gap-1.5">
              {excluded.map((d) => (
                <span key={d} className="chip bg-surface-3 text-muted">
                  {d}
                  <button type="button" aria-label={`${d} 제외 해제`} onClick={() => setExcluded((xs) => xs.filter((x) => x !== d))}>
                    <X aria-hidden />
                  </button>
                </span>
              ))}
              <button type="button" className="chip border border-dashed border-border-strong text-muted">
                + 날짜
              </button>
            </span>
          </div>
          <label className="flex items-center gap-2">
            <input type="checkbox" defaultChecked className="size-4 accent-[var(--primary)]" />
            예상 문제 풀이 포함
          </label>
          <div className="flex justify-end">
            <button type="button" className="btn btn-primary btn-sm" onClick={() => setStep("preview")}>
              계산하기
            </button>
          </div>
        </div>
      )}
      {step === "preview" && (
        <div className="space-y-3">
          <Banner
            tone="danger"
            action={
              <>
                <button type="button" className="btn btn-sm">시작일 당기기</button>
                <button type="button" className="btn btn-sm">범위 줄이기</button>
                <button type="button" className="btn btn-sm">상한 올리기</button>
              </>
            }
          >
            10/20 에 3과목 5시간 — 하루 상한을 넘습니다
          </Banner>
          <ul className="divide-y divide-border rounded-xl border border-border">
            {demoPlanPreview.map((r) => (
              <li key={r.date} className={`flex items-center gap-3 px-3 py-2 text-[14px] ${r.excluded ? "text-faint" : ""}`}>
                <span className="num w-20 flex-none font-semibold">{fmtMD(parseLocal(r.date))}</span>
                <span className="min-w-0 flex-1 truncate">{r.excluded ? "— 제외일" : r.label}</span>
                {!r.excluded && (
                  <span className="num flex-none text-muted">
                    {r.pages ? `${r.pages}쪽 · ` : ""}
                    {fmtHours(r.minutes / 60)}
                  </span>
                )}
              </li>
            ))}
          </ul>
          <p className="num text-right text-[14px] font-semibold">
            합계 {exam.pages ?? 120}쪽 · {fmtHours(total / 60)}
          </p>
          <div className="flex justify-end gap-2">
            <button type="button" className="btn btn-sm" onClick={() => setStep("options")}>
              다시 계산
            </button>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={() => {
                closeQuery(["exam", "step"]);
                toast("8일치 학습 계획을 캘린더에 넣었습니다 (예시 — 계획 API 연결 전)", { tone: "success" });
              }}
            >
              <CalendarPlus aria-hidden />
              등록하기
            </button>
          </div>
        </div>
      )}
      {step === "progress" && exam.plan && (
        <div className="space-y-3 text-[14px]">
          <ProgressBar value={exam.plan.done} max={exam.plan.total} tone="accent" marker={0.55} label="진도" height={10} />
          <p className="num">
            완료 {exam.plan.done} / 계획 {exam.plan.total}쪽 · 오늘까지 계획 66쪽
          </p>
          {exam.plan.behindDays > 0 && (
            <Banner
              tone="warn"
              action={
                <button type="button" className="btn btn-sm" onClick={() => setStep("preview")}>
                  재조정하기
                </button>
              }
            >
              {exam.plan.behindDays}일 밀렸습니다 — 남은 6일로 다시 나누면 하루 19쪽입니다
            </Banner>
          )}
          <button type="button" className="btn btn-ghost btn-danger btn-sm">
            계획 취소 (완료분은 남김)
          </button>
        </div>
      )}
    </div>
  );
  if (bare) return body;
  return (
    <Section
      title={`${exam.course} ${exam.kind}`}
      action={
        <button type="button" className="btn btn-ghost btn-icon btn-sm" aria-label="패널 닫기" onClick={() => closeQuery(["exam", "step"])}>
          <X aria-hidden />
        </button>
      }
    >
      <p className="num -mt-2 mb-3 text-[13px] text-muted">
        <DdayChip date={parseLocal(exam.date)} /> {fmtDateTime(parseLocal(exam.date))}
      </p>
      {body}
    </Section>
  );
}

function AddExamModal() {
  const open = useQueryValue("new") === "exam";
  const close = () => closeQuery(["new"]);
  return (
    <Modal
      open={open}
      onClose={close}
      title="시험 추가"
      footer={
        <>
          <button type="button" className="btn" onClick={close}>
            취소
          </button>
          <button type="button" className="btn btn-primary" onClick={close}>
            추가
          </button>
        </>
      }
    >
      <div className="space-y-4 pt-1">
        <div>
          <label className="label" htmlFor="ex-c">
            과목
          </label>
          <input id="ex-c" data-autofocus className="field" placeholder="예) 운영체제[2]" />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label" htmlFor="ex-d">
              일시
            </label>
            <input id="ex-d" type="datetime-local" className="field" />
          </div>
          <div>
            <label className="label" htmlFor="ex-r">
              장소
            </label>
            <input id="ex-r" className="field" placeholder="공7-223" />
          </div>
        </div>
        <div>
          <label className="label" htmlFor="ex-s">
            범위 <span className="font-normal text-faint">(선택)</span>
          </label>
          <input id="ex-s" className="field" placeholder="3~7주차" />
        </div>
      </div>
    </Modal>
  );
}
