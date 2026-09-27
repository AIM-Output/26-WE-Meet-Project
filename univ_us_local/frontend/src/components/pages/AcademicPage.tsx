"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { CalendarCheck, ChevronDown, ExternalLink, Inbox, Landmark, RefreshCw, RotateCcw } from "lucide-react";
import { Page, PageHeader } from "@/components/ui/Layout";
import { Tabs } from "@/components/ui/Tabs";
import { Banner, DemoNotice, EmptyState } from "@/components/ui/Feedback";
import { Chip, DdayChip, StatusBadge } from "@/components/ui/Chip";
import { useToast } from "@/components/ui/Toast";
import { EventDetailHost } from "@/components/events/EventDetailHost";
import { AcademicIcon } from "@/components/academic/AcademicIcon";
import { useAcademic } from "@/lib/useAcademic";
import { useProfile } from "@/lib/useProfile";
import { navigateQuery, useQueryParam } from "@/lib/useQueryState";
import { DEMO_SEMESTERS, type AcademicEvent } from "@/lib/demo";
import { fmtMD, fmtTime, parseLocal, startOfDay } from "@/lib/dates";

// /academic — 학기 전체 일정표 (Frontend-Route 6-3). 목록이고, 일정을 그리는 곳은 `/` 캘린더뿐이다.

const TABS = ["all", "mine", "review", "hidden"] as const;
type Tab = (typeof TABS)[number];

function period(e: AcademicEvent) {
  const s = parseLocal(e.start);
  const t = (d: Date, has: boolean) => `${fmtMD(d)}${has ? ` ${fmtTime(d)}` : ""}`;
  if (!e.end) return t(s, !e.allDay);
  return `${t(s, !e.allDay)} ~ ${t(parseLocal(e.end), !e.allDay)}`;
}

function When({ e }: { e: AcademicEvent }) {
  const today = startOfDay(new Date());
  const s = startOfDay(parseLocal(e.start));
  const end = e.end ? startOfDay(parseLocal(e.end)) : s;
  if (s <= today && today <= end && e.end) return <Chip tone="primary">진행 중</Chip>;
  return <DdayChip date={s} />;
}

export default function AcademicPage() {
  const toast = useToast();
  const { list, update } = useAcademic();
  const { complete } = useProfile();
  const [tab, setTab] = useQueryParam<Tab>("tab", "all", TABS);
  const [semester, setSemester] = useQueryParam<string>("semester", DEMO_SEMESTERS[0], DEMO_SEMESTERS);
  const [syncing, setSyncing] = useState(false);

  const inSemester = useMemo(() => (semester === "2026-2" ? list : []), [semester, list]);
  const confirmed = useMemo(() => inSemester.filter((e) => e.status === "confirmed"), [inSemester]);
  const counts = {
    all: confirmed.length,
    mine: confirmed.filter((e) => e.appliesToMe === true).length,
    review: inSemester.filter((e) => e.status === "review").length,
    hidden: inSemester.filter((e) => e.status === "hidden").length,
  };

  const rows = useMemo(() => {
    const src =
      tab === "mine" ? confirmed.filter((e) => e.appliesToMe === true) : tab === "hidden" ? inSemester.filter((e) => e.status === "hidden") : confirmed;
    return [...src].sort((a, b) => a.start.localeCompare(b.start));
  }, [tab, confirmed, inSemester]);

  const months = useMemo(() => {
    const m = new Map<string, AcademicEvent[]>();
    for (const r of rows) {
      const k = r.start.slice(0, 7);
      m.set(k, [...(m.get(k) ?? []), r]);
    }
    return [...m.entries()];
  }, [rows]);

  // 첫 진입: 오늘 이후 첫 항목이 화면 위 1/3 지점에 오도록 (6-3)
  const firstUpcoming = useRef<HTMLLIElement | null>(null);
  const scrolled = useRef(false);
  useEffect(() => {
    if (scrolled.current || tab === "review" || new URLSearchParams(window.location.search).get("event")) return;
    const el = firstUpcoming.current;
    if (!el) return;
    scrolled.current = true;
    const top = el.getBoundingClientRect().top + window.scrollY - window.innerHeight / 3;
    if (top > 0) window.scrollTo({ top });
  }, [rows, tab]);

  const todayKey = new Date().toISOString().slice(0, 10);
  let upcomingMarked = false;

  return (
    <Page>
      <PageHeader
        icon={<Landmark />}
        title="학사일정"
        meta={<span className="num">수집: 오늘 06:00 · 24건</span>}
        actions={
          <>
            <label className="sr-only" htmlFor="semester">
              학기
            </label>
            <select id="semester" className="field field-sm w-auto" value={semester} onChange={(e) => setSemester(e.target.value)}>
              {DEMO_SEMESTERS.map((s) => (
                <option key={s} value={s}>
                  {s.replace("-", "-")}학기
                </option>
              ))}
            </select>
            <button
              type="button"
              className="btn btn-sm"
              disabled={syncing}
              onClick={() => {
                setSyncing(true);
                window.setTimeout(() => {
                  setSyncing(false);
                  toast("학사일정 수집 API 가 아직 없습니다 — 예시 데이터를 보여 줍니다");
                }, 900);
              }}
            >
              <RefreshCw className={syncing ? "animate-spin" : ""} aria-hidden />
              {syncing ? "수집 중…" : "동기화"}
            </button>
          </>
        }
      />

      <div className="mb-5 space-y-3">
        <DemoNotice what="학사일정" />
        {!complete && (
          <Banner
            tone="info"
            action={
              <Link href="/onboarding?step=1" className="btn btn-sm">
                입력하기
              </Link>
            }
          >
            학년·소속을 입력하면 나에게 해당하는 일정만 골라 드립니다
          </Banner>
        )}
      </div>

      <Tabs
        className="mb-5"
        label="학사일정 분류"
        value={tab}
        onChange={(t) => setTab(t)}
        items={[
          { key: "all", label: "전체", count: counts.all },
          { key: "mine", label: "내 해당", count: counts.mine },
          { key: "review", label: "확인 필요", count: counts.review || undefined },
          { key: "hidden", label: "숨김", count: counts.hidden || undefined },
        ]}
      />

      {semester !== "2026-2" ? (
        <EmptyState icon={<Inbox />} title="아직 수집한 학사일정이 없습니다" action={<button type="button" className="btn btn-primary btn-sm">지금 수집하기</button>} />
      ) : tab === "review" ? (
        <ReviewList items={inSemester.filter((e) => e.status === "review")} update={update} />
      ) : rows.length === 0 ? (
        <EmptyState icon={<Inbox />} title={tab === "hidden" ? "숨긴 일정이 없습니다" : "아직 수집한 학사일정이 없습니다"} />
      ) : (
        <div className="space-y-6">
          {months.map(([month, items]) => (
            <section key={month} aria-labelledby={`m-${month}`}>
              <h2 id={`m-${month}`} className="num sticky top-[var(--header-h)] z-10 -mx-1 mb-2 bg-bg/95 px-1 py-1.5 text-[14px] font-bold text-muted backdrop-blur">
                {month.slice(0, 4)}년 {Number(month.slice(5))}월
              </h2>
              <ul className="overflow-hidden rounded-xl border border-border bg-surface">
                {items.map((e) => {
                  const past = (e.end ?? e.start).slice(0, 10) < todayKey;
                  const isFirst = !past && !upcomingMarked;
                  if (isFirst) upcomingMarked = true;
                  return (
                    <li key={e.id} ref={isFirst ? firstUpcoming : undefined} className="border-b border-border last:border-b-0">
                      <div className={`flex items-center gap-3 px-3 py-3 transition-colors hover:bg-surface-2 md:px-4 ${past ? "opacity-55" : ""}`}>
                        <button type="button" className="flex min-w-0 flex-1 items-center gap-3 text-left" onClick={() => navigateQuery({ event: e.id }, "push")}>
                          <AcademicIcon type={e.type} />
                          <span className="min-w-0 flex-1">
                            <span className={`block truncate text-[15px] font-semibold ${e.appliesToMe === false ? "text-muted" : ""}`}>{e.title}</span>
                            <span className="num flex flex-wrap items-center gap-x-2 text-[13px] text-muted">
                              {period(e)}
                              <span className="text-faint md:hidden">· {e.source}</span>
                            </span>
                          </span>
                          <span className="hidden flex-none items-center gap-1.5 sm:flex">
                            {e.changedFrom && <Chip tone="warn">변경됨</Chip>}
                            {e.appliesToMe === true && <StatusBadge tone="ok">내 해당</StatusBadge>}
                            {e.appliesToMe === false && <StatusBadge tone="neutral">해당 없음</StatusBadge>}
                            {e.appliesToMe === null && <StatusBadge tone="warn" unknown>판단 불가</StatusBadge>}
                          </span>
                          <span className="hidden w-24 flex-none truncate text-right text-[12px] text-faint md:block">{e.source}</span>
                          <span className="w-16 flex-none text-right">
                            <When e={e} />
                          </span>
                        </button>
                        {tab === "hidden" && (
                          <button
                            type="button"
                            className="btn btn-sm flex-none"
                            onClick={() => {
                              update(e.id, { status: "confirmed" });
                              toast("다시 보이게 했습니다");
                            }}
                          >
                            <RotateCcw aria-hidden />
                            복원
                          </button>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </div>
      )}

      <EventDetailHost />
    </Page>
  );
}

/** 확인 필요 — 목록이 아니라 카드(승인 동작이 있으므로). 날짜를 그 자리에서 고쳐 등록한다(F1-S09). */
function ReviewList({ items, update }: { items: AcademicEvent[]; update: ReturnType<typeof useAcademic>["update"] }) {
  const [weakOpen, setWeakOpen] = useState(false);
  const strong = items.filter((e) => e.confidence >= 0.5);
  const weak = items.filter((e) => e.confidence < 0.5);
  if (items.length === 0) return <EmptyState icon={<CalendarCheck />} title="확인할 항목이 없습니다" />;
  return (
    <div className="space-y-3">
      <AnimatePresence initial={false}>
        {strong.map((e) => (
          <ReviewCard key={e.id} e={e} update={update} />
        ))}
      </AnimatePresence>
      {weak.length > 0 && (
        <div>
          <button type="button" className="btn btn-ghost btn-sm" aria-expanded={weakOpen} onClick={() => setWeakOpen((v) => !v)}>
            근거가 약한 항목 {weak.length}건
            <ChevronDown className={`transition-transform ${weakOpen ? "rotate-180" : ""}`} aria-hidden />
          </button>
          {weakOpen && (
            <div className="mt-2 space-y-3">
              {weak.map((e) => (
                <ReviewCard key={e.id} e={e} update={update} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ReviewCard({ e, update }: { e: AcademicEvent; update: ReturnType<typeof useAcademic>["update"] }) {
  const toast = useToast();
  const [start, setStart] = useState(e.start);
  const [end, setEnd] = useState(e.end ?? "");
  const withTime = e.start.includes("T");

  return (
    <motion.article
      layout
      exit={{ opacity: 0, x: 24, transition: { duration: 0.15 } }}
      className="card p-4 md:p-5"
      aria-labelledby={`rv-${e.id}`}
    >
      <div className="flex items-start gap-3">
        <AcademicIcon type={e.type} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 id={`rv-${e.id}`} className="text-[16px] font-bold">
              {e.title}
            </h3>
            <Chip tone={e.confidence < 0.5 ? "danger" : "warn"} square>
              신뢰도 <span className="num">{e.confidence.toFixed(2)}</span>
            </Chip>
          </div>
          <div className="mt-3 flex flex-wrap items-end gap-3">
            <label className="text-[13px] font-semibold text-muted">
              시작
              <input className="field field-sm mt-1 block w-auto" type={withTime ? "datetime-local" : "date"} value={start} onChange={(x) => setStart(x.target.value)} />
            </label>
            <label className="text-[13px] font-semibold text-muted">
              종료
              <input className="field field-sm mt-1 block w-auto" type={withTime ? "datetime-local" : "date"} value={end} onChange={(x) => setEnd(x.target.value)} />
            </label>
          </div>
          <blockquote className="mt-3 border-l-2 border-primary pl-3 text-[14px] text-muted">&ldquo;{e.evidence}&rdquo;</blockquote>
          <p className="mt-2 flex flex-wrap items-center gap-2 text-[13px] text-faint">
            출처: {e.source}
            <a href={e.sourceUrl} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 font-semibold text-primary hover:underline">
              원문 보기
              <ExternalLink className="size-3.5" aria-hidden />
            </a>
          </p>
        </div>
      </div>
      <div className="mt-4 flex justify-end gap-2 border-t border-border pt-3">
        <button
          type="button"
          className="btn btn-sm"
          onClick={() => {
            update(e.id, { status: "hidden" });
            toast("숨겼습니다", { action: { label: "되돌리기", onClick: () => update(e.id, { status: "review" }) } });
          }}
        >
          필요 없음
        </button>
        <button
          type="button"
          className="btn btn-primary btn-sm"
          onClick={() => {
            update(e.id, { status: "confirmed", start, end: end || null });
            toast("등록했습니다", { tone: "success" });
          }}
        >
          <CalendarCheck aria-hidden />
          캘린더에 등록
        </button>
      </div>
    </motion.article>
  );
}
