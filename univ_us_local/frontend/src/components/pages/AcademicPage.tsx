"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { CalendarCheck, CalendarPlus, CheckCheck, ChevronDown, ExternalLink, Inbox, Landmark, RefreshCw, RotateCcw, Sparkles, TriangleAlert } from "lucide-react";
import { Page, PageHeader } from "@/components/ui/Layout";
import { Tabs } from "@/components/ui/Tabs";
import { Banner, EmptyState, ErrorPanel } from "@/components/ui/Feedback";
import { Chip, DdayChip, StatusBadge } from "@/components/ui/Chip";
import { useToast } from "@/components/ui/Toast";
import { EventDetailHost } from "@/components/events/EventDetailHost";
import { AcademicIcon } from "@/components/academic/AcademicIcon";
import { useAppData } from "@/components/app/AppData";
import { AcademicSourceStrip } from "@/components/academic/AcademicSources";
import { api } from "@/lib/api";
import { useAcademic } from "@/lib/useAcademic";
import { useProfile } from "@/lib/useProfile";
import { navigateQuery, useQueryParam } from "@/lib/useQueryState";
import { academicPeriod, isConfirmed, lastDay, semesterLabel, toInputs, type AcademicEvent } from "@/lib/academic";
import { fmtRelative, parseLocal, startOfDay, toDateStr } from "@/lib/dates";

// /academic — 학기 전체 일정표 (Frontend-Route 6-3). 목록이고, 일정을 그리는 곳은 `/` 캘린더뿐이다.
// 데이터: GET /api/academic/events 한 번 → 탭·학기 전환은 화면에서 거른다(재요청 없음, 6-9).

const TABS = ["all", "mine", "review", "hidden"] as const;
type Tab = (typeof TABS)[number];

function When({ e }: { e: AcademicEvent }) {
  if (!e.start) return null;
  const today = startOfDay(new Date());
  const s = startOfDay(parseLocal(e.start));
  const end = startOfDay(lastDay(e)!);
  if (s <= today && today <= end && end > s) return <Chip tone="primary">진행 중</Chip>;
  return <DdayChip date={s} />;
}

export default function AcademicPage() {
  const toast = useToast();
  const { data, list, loading, error, update, sync, syncing, status, refresh } = useAcademic();
  const { doc: profileDoc, complete } = useProfile();
  const { events } = useAppData();
  // '내 일정에 넣기'로 만든 내 일정이 가리키는 학사 일정 id
  const inMine = useMemo(
    () => new Set(events.flatMap((e) => (e.extendedProps.kind === "user" && e.extendedProps.origin ? [e.extendedProps.origin] : []))),
    [events],
  );
  const semesters = data?.semesters ?? [];
  const [tab, setTab] = useQueryParam<Tab>("tab", "all", TABS);
  const [semester, setSemester] = useQueryParam<string>("semester", data?.currentSemester ?? "", semesters);
  const sem = semester || data?.currentSemester || "";

  const inSemester = useMemo(() => list.filter((e) => e.semester === sem), [list, sem]);
  const confirmed = useMemo(() => inSemester.filter(isConfirmed), [inSemester]);
  // 확인 필요 — 대시보드 '확인 필요 N건'과 같은 기준: 학기와 상관없이 아직 끝나지 않은 것(날짜를 못 읽은 것 포함).
  // 이미 지난 것은 승인해도 쓸모가 없어 아래에 접어 두고 세지 않는다.
  const { review, reviewPast } = useMemo(() => {
    const today = toDateStr(new Date());
    const all = list.filter((e) => e.status === "review");
    const ended = (e: AcademicEvent) => !!e.start && toDateStr(lastDay(e)!) < today;
    return { review: all.filter((e) => !ended(e)), reviewPast: all.filter(ended) };
  }, [list]);
  const hidden = useMemo(() => inSemester.filter((e) => e.status === "hidden"), [inSemester]);
  const mineOf = (e: AcademicEvent) => e.appliesToMe === true || e.pinned;
  const counts = {
    all: confirmed.length,
    mine: confirmed.filter(mineOf).length,
    review: review.length,
    hidden: hidden.length,
  };

  // 마지막 수집에서 새로 찾은 일정 — 학기와 상관없이 목록 맨 위에 모은다. '전체 확인' 전까지는 날짜순 목록에서 뺀다.
  // 이미 지난 일정(학과 게시판의 옛 글 등)은 새로 찾았어도 쓸모가 없어 날짜순 목록에만 둔다 — 대시보드 '신규 일정'과 같은 기준
  const isFresh = (e: AcademicEvent) => e.isNew && isConfirmed(e) && !!e.start && toDateStr(lastDay(e)!) >= toDateStr(new Date());
  const fresh = useMemo(() => {
    if (tab !== "all" && tab !== "mine") return [];
    const src = list.filter((e) => isFresh(e) && (tab === "all" || mineOf(e)));
    return [...src].sort((a, b) => (a.start ?? "").localeCompare(b.start ?? "") || a.title.localeCompare(b.title));
  }, [list, tab]);

  const rows = useMemo(() => {
    const src = tab === "mine" ? confirmed.filter(mineOf) : tab === "hidden" ? hidden : confirmed;
    return [...src].filter((e) => tab === "hidden" || !isFresh(e)).sort((a, b) => (a.start ?? "").localeCompare(b.start ?? "") || a.title.localeCompare(b.title));
  }, [tab, confirmed, hidden]);

  const months = useMemo(() => {
    const m = new Map<string, AcademicEvent[]>();
    for (const r of rows) {
      const k = (r.start ?? "").slice(0, 7);
      m.set(k, [...(m.get(k) ?? []), r]);
    }
    return [...m.entries()];
  }, [rows]);

  // 첫 진입: 오늘 이후 첫 항목이 화면 위 1/3 지점에 오도록 (6-3). 새로 수집된 묶음이 있으면 그것이 먼저 보이게 맨 위에 둔다
  const firstUpcoming = useRef<HTMLLIElement | null>(null);
  const scrolled = useRef(false);
  useEffect(() => {
    if (scrolled.current || tab === "review" || new URLSearchParams(window.location.search).get("event")) return;
    if (fresh.length > 0) {
      scrolled.current = true;
      return;
    }
    const el = firstUpcoming.current;
    if (!el) return;
    scrolled.current = true;
    const top = el.getBoundingClientRect().top + window.scrollY - window.innerHeight / 3;
    if (top > 0) window.scrollTo({ top });
  }, [rows, tab, fresh.length]);

  const todayKey = toDateStr(new Date());
  let upcomingMarked = false;

  // 헤더 메타: 원천 중 가장 최근 성공 시각 · 이 학기 건수 (F1-S04)
  const sources = (status?.sources ?? []).filter((s) => s.enabled);
  const lastOk = sources.map((s) => s.lastOkAt).filter(Boolean).sort().at(-1) ?? null;
  const failed = sources.filter((s) => s.state === "failed" || s.state === "format_changed");
  const never = status?.available && !lastOk;
  const allOff = (status?.sources ?? []).length > 0 && sources.length === 0;

  return (
    <Page>
      <PageHeader
        icon={<Landmark />}
        title="학사일정"
        meta={
          <span className="num">
            {lastOk ? `수집: ${fmtRelative(lastOk)} · ${semesterLabel(sem)} ${counts.all}건` : "아직 수집하지 않았습니다"}
            {" · "}
            <Link href="/settings/sources" className="underline-offset-2 hover:underline">
              수집 원천
            </Link>
          </span>
        }
        actions={
          <>
            <label className="sr-only" htmlFor="semester">
              학기
            </label>
            <select id="semester" className="field field-sm w-auto" value={sem} onChange={(e) => setSemester(e.target.value)} disabled={!semesters.length}>
              {semesters.map((s) => (
                <option key={s} value={s}>
                  {semesterLabel(s)}
                </option>
              ))}
            </select>
            <button type="button" className="btn btn-sm" disabled={syncing || status?.available === false} onClick={() => void sync()}>
              <RefreshCw className={syncing ? "animate-spin" : ""} aria-hidden />
              {syncing ? "수집 중…" : "동기화"}
            </button>
          </>
        }
      />

      <div className="mb-5 space-y-3">
        {status?.available !== false && <AcademicSourceStrip />}
        {status?.available === false && (
          <Banner tone="danger">학사일정 기능을 불러오지 못했습니다 — {status.error ?? "F1_Bachelor_agent 폴더를 확인하세요"}</Banner>
        )}
        {failed.length > 0 && !syncing && (
          <Banner
            tone="danger"
            action={
              <Link href="/settings/sources" className="btn btn-sm">
                수집 원천
              </Link>
            }
          >
            {failed.map((s) => `${s.name}: ${s.error ?? "실패"}`).join(" / ")} — 다른 원천의 일정은 그대로 보입니다
          </Banner>
        )}
        {profileDoc && (!complete || data?.profileMissing || !profileDoc.profile.grade) && (
          <Banner
            tone="info"
            action={
              <Link href="/settings/profile" className="btn btn-sm">
                입력하기
              </Link>
            }
          >
            학년·소속을 입력하면 나에게 해당하는 일정만 골라 캘린더에 넣어 드립니다
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

      {error && !data ? (
        <ErrorPanel message="학사일정을 불러오지 못했습니다" onRetry={() => void refresh()} />
      ) : loading ? (
        <ListSkeleton />
      ) : allOff ? (
        <EmptyState icon={<Inbox />} title="가져오는 곳을 모두 껐습니다">
          위의 원천을 하나 이상 켜면 그곳의 학사 일정이 다시 보입니다
        </EmptyState>
      ) : never || list.length === 0 ? (
        <EmptyState
          icon={<Inbox />}
          title="아직 수집한 학사일정이 없습니다"
          action={
            <button type="button" className="btn btn-primary btn-sm" disabled={syncing} onClick={() => void sync()}>
              <RefreshCw className={syncing ? "animate-spin" : ""} aria-hidden />
              {syncing ? "수집 중…" : "지금 수집하기"}
            </button>
          }
        />
      ) : tab === "review" ? (
        <ReviewList items={review} past={reviewPast} update={update} />
      ) : rows.length === 0 && fresh.length === 0 ? (
        <EmptyState icon={<Inbox />} title={tab === "hidden" ? "숨긴 일정이 없습니다" : tab === "mine" ? "이 학기에 나에게 해당하는 일정이 없습니다" : "이 학기의 학사일정이 없습니다"} />
      ) : (
        <div className="space-y-6">
          {fresh.length > 0 && <NewSection items={fresh} inMine={inMine} sem={sem} lastRunAt={status?.lastRunAt} />}
          {months.map(([month, items]) => (
            <section key={month} aria-labelledby={`m-${month}`}>
              <h2 id={`m-${month}`} className="num sticky top-[var(--header-h)] z-10 -mx-1 mb-2 bg-bg/95 px-1 py-1.5 text-[14px] font-bold text-muted backdrop-blur">
                {month.slice(0, 4)}년 {Number(month.slice(5))}월
              </h2>
              <ul className="overflow-hidden rounded-xl border border-border bg-surface">
                {items.map((e) => {
                  const past = toDateStr(lastDay(e)!) < todayKey;
                  const isFirst = !past && !upcomingMarked;
                  if (isFirst) upcomingMarked = true;
                  return (
                    <EventRow
                      key={e.id}
                      e={e}
                      past={past}
                      added={inMine.has(e.id)}
                      hiddenTab={tab === "hidden"}
                      liRef={isFirst ? firstUpcoming : undefined}
                      onRestore={() => {
                        void update(e.id, { status: "restore" });
                        toast("다시 보이게 했습니다");
                      }}
                    />
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

/** 목록 한 줄 — 날짜순 목록과 위쪽 '새로 수집된 학사일정' 묶음이 같이 쓴다 */
function EventRow({
  e,
  past,
  added,
  hiddenTab,
  liRef,
  onRestore,
  semesterChip,
}: {
  e: AcademicEvent;
  past: boolean;
  added: boolean;
  hiddenTab?: boolean;
  liRef?: React.Ref<HTMLLIElement>;
  onRestore?: () => void;
  /** 신규 묶음은 학기를 가리지 않으므로 다른 학기 것에 학기를 붙인다 */
  semesterChip?: string | null;
}) {
  const canAdd = !hiddenTab && !added && !past;
  return (
    <li ref={liRef} className="border-b border-border last:border-b-0">
      <div className={`flex items-center gap-3 px-3 py-3 transition-colors hover:bg-surface-2 md:px-4 ${past ? "opacity-55" : ""}`}>
        <button type="button" className="flex min-w-0 flex-1 items-center gap-3 text-left" onClick={() => navigateQuery({ event: e.id }, "push")}>
          <AcademicIcon type={e.type} />
          <span className="min-w-0 flex-1">
            <span className={`block truncate text-[15px] font-semibold ${e.appliesToMe === false && !e.pinned ? "text-muted" : ""}`}>{e.title}</span>
            <span className="num flex flex-wrap items-center gap-x-2 text-[13px] text-muted">
              {academicPeriod(e)}
              {semesterChip && <span className="text-faint">· {semesterChip}</span>}
              <span className="text-faint md:hidden">· {e.sources[0]?.name}</span>
            </span>
          </span>
          <span className="hidden flex-none items-center gap-1.5 sm:flex">
            {e.isNew && !past && <Chip tone="primary">신규</Chip>}
            {e.changed && <Chip tone="warn">변경됨</Chip>}
            {e.removed && <Chip tone="danger" square>원문 삭제됨</Chip>}
            {e.pinned && <Chip tone="primary" square>담음</Chip>}
            {added && (
              <Chip tone="ok" square icon={<CalendarCheck className="size-3" aria-hidden />}>
                내 일정
              </Chip>
            )}
            {e.appliesToMe === true && <StatusBadge tone="ok">내 해당</StatusBadge>}
            {e.appliesToMe === false && <StatusBadge tone="neutral">해당 없음</StatusBadge>}
            {e.appliesToMe === null && <StatusBadge tone="warn" unknown>판단 불가</StatusBadge>}
          </span>
          <span className="hidden w-28 flex-none truncate text-right text-[12px] text-faint md:block">{e.sources[0]?.name}</span>
          <span className="w-16 flex-none text-right">
            <When e={e} />
          </span>
        </button>
        {hiddenTab && onRestore && (
          <button type="button" className="btn btn-sm flex-none" onClick={onRestore}>
            <RotateCcw aria-hidden />
            복원
          </button>
        )}
        {canAdd && (
          <button
            type="button"
            className="btn btn-ghost btn-icon btn-sm flex-none"
            title="내 일정에 넣기"
            aria-label={`${e.title} 내 일정에 넣기`}
            onClick={() => navigateQuery({ event: e.id, add: "1" }, "push")}
          >
            <CalendarPlus aria-hidden />
          </button>
        )}
      </div>
    </li>
  );
}

/** 마지막 수집에서 새로 찾은 일정 — 목록 맨 위에 모아 보여 주고, '전체 확인'을 누르면 날짜순 목록으로 돌아간다 */
function NewSection({ items, inMine, sem, lastRunAt }: { items: AcademicEvent[]; inMine: Set<string>; sem: string; lastRunAt?: string | null }) {
  const toast = useToast();
  const { refresh, refreshAcademic } = useAppData();
  const [busy, setBusy] = useState(false);
  const todayKey = toDateStr(new Date());
  const ack = async () => {
    setBusy(true);
    try {
      await api.ackNewAcademic();
      await Promise.all([refresh(), refreshAcademic()]);
      toast(`${items.length}건을 확인했습니다 — 날짜순 목록으로 옮겼습니다`, { tone: "success" });
    } catch (err) {
      toast(`확인하지 못했습니다: ${err instanceof Error ? err.message : String(err)}`, { tone: "error" });
    } finally {
      setBusy(false);
    }
  };
  return (
    <section aria-labelledby="new-academic" className="mb-6 rounded-2xl border border-primary-soft-2 bg-primary-soft p-3 md:p-4">
      <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-2">
        <Sparkles className="size-4 flex-none text-primary" aria-hidden />
        <h2 id="new-academic" className="text-[15px] font-bold text-primary">
          새로 수집된 학사일정 <span className="num">{items.length}</span>건
        </h2>
        {lastRunAt && <span className="text-[12px] text-muted">{fmtRelative(lastRunAt)} 수집</span>}
        <button type="button" className="btn btn-primary btn-sm ml-auto" disabled={busy} onClick={() => void ack()}>
          <CheckCheck aria-hidden />
          전체 확인
        </button>
      </div>
      <ul className="overflow-hidden rounded-xl border border-border bg-surface">
        {items.map((e) => (
          <EventRow
            key={e.id}
            e={e}
            past={toDateStr(lastDay(e)!) < todayKey}
            added={inMine.has(e.id)}
            semesterChip={e.semester && e.semester !== sem ? semesterLabel(e.semester) : null}
          />
        ))}
      </ul>
      <p className="mt-2 text-[12px] text-muted">확인하면 아래 날짜순 목록으로 들어갑니다. 다음 수집에서 새로 찾은 일정이 다시 여기에 모입니다.</p>
    </section>
  );
}

function ListSkeleton() {
  return (
    <ul className="overflow-hidden rounded-xl border border-border bg-surface" aria-busy="true" aria-label="불러오는 중">
      {Array.from({ length: 6 }, (_, i) => (
        <li key={i} className="flex items-center gap-3 border-b border-border px-4 py-3 last:border-b-0">
          <span className="size-8 flex-none animate-pulse rounded-lg bg-surface-3" />
          <span className="flex-1 space-y-2">
            <span className="block h-3.5 w-1/2 animate-pulse rounded bg-surface-3" />
            <span className="block h-3 w-1/4 animate-pulse rounded bg-surface-3" />
          </span>
        </li>
      ))}
    </ul>
  );
}

type Update = ReturnType<typeof useAcademic>["update"];

/** 확인 필요 — 목록이 아니라 카드(승인 동작이 있으므로). 날짜를 그 자리에서 고쳐 등록한다(F1-S09). */
function ReviewList({ items, past, update }: { items: AcademicEvent[]; past: AcademicEvent[]; update: Update }) {
  const [weakOpen, setWeakOpen] = useState(false);
  const [pastOpen, setPastOpen] = useState(false);
  const sorted = [...items].sort((a, b) => (a.start ?? "9").localeCompare(b.start ?? "9"));
  const strong = sorted.filter((e) => !e.weak);
  const weak = sorted.filter((e) => e.weak);
  const pastSorted = [...past].sort((a, b) => (b.start ?? "").localeCompare(a.start ?? ""));
  const pastGroup = past.length > 0 && (
    <div>
      <button type="button" className="btn btn-ghost btn-sm" aria-expanded={pastOpen} onClick={() => setPastOpen((v) => !v)}>
        이미 지난 항목 {past.length}건 <span className="font-normal text-faint">(건수에서 뺌)</span>
        <ChevronDown className={`transition-transform ${pastOpen ? "rotate-180" : ""}`} aria-hidden />
      </button>
      {pastOpen && (
        <div className="mt-2 space-y-3 opacity-80">
          <AnimatePresence initial={false}>
            {pastSorted.map((e) => (
              <ReviewCard key={e.id} e={e} update={update} />
            ))}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
  if (items.length === 0)
    return (
      <div className="space-y-3">
        <EmptyState icon={<CalendarCheck />} title="확인할 항목이 없습니다" />
        {pastGroup}
      </div>
    );
  return (
    <div className="space-y-3">
      <p className="text-[13px] text-muted">
        공지에서 찾았지만 신뢰도가 자동 등록 기준(0.80)보다 낮은 일정입니다. 날짜를 확인하고 등록하세요. 학기와 상관없이 아직 지나지 않은 것만 셉니다(대시보드와 같은 기준).
      </p>
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
              <AnimatePresence initial={false}>
                {weak.map((e) => (
                  <ReviewCard key={e.id} e={e} update={update} />
                ))}
              </AnimatePresence>
            </div>
          )}
        </div>
      )}
      {pastGroup}
    </div>
  );
}

function ReviewCard({ e, update }: { e: AcademicEvent; update: Update }) {
  const toast = useToast();
  const init = toInputs(e);
  const [withTime, setWithTime] = useState(init.withTime);
  const [start, setStart] = useState(init.start);
  const [end, setEnd] = useState(init.end);
  const [busy, setBusy] = useState(false);
  const src = e.sources[0];
  const bad = !start || (!!end && end < start);

  const approve = async () => {
    setBusy(true);
    const saved = await update(e.id, { status: "approved", start, end: end || null });
    setBusy(false);
    if (saved) toast("등록했습니다 — 캘린더에 들어갔습니다", { tone: "success" });
  };

  return (
    <motion.article layout exit={{ opacity: 0, x: 24, transition: { duration: 0.15 } }} className="card p-4 md:p-5" aria-labelledby={`rv-${e.id}`}>
      <div className="flex items-start gap-3">
        <AcademicIcon type={e.type} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 id={`rv-${e.id}`} className="text-[16px] font-bold">
              {e.title}
            </h3>
            <Chip tone={e.weak ? "danger" : "warn"} square>
              신뢰도 <span className="num">{e.confidence.toFixed(2)}</span>
            </Chip>
            {e.appliesToMe === false && <StatusBadge tone="neutral">해당 없음</StatusBadge>}
          </div>
          {e.needsOcr && (
            <p className="mt-2 flex items-center gap-1.5 text-[13px] font-medium text-warn-text">
              <TriangleAlert className="size-3.5" aria-hidden />
              본문이 이미지라 날짜를 읽지 못했습니다 — 원문을 보고 입력하세요
            </p>
          )}
          <div className="mt-3 flex flex-wrap items-end gap-3">
            <label className="text-[13px] font-semibold text-muted">
              시작
              <input
                className="field field-sm mt-1 block w-auto"
                type={withTime ? "datetime-local" : "date"}
                value={start}
                onChange={(x) => setStart(x.target.value)}
              />
            </label>
            <label className="text-[13px] font-semibold text-muted">
              {withTime ? "종료" : "마지막 날"}
              <input className="field field-sm mt-1 block w-auto" type={withTime ? "datetime-local" : "date"} value={end} onChange={(x) => setEnd(x.target.value)} />
            </label>
            <label className="flex h-9 items-center gap-1.5 text-[13px] text-muted">
              <input
                type="checkbox"
                checked={withTime}
                onChange={(x) => {
                  const on = x.target.checked;
                  setWithTime(on);
                  setStart((v) => (v ? (on ? `${v.slice(0, 10)}T09:00` : v.slice(0, 10)) : v));
                  setEnd((v) => (v ? (on ? `${v.slice(0, 10)}T18:00` : v.slice(0, 10)) : v));
                }}
              />
              시각 있음
            </label>
          </div>
          {e.evidence[0] && <blockquote className="mt-3 border-l-2 border-primary pl-3 text-[14px] text-muted">&ldquo;{e.evidence[0].quote}&rdquo;</blockquote>}
          {src && (
            <p className="mt-2 flex flex-wrap items-center gap-2 text-[13px] text-faint">
              출처: {src.name}
              {src.postedAt && <span className="num">· {src.postedAt}</span>}
              <a href={src.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 font-semibold text-primary hover:underline">
                원문 보기
                <ExternalLink className="size-3.5" aria-hidden />
              </a>
            </p>
          )}
        </div>
      </div>
      <div className="mt-4 flex justify-end gap-2 border-t border-border pt-3">
        <button
          type="button"
          className="btn btn-sm"
          onClick={() => {
            void update(e.id, { status: "hidden" });
            toast("숨겼습니다", { action: { label: "되돌리기", onClick: () => void update(e.id, { status: "restore" }) } });
          }}
        >
          필요 없음
        </button>
        <button type="button" className="btn btn-primary btn-sm" disabled={bad || busy} onClick={() => void approve()} title={bad ? "시작 날짜를 확인하세요" : undefined}>
          <CalendarCheck aria-hidden />
          캘린더에 등록
        </button>
      </div>
    </motion.article>
  );
}
