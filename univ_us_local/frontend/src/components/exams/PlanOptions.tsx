"use client";

import { useState } from "react";
import { Calculator, RotateCcw } from "lucide-react";
import { Banner } from "@/components/ui/Feedback";
import { TimeAllocator } from "@/components/exams/TimeAllocator";
import { hm, type Difficulty, type ExamDetail, type PlanOptionsInput, type PlanPreview } from "@/lib/exams";

// 계획 만들기 — 옵션 (F5-S04 · Frontend-Route 10-4).
// 2026-10-06(D11): 세 단계로 묻는다 — ① 얼마나(분량 × 난이도 = **총 공부 시간**) → ② 언제(학습일 수·달력)
// → ③ 하루 몇 시간(총 시간을 학습일에 자유롭게 나눈다, TimeAllocator). 예전에는 학습일 수로 똑같이 나누기만 했다.
// 분량은 쪽수로만 받는다(시간(분) 단위는 뺐다). F4 자료에서 쪽수를 자동으로 채우고(F5-R10), 없으면 직접 넣는다(F5-R11).
// 계산은 서버가 한다 — 옵션을 바꾸면 미리보기를 조용히 다시 받아 총 시간·날마다의 분량이 바로 따라온다.

const ROW = "grid grid-cols-[92px_1fr] items-start gap-3";
const WD = ["일", "월", "화", "수", "목", "금", "토"];

export function PlanOptions({
  detail,
  value,
  preview,
  difficulties,
  calculating,
  onChange,
  onCalc,
}: {
  detail: ExamDetail;
  value: PlanOptionsInput;
  /** 지금 옵션으로 계산한 결과 (저장하지 않은 미리보기) — 총 공부 시간·학습일·날마다의 분량을 여기서 읽는다 */
  preview: PlanPreview | null;
  /** 고를 수 있는 값은 서버가 준다 (/api/exams 의 difficulties) */
  difficulties: { key: Difficulty; label: string; pageMinutes: number }[];
  calculating: boolean;
  onChange: (patch: PlanOptionsInput) => void;
  onCalc: () => void;
}) {
  const [draft, setDraft] = useState<string | null>(null); // 학습일 칸에 치는 중인 글자 (null = 치고 있지 않음)
  const weeks = detail.scopeChoices.weeks;
  const picked = new Set(value.scopeWeeks ?? []);
  const scope = preview?.scope ?? null;
  const autoPages = scope ? scope.pages : (detail.scope.pages ?? 0);
  const noMaterials = !autoPages && !value.totalPages;
  const pool = preview?.studyPool ?? 0;
  // 학습일 기본 3일(2026-10-02). 시험까지 남은 날이 그보다 적으면 계산기가 줄인 만큼만 보여 준다
  const asked = value.studyDays ?? preview?.studyDays ?? null;
  const count = value.studyDates?.length ? value.studyDates.length : asked !== null && pool > 0 && asked > pool ? pool : asked;
  const al = preview?.allocation;
  const pinnedCount = Object.keys(value.dayMinutes ?? {}).filter((d) => preview?.studyDates.includes(d)).length;

  const toggleWeek = (w: number) => {
    const next = new Set(picked);
    if (next.has(w)) next.delete(w);
    else next.add(w);
    // 범위가 바뀌면 쪽수를 다시 자동으로 채운다(0 = 서버가 F4 에서 센다)
    onChange({ scopeWeeks: [...next].sort((a, b) => a - b), totalPages: 0 });
  };

  return (
    <div className="space-y-3 text-[14px]">
      {/* ── ① 얼마나 — 분량 × 난이도 = 총 공부 시간 ── */}
      <Part n={1} title="얼마나 공부할까">
        {noMaterials && <Banner tone="info">범위 안 강의자료의 쪽수를 찾지 못했습니다 — 쪽수를 직접 넣으면 계획을 만들 수 있습니다.</Banner>}
        <div className="space-y-2.5">
          {weeks.length > 0 && (
            <div className={ROW}>
              <span className="pt-1.5 font-semibold text-muted">범위 주차</span>
              <span className="flex flex-wrap gap-1.5">
                {weeks.map((w) => (
                  <button
                    key={w}
                    type="button"
                    aria-pressed={picked.has(w)}
                    onClick={() => toggleWeek(w)}
                    className={`chip ${picked.has(w) ? "bg-primary text-on-primary" : "bg-surface-3 text-muted"}`}
                  >
                    {w}주
                  </button>
                ))}
                {picked.size > 0 && (
                  <button type="button" className="chip border border-dashed border-border-strong text-muted" onClick={() => onChange({ scopeWeeks: [], totalPages: 0 })}>
                    전체
                  </button>
                )}
              </span>
            </div>
          )}

          <div className={ROW}>
            <label htmlFor="plan-pages" className="pt-1.5 font-semibold text-muted">
              분량
            </label>
            <span className="flex flex-wrap items-center gap-2">
              <input
                id="plan-pages"
                type="number"
                min={0}
                className="field field-sm num w-[96px]"
                placeholder={autoPages ? String(autoPages) : "직접 입력"}
                value={value.totalPages || ""}
                onChange={(e) => onChange({ unit: "pages", totalPages: Number(e.target.value) || 0 })}
              />
              <span>쪽</span>
              <span className="text-[12px] text-faint">
                {/* 서버가 F4 자료에서 채운 값과 같으면 '자동', 사용자가 고쳤으면 그렇게 말한다 */}
                {value.totalPages && value.totalPages !== autoPages
                  ? "직접 넣은 값"
                  : scope?.note || (autoPages ? `자료 ${autoPages}쪽 (자동)` : "쪽수를 직접 입력하세요")}
              </span>
            </span>
          </div>

          <div className={ROW}>
            <span className="pt-1.5 font-semibold text-muted">난이도</span>
            <span className="flex flex-wrap items-center gap-2">
              <select
                className="field field-sm w-auto"
                aria-label="난이도"
                value={value.difficulty ?? "normal"}
                onChange={(e) => onChange({ difficulty: e.target.value as Difficulty, pageMinutes: undefined })}
              >
                {difficulties.map((d) => (
                  <option key={d.key} value={d.key}>
                    {d.label} ({d.pageMinutes}분/쪽)
                  </option>
                ))}
              </select>
              <span className="text-[12px] text-faint">시간은 위쪽 &lsquo;난이도 시간 설정&rsquo;에서 바꿉니다</span>
            </span>
          </div>
        </div>

        {/* 총 공부 시간 — 이 숫자를 ③에서 날마다 나눈다 */}
        <div className="mt-3 flex flex-wrap items-baseline gap-x-3 gap-y-0.5 rounded-lg bg-primary-soft/60 px-3 py-2" aria-live="polite">
          <span className="text-[13px] font-semibold text-muted">총 공부 시간</span>
          <b className="num text-[22px] leading-tight">{al ? hm(al.needMinutes) : "—"}</b>
          {preview && al && (
            <span className="num text-[12px] text-muted">
              {preview.unit === "pages"
                ? `${Math.max(0, preview.totalPages - preview.carried.pages)}쪽 × ${preview.pageMinutes}분`
                : "직접 넣은 시간"}
              {preview.carried.pages > 0 && ` (이미 마친 ${preview.carried.pages}쪽 제외)`}
              {al.reviewMinutes > 0 && ` · 마무리 복습 ${hm(al.reviewMinutes)}은 따로`}
            </span>
          )}
          {calculating && <span className="text-[12px] text-faint">계산 중…</span>}
        </div>
      </Part>

      {/* ── ② 언제 — 학습일 수 또는 달력에서 직접 ── */}
      <Part n={2} title="언제 공부할까">
        <div className="flex flex-wrap items-center gap-2">
          <label htmlFor="plan-days" className="font-semibold">
            학습일
          </label>
          <input
            id="plan-days"
            type="number"
            min={1}
            max={pool || undefined}
            className="field field-sm num w-[76px]"
            // 치는 동안은 친 글자 그대로 보여 준다(draft). 계산값에 묶어 두면 한 자리를 지우는 순간 직전 값이 다시 들어와
            // Backspace 가 먹지 않는 것처럼 보였다. 비운 채로 칸을 떠나면 직전 학습일 수로 돌아간다.
            value={draft ?? (count ?? "")}
            placeholder={pool ? String(pool) : ""}
            onChange={(e) => {
              setDraft(e.target.value);
              const n = Number(e.target.value);
              if (e.target.value !== "" && Number.isInteger(n) && n > 0) onChange({ studyDays: n, studyDates: [] });
            }}
            onBlur={() => setDraft(null)}
          />
          <span>일</span>
        </div>
        <p className="mt-1 text-[12px] text-muted">
          {value.studyDates?.length
            ? "아래 달력에서 고른 날에 공부합니다."
            : `시험 직전 마무리 복습일 바로 앞 ${count ?? "모든"}${count ? "일" : " 날"}${pool ? ` (최대 ${pool}일)` : ""} — 달력에서 날짜를 직접 고를 수도 있습니다.`}
        </p>
        <DatePicker detail={detail} value={value} preview={preview} onChange={onChange} />
      </Part>

      {/* ── ③ 하루 몇 시간 — 총 공부 시간을 학습일에 자유롭게 ── */}
      <Part
        n={3}
        title="하루 몇 시간"
        aside={
          pinnedCount > 0 && (
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => onChange({ dayMinutes: {} })}>
              <RotateCcw aria-hidden />
              고르게 나누기
            </button>
          )
        }
      >
        <p className="mb-2.5 text-[12px] text-muted">
          날마다 공부할 시간을 정하세요. 손대지 않은 날(<b className="font-semibold">자동</b>)이 남은 시간을 나눠 가지므로 합계는 늘 총
          공부 시간과 같습니다.
        </p>
        <TimeAllocator value={value} preview={preview} onChange={onChange} />
      </Part>

      {/* ── 마무리 ── */}
      <div className="space-y-2.5 rounded-xl border border-border px-3 py-3">
        <div className={ROW}>
          <span className="pt-1.5 font-semibold text-muted">마무리 복습</span>
          <span className="flex flex-wrap items-center gap-2">
            <select
              className="field field-sm w-auto"
              aria-label="마무리 복습일"
              value={value.reviewDays ?? 1}
              onChange={(e) => onChange({ reviewDays: Number(e.target.value) })}
            >
              {[0, 1, 2, 3, 4, 5].map((n) => (
                <option key={n} value={n}>
                  {n === 0 ? "없음" : `${n}일`}
                </option>
              ))}
            </select>
            <span className="text-[12px] text-faint">기본은 시험 전날 하루 — 이 날은 새 진도 없이 전체 복습</span>
          </span>
        </div>

        <div className={ROW}>
          <span className="pt-1.5 font-semibold text-muted">예상 문제</span>
          <span className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                className="size-4 accent-[var(--primary)]"
                checked={!!value.includeQuiz}
                onChange={(e) => onChange({ includeQuiz: e.target.checked, quizCount: e.target.checked ? value.quizCount || 20 : 0 })}
              />
              마무리 복습일에 문제 풀이 포함
            </label>
            {value.includeQuiz && (
              <>
                <input
                  type="number"
                  min={1}
                  max={500}
                  className="field field-sm w-[88px]"
                  aria-label="예상 문제 수"
                  value={value.quizCount || 20}
                  onChange={(e) => onChange({ quizCount: Number(e.target.value) || 0 })}
                />
                <span className="text-[12px] text-faint">문항 · 문항당 2분으로 봅니다</span>
              </>
            )}
          </span>
        </div>
      </div>

      <div className="flex items-center justify-end gap-2 pt-1">
        <button type="button" className="btn btn-primary btn-sm" onClick={onCalc} disabled={calculating}>
          <Calculator aria-hidden />
          미리보기
        </button>
      </div>
    </div>
  );
}

/** 계획 만들기의 한 단계 — 번호 · 제목 · (오른쪽 버튼) */
function Part({ n, title, aside, children }: { n: number; title: string; aside?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-border p-3" aria-label={title}>
      <header className="mb-2.5 flex min-h-7 items-center gap-2">
        <span className="num grid size-5 flex-none place-items-center rounded-full bg-primary text-[11px] font-bold text-on-primary" aria-hidden>
          {n}
        </span>
        <h3 className="text-[14px] font-bold">{title}</h3>
        {aside && <span className="ml-auto">{aside}</span>}
      </header>
      {children}
    </section>
  );
}

/** 학습 날짜 고르기 — 오늘 ~ 시험 전날. 누르면 그 날을 넣고 빼며, 그때부터 '고른 날'에 나눈다. */
function DatePicker({
  detail,
  value,
  preview,
  onChange,
}: {
  detail: ExamDetail;
  value: PlanOptionsInput;
  preview: PlanPreview | null;
  onChange: (patch: PlanOptionsInput) => void;
}) {
  const dates = preview?.selectableDates ?? [];
  if (!dates.length) {
    return <p className="mt-2 text-[12px] text-faint">{preview ? "시험까지 고를 수 있는 날이 없습니다." : "날짜를 불러오는 중…"}</p>;
  }
  const study = new Set(value.studyDates?.length ? value.studyDates : preview?.studyDates ?? []);
  const review = new Set(preview?.reviewDayDates ?? []);
  const toggle = (d: string) => {
    const next = new Set(value.studyDates?.length ? value.studyDates : preview?.studyDates ?? []);
    if (next.has(d)) next.delete(d);
    else next.add(d);
    onChange({ studyDates: [...next].sort(), studyDays: null });
  };

  // 일요일부터 시작하는 주 단위 칸 — 앞쪽은 빈칸으로 채운다
  const first = parse(dates[0]);
  const cells: (string | null)[] = [...Array(first.getDay()).fill(null), ...dates];

  return (
    <div className="mt-3">
      <div className="grid grid-cols-7 gap-1 text-center text-[11px] font-semibold text-faint" aria-hidden>
        {WD.map((w) => (
          <span key={w}>{w}</span>
        ))}
      </div>
      <div className="mt-1 grid grid-cols-7 gap-1" role="group" aria-label="공부할 날짜">
        {cells.map((d, i) => {
          if (!d) return <span key={`b${i}`} />;
          const day = parse(d);
          const isStudy = study.has(d);
          const isReview = !isStudy && review.has(d);
          const label = `${day.getMonth() + 1}월 ${day.getDate()}일 (${WD[day.getDay()]})${isStudy ? " 공부일" : isReview ? " 마무리 복습" : ""}`;
          return (
            <button
              key={d}
              type="button"
              aria-pressed={isStudy}
              aria-label={label}
              title={label}
              onClick={() => toggle(d)}
              className={`num flex h-9 flex-col items-center justify-center rounded-lg text-[12px] leading-none transition-colors ${
                isStudy
                  ? "bg-study font-bold text-on-study"
                  : isReview
                    ? "border border-dashed border-study bg-surface text-study"
                    : "border border-border bg-surface text-muted hover:bg-surface-2"
              }`}
            >
              <span>{day.getDate() === 1 || i === first.getDay() ? `${day.getMonth() + 1}/${day.getDate()}` : day.getDate()}</span>
              {isReview && <span className="mt-0.5 text-[9px]">복습</span>}
            </button>
          );
        })}
        <span className="num col-span-7 mt-1 text-right text-[11px] text-faint">
          시험 {detail.date.slice(5).replace("-", "/")}({detail.weekday})
        </span>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-3 text-[12px] text-muted">
        <span className="flex items-center gap-1">
          <i className="inline-block size-3 rounded bg-study" aria-hidden /> 공부
        </span>
        <span className="flex items-center gap-1">
          <i className="inline-block size-3 rounded border border-dashed border-study" aria-hidden /> 마무리 복습
        </span>
        {!!value.studyDates?.length && (
          <button type="button" className="btn btn-ghost btn-sm ml-auto" onClick={() => onChange({ studyDates: [], studyDays: null })}>
            <RotateCcw aria-hidden />
            자동으로
          </button>
        )}
      </div>
    </div>
  );
}

function parse(s: string): Date {
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, m - 1, d);
}
