"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { CalendarX2, Settings2, X } from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { Banner, EmptyState, ErrorPanel, Spinner } from "@/components/ui/Feedback";
import { useToast } from "@/components/ui/Toast";
import { useAppData } from "@/components/app/AppData";
import { api } from "@/lib/api";
import { closeQuery, navigateQuery, useQueryValue } from "@/lib/useQueryState";
import { useMediaQuery } from "@/lib/useMediaQuery";
import { hm, TASK_LABEL, toMin, type PlacementPreview as Preview, type PlannedBlock, type PreviewDay, type SavedBlock } from "@/lib/placement";

/** 블록 색 — 공부(채우기)는 청록, 과제·할 일은 연두 */
const blockCls = (t: string) =>
  t === "study" ? "border-primary bg-primary-soft text-primary" : "border-study bg-study-soft text-study";

// F8 공강 배치 미리보기 — `/?place=preview` 전체 화면 모달(Frontend-Route 13-3).
// 계산은 전부 서버(POST /api/placement/preview)가 하고, 화면은 그대로 그린다. 배치하기 전엔 캘린더가 바뀌지 않는다.
// 낮 공강(기본 09~18시)만 쓴다 — 과제·할 일이 먼저, 남는 공강은 공부 블록(2026-10-07). 저녁은 F5 시험 공부 계획 몫.
// 수업 = 회색, 기존 일정 = 파랑, 새 과제·할 일 = 연두, 새 공부 = 청록. 색만으로 구분하지 않게 블록에 종류와 이름을 쓴다.

const RANGES = [7, 14] as const;

export default function PlacementPreview() {
  const open = useQueryValue("place") === "preview";
  const rangeRaw = Number(useQueryValue("range"));
  const range = (RANGES as readonly number[]).includes(rangeRaw) ? rangeRaw : undefined;
  const close = () => closeQuery(["place", "range"]);
  return (
    <Modal open={open} onClose={close} size="xl" title="공강에 배치하기">
      {/* 열 때마다 · 기간을 바꿀 때마다 새로 계산한다 (key 로 다시 마운트 — 제외 목록도 비운다) */}
      {open && <PreviewBody key={range ?? "default"} range={range} onClose={close} />}
    </Modal>
  );
}

function PreviewBody({ range, onClose }: { range?: number; onClose: () => void }) {
  const toast = useToast();
  const { refresh } = useAppData();
  const [data, setData] = useState<Preview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [exclude, setExclude] = useState<string[]>([]);

  const load = async (ex: string[]) => {
    setLoading(true);
    try {
      setData(await api.placementPreview({ range, exclude: ex }));
      setError(null);
    } catch (e) {
      if (data) toast(`계산하지 못했습니다: ${e instanceof Error ? e.message : String(e)}`, { tone: "error" });
      else setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void Promise.resolve().then(() => load([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const drop = (key: string) => {
    const ex = [...exclude, key];
    setExclude(ex);
    void load(ex);
  };

  const recalc = () => {
    setExclude([]);
    void load([]);
  };

  const adjust = async (patch: Record<string, unknown>, label: string) => {
    try {
      await api.patchAvailability(patch);
      toast(`${label} — 설정을 바꾸고 다시 계산했습니다`, { tone: "success" });
      await load(exclude);
    } catch (e) {
      toast(`설정을 바꾸지 못했습니다: ${e instanceof Error ? e.message : String(e)}`, { tone: "error" });
    }
  };

  const register = async () => {
    if (!data) return;
    setSaving(true);
    try {
      const out = await api.registerPlacement({ signature: data.signature, at: data.at, range, exclude });
      await refresh();
      onClose();
      // 공부 블록은 공부 캘린더에만 들어간다 — 전체 캘린더와 공부 캘린더는 따로다 (F5 D7)
      const work = out.created - out.studyCreated;
      const parts = [work && `과제·할 일 ${work}개는 캘린더에`, out.studyCreated && `공부 ${out.studyCreated}개는 공부 캘린더에`].filter(Boolean);
      toast(`${parts.join(", ") || `${out.created}개 블록을`} 넣었습니다`, {
        tone: "success",
        action: work
          ? { label: "캘린더에서 보기", onClick: () => navigateQuery({ view: "week", date: data.range.start }, "replace") }
          : { label: "공부 캘린더 보기", onClick: () => window.location.assign(new URL("/study-calendar", window.location.origin).href) },
      });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      toast(msg.includes("다시 계산") ? msg : `배치하지 못했습니다: ${msg}`, { tone: "error" });
      if (msg.includes("다시 계산")) void load(exclude);
    } finally {
      setSaving(false);
    }
  };

  if (error && !data) return <ErrorPanel message={`배치를 계산하지 못했습니다 — ${error}`} onRetry={() => void load(exclude)} />;
  if (!data) return <div className="grid place-items-center py-16"><Spinner label="빈 시간을 찾는 중…" /></div>;

  const s = data.state;
  const curRange = data.range.days;

  return (
    <div className="space-y-4 pt-1" aria-busy={loading}>
      <div className="flex flex-wrap items-center gap-2 text-[13px] text-muted">
        <span className="num">
          {data.range.start.slice(5).replace("-", "/")} ~ {data.range.end.slice(5).replace("-", "/")}
        </span>
        <label className="sr-only" htmlFor="place-range">배치 기간</label>
        <select
          id="place-range"
          className="field field-sm w-auto"
          value={curRange}
          onChange={(e) => navigateQuery({ range: e.target.value === String(data.settings.rangeDays) ? null : e.target.value }, "replace")}
        >
          {RANGES.map((n) => (
            <option key={n} value={n}>
              {n === 7 ? "이번 주(7일)" : "2주(14일)"}
            </option>
          ))}
        </select>
        <span>
          낮 {data.settings.dayStart}~{data.settings.dayEnd} 공강 · 블록 {data.settings.minSlotMinutes}분~{hm(data.settings.maxBlockMinutes)}
          {data.settings.fillStudy ? " · 남는 공강은 공부" : ""}
        </span>
        <Link href="/settings/availability" className="btn btn-ghost btn-sm ml-auto">
          <Settings2 aria-hidden />
          가용 시간 설정
        </Link>
        {loading && <Spinner />}
      </div>

      {!s.timetable && (
        <Banner tone="info" action={<Link href="/attendance?tab=timetable" className="btn btn-sm">시간표 넣기</Link>}>
          시간표가 없어 수업 시간을 빼지 못했습니다 — 낮 시간 전체를 공강으로 봅니다
        </Banner>
      )}
      {data.existing > 0 && (
        <Banner tone="neutral">
          이미 배치된 블록 <b className="num">{data.existing}</b>개 — 새로 계산하면 자동 배치분만 바뀝니다 (내가 옮긴 블록·완료한 블록은 그대로)
        </Banner>
      )}

      {s.tasks === 0 && data.blocks.length === 0 && data.kept.length === 0 ? (
        <EmptyState icon={<CalendarX2 />} title="지금 배치할 과제·할 일·공부가 없습니다">
          e클래스 과제나 할 일이 생기거나, 30일 안에 시험이 잡히면(시험·발표 화면) 여기서 공강에 넣을 수 있습니다.
        </EmptyState>
      ) : (
        <>
          {!s.allUnplaced && (
            <>
              <div className="flex flex-wrap gap-3 text-[12px] text-muted">
                <Legend cls="bg-surface-3 border-border" label="수업" />
                <Legend cls="bg-info-soft border-info-line" label="기존 일정" />
                <Legend cls="bg-study-soft border-study border-dashed" label="이미 있는 블록" />
                <Legend cls="bg-study-soft border-study" label="새 과제·할 일" />
                <Legend cls="bg-primary-soft border-primary" label="새 공부 블록 (공부 캘린더에만)" />
              </div>
              <Grid data={data} onDrop={drop} />
              <DailyTotals data={data} />
              <StudyOrder data={data} />
            </>
          )}
          <UnplacedPanel data={data} onAdjust={adjust} />
        </>
      )}

      <div className="flex flex-wrap items-center justify-end gap-2 border-t border-border pt-3">
        <span className="mr-auto text-[13px] text-muted">
          새 블록 <b className="num text-text">{data.blocks.length}</b>개 · <b className="num text-text">{hm(data.totalMinutes)}</b>
          {data.studyMinutes > 0 && <> (공부 {hm(data.studyMinutes)})</>}
          {exclude.length > 0 && <> · 뺀 블록 {exclude.length}개</>}
        </span>
        <button type="button" className="btn" disabled={loading} onClick={recalc}>
          다시 계산
        </button>
        <button type="button" className="btn btn-primary" disabled={loading || saving || data.blocks.length === 0} onClick={register}>
          {saving ? "넣는 중…" : "배치하기"}
        </button>
      </div>
    </div>
  );
}

function Legend({ cls, label }: { cls: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`size-3 rounded border ${cls}`} aria-hidden />
      {label}
    </span>
  );
}

/* ---------------------------------------------------------------- 주간 격자 (F8-S02 · S03 · S04) */

const PX = 0.8; // 1분 = 0.8px (한 시간 48px)

function Grid({ data, onDrop }: { data: Preview; onDrop: (key: string) => void }) {
  const narrow = useMediaQuery("(max-width: 767px)");
  const byDay = useMemo(() => {
    const m = new Map<string, { blocks: PlannedBlock[]; kept: SavedBlock[] }>();
    for (const d of data.days) m.set(d.date, { blocks: [], kept: [] });
    for (const b of data.blocks) m.get(b.date)?.blocks.push(b);
    for (const b of data.kept) m.get(b.date)?.kept.push(b);
    return m;
  }, [data]);

  // 보여 줄 시간 범위 — 수업·일정·빈 시간·블록이 있는 곳만 (기본 09~24)
  const [h0, h1] = useMemo(() => {
    let lo = 9 * 60;
    let hi = 21 * 60;
    for (const d of data.days) {
      for (const x of [...d.classes, ...d.events, ...d.slots]) {
        lo = Math.min(lo, toMin(x.start));
        hi = Math.max(hi, toMin(x.end));
      }
    }
    for (const b of [...data.blocks, ...data.kept]) {
      lo = Math.min(lo, toMin(b.start));
      hi = Math.max(hi, toMin(b.end));
    }
    return [Math.floor(lo / 60), Math.min(24, Math.ceil(hi / 60))];
  }, [data]);

  // 폰: 격자 대신 날짜별 목록 (Frontend-Route 13-8)
  if (narrow) {
    return (
      <ol className="space-y-3">
        {data.days.map((d) => {
          const x = byDay.get(d.date)!;
          if (!x.blocks.length && !x.kept.length) return null;
          return (
            <li key={d.date}>
              <h3 className="mb-1 text-[13px] font-bold text-muted">
                {d.date.slice(5).replace("-", "/")}({d.weekday})
              </h3>
              <ul className="space-y-1.5">
                {x.kept.map((b) => (
                  <li key={b.id} className="rounded-lg border border-dashed border-study bg-study-soft px-3 py-2 text-[13px] text-study">
                    <span className="num font-semibold">{b.start}~{b.end}</span> {b.title} <span className="opacity-75">· {b.done ? "완료" : b.auto ? "자동" : "고정"}</span>
                  </li>
                ))}
                {x.blocks.map((b) => (
                  <li key={b.key} className={`flex items-start gap-2 rounded-lg border px-3 py-2 text-[13px] ${blockCls(b.taskType)}`}>
                    <span className="min-w-0 flex-1">
                      <span className="num font-semibold">{b.start}~{b.end}</span> <span className="text-[11px] font-bold">[{TASK_LABEL[b.taskType]}]</span> <b>{b.title}</b>
                      <span className="block text-[12px] opacity-80">{b.reason}</span>
                    </span>
                    <DropButton block={b} onDrop={onDrop} />
                  </li>
                ))}
              </ul>
            </li>
          );
        })}
      </ol>
    );
  }

  const hours = Array.from({ length: h1 - h0 }, (_, i) => h0 + i);
  const height = (h1 - h0) * 60 * PX;
  return (
    <div className="thin-scroll overflow-x-auto">
      <div className="grid min-w-[640px] gap-1" style={{ gridTemplateColumns: `40px repeat(${data.days.length}, minmax(${data.days.length > 7 ? 92 : 72}px, 1fr))` }}>
        <div />
        {data.days.map((d) => (
          <div key={d.date} className={`pb-1 text-center text-[13px] font-semibold ${d.weekend ? "text-faint" : "text-muted"}`}>
            {d.weekday} <span className="num font-normal">{d.date.slice(8)}</span>
          </div>
        ))}
        <div className="relative" style={{ height }}>
          {hours.map((h) => (
            <span key={h} className="num absolute right-1 text-[11px] text-faint" style={{ top: (h - h0) * 60 * PX - 6 }}>
              {String(h).padStart(2, "0")}
            </span>
          ))}
        </div>
        {data.days.map((d) => (
          <DayColumn key={d.date} day={d} blocks={byDay.get(d.date)!.blocks} kept={byDay.get(d.date)!.kept} h0={h0} hours={hours} height={height} onDrop={onDrop} />
        ))}
      </div>
    </div>
  );
}

function DayColumn({
  day,
  blocks,
  kept,
  h0,
  hours,
  height,
  onDrop,
}: {
  day: PreviewDay;
  blocks: PlannedBlock[];
  kept: SavedBlock[];
  h0: number;
  hours: number[];
  height: number;
  onDrop: (key: string) => void;
}) {
  const pos = (start: string, end: string) => {
    const top = (toMin(start) - h0 * 60) * PX;
    return { top, height: Math.max((toMin(end) - toMin(start)) * PX, 14) };
  };
  return (
    <div className="relative rounded-md bg-surface-2" style={{ height }} role="group" aria-label={`${day.date.slice(5).replace("-", "/")} ${day.weekday}요일`}>
      {hours.map((h) => (
        <div key={h} className="absolute inset-x-0 border-t border-border/60" style={{ top: (h - h0) * 60 * PX }} aria-hidden />
      ))}
      {day.classes.map((c, i) => (
        <div
          key={`c${i}`}
          className={`absolute inset-x-0.5 overflow-hidden rounded border px-1 text-[11px] leading-tight ${c.canceled ? "border-dashed border-border bg-transparent text-faint line-through" : "border-border bg-surface-3 text-faint"}`}
          style={pos(c.start, c.end)}
          title={`수업 · ${c.title} ${c.start}~${c.end}${c.canceled ? " · 휴강" : ""}`}
        >
          {c.title}
        </div>
      ))}
      {day.events.map((e, i) => (
        <div
          key={`e${i}`}
          className="absolute inset-x-0.5 overflow-hidden rounded border border-info-line bg-info-soft px-1 text-[11px] leading-tight text-info-text"
          style={pos(e.start, e.end)}
          title={`일정 · ${e.title} ${e.start}~${e.end}`}
        >
          {e.title}
        </div>
      ))}
      {kept.map((b) => (
        <div
          key={b.id}
          className="absolute inset-x-0.5 overflow-hidden rounded border border-dashed border-study bg-study-soft px-1 text-[11px] leading-tight text-study"
          style={pos(b.start, b.end)}
          title={`이미 있는 블록 · ${b.title} ${b.start}~${b.end} · ${b.done ? "완료" : b.auto ? "자동" : "고정"} · ${b.reason}`}
        >
          {b.title}
        </div>
      ))}
      {blocks.map((b) => (
        <div
          key={b.key}
          className={`group absolute inset-x-0.5 flex items-start gap-0.5 overflow-hidden rounded border px-1 text-[11px] leading-tight font-semibold focus-within:ring-2 focus-within:ring-study ${blockCls(b.taskType)}`}
          style={pos(b.start, b.end)}
        >
          {/* 호버·포커스하면 근거 — '운영체제 15쪽 · 9/26 분량 · 공강 60분' (F8-S03) */}
          <button
            type="button"
            className="min-w-0 flex-1 cursor-default truncate text-left outline-none"
            title={`${b.start}~${b.end} [${TASK_LABEL[b.taskType]}] ${b.title}${b.part ? ` (${b.part})` : ""}\n${b.reason}`}
            aria-label={`${b.date.slice(5).replace("-", "/")} ${b.start}부터 ${b.end}까지 ${TASK_LABEL[b.taskType]} ${b.title}. ${b.reason}`}
          >
            <span className="num block font-normal opacity-80">
              {b.start} · {TASK_LABEL[b.taskType]}
            </span>
            {b.title}
          </button>
          <DropButton block={b} onDrop={onDrop} />
        </div>
      ))}
    </div>
  );
}

function DropButton({ block, onDrop }: { block: PlannedBlock; onDrop: (key: string) => void }) {
  return (
    <button
      type="button"
      className="grid size-4 flex-none place-items-center rounded opacity-60 hover:bg-study hover:text-on-study hover:opacity-100 focus-visible:opacity-100"
      aria-label={`${block.title} ${block.start} 블록 빼기`}
      title="이 블록 빼기"
      onClick={() => onDrop(block.key)}
    >
      <X className="size-3" aria-hidden />
    </button>
  );
}

/* ---------------------------------------------------------------- 하루 합계 (F8-S06) — 상한은 없다 */

function DailyTotals({ data }: { data: Preview }) {
  const wd = new Map(data.days.map((d) => [d.date, d.weekday]));
  return (
    <div className="flex flex-wrap items-center gap-2 text-[13px]">
      <span className="font-semibold text-muted">하루 합계</span>
      {data.dailyTotals.map((t) => (
        <span key={t.date} className={`num rounded-md px-2 py-0.5 ${t.minutes ? "bg-study-soft text-study" : "bg-surface-3 text-faint"}`} title={`새 블록 ${hm(t.newMinutes)} (공부 ${hm(t.studyMinutes)}) · 이미 있는 블록 ${hm(t.keptMinutes)}`}>
          {wd.get(t.date)} {t.minutes ? hm(t.minutes) : "0"}
        </span>
      ))}
    </div>
  );
}

/* ---------------------------------------------------------------- 공부 과목 고르는 순서 (2026-10-07) */

function StudyOrder({ data }: { data: Preview }) {
  if (!data.settings.fillStudy || data.studyTargets.length === 0) return null;
  return (
    <details className="rounded-xl border border-border bg-surface-2 px-3 py-2 text-[13px]">
      <summary className="cursor-pointer font-semibold text-muted">
        공부 과목 고르는 순서 — 남은 진도율 ÷ 시험까지 남은 날수 (같은 날 같은 과목은 반씩 감점)
      </summary>
      <ol className="mt-2 space-y-1">
        {data.studyTargets.map((t, i) => (
          <li key={t.examId} className="flex flex-wrap items-center gap-x-2">
            <span className="num w-5 text-faint">{i + 1}</span>
            <span className="size-2.5 flex-none rounded-full" style={{ background: t.color }} aria-hidden />
            <Link href={t.href} className="font-semibold hover:underline">
              {t.title}
            </Link>
            <span className="num text-muted">
              남은 진도 {100 - Math.round(t.percent)}% · D-{t.dday}
              {t.isAuto ? " · 임의 일정" : ""}
            </span>
          </li>
        ))}
      </ol>
    </details>
  );
}

/* ---------------------------------------------------------------- 미배치 + 조정 제안 (F8-S05) */

function UnplacedPanel({ data, onAdjust }: { data: Preview; onAdjust: (patch: Record<string, unknown>, label: string) => void }) {
  const missing = data.unplaced;
  return (
    <>
      {missing.length > 0 && (
        <Banner
          tone={data.state.allUnplaced ? "danger" : "warn"}
          action={
            data.adjustments.length > 0 ? (
              <>
                {data.adjustments.map((a) => (
                  <button key={a.key} type="button" className="btn btn-sm" title={a.text} onClick={() => onAdjust(a.patch, a.label)}>
                    {a.label}
                  </button>
                ))}
              </>
            ) : undefined
          }
        >
          <b>배치하지 못함 {missing.length}건</b>
          <ul className="mt-1 space-y-0.5 font-normal">
            {missing.map((u) => (
              <li key={`${u.refId}-${u.reasonKey}`}>
                {u.text}
              </li>
            ))}
          </ul>
        </Banner>
      )}
      {data.deferred.length > 0 && (
        <ul className="space-y-0.5 text-[13px] text-muted">
          {data.deferred.map((x) => (
            <li key={x.refId}>
              · {x.title} — {x.text}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
