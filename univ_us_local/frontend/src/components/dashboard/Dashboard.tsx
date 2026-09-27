"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo } from "react";
import { PanelLeftOpen } from "lucide-react";
import { useAppData } from "@/components/app/AppData";
import { useToast } from "@/components/ui/Toast";
import { Tabs } from "@/components/ui/Tabs";
import { ErrorPanel } from "@/components/ui/Feedback";
import { EventDetailHost } from "@/components/events/EventDetailHost";
import { EventForm, DEFAULT_CATEGORIES, type EventDraft } from "@/components/events/EventForm";
import ActionPanel from "./ActionPanel";
import BriefingCard from "./BriefingCard";
import FeatureTiles from "./FeatureTiles";
import PlacementPreview from "./PlacementPreview";
import TodoPanel, { TopPriority } from "./TodoPanel";
import type { CalView } from "./CalendarView";
import { api } from "@/lib/api";
import { closeQuery, navigateQuery, useQueryParam, useQueryValue } from "@/lib/useQueryState";
import { readStore, writeStore } from "@/lib/storage";
import { useAcademic } from "@/lib/useAcademic";
import { composeBriefing } from "@/lib/demo";
import type { UserEventInput } from "@/lib/types";
import { addDays, parseLocal, toDateStr, toLocalIso, WEEKDAY_KO } from "@/lib/dates";

// `/` 대시보드 = 허브 (Frontend-Route 3절). 브리핑 → 3단(액션 / 캘린더 / 할 일) → 기능 타일.

function CalendarSkeleton() {
  return (
    <div aria-busy="true" aria-label="캘린더 불러오는 중">
      <div className="mb-3 flex items-center gap-2">
        <div className="skeleton h-8 w-40" />
        <div className="skeleton ml-auto h-8 w-52" />
      </div>
      <div className="grid grid-cols-7 gap-px overflow-hidden rounded-lg border border-border bg-border">
        {Array.from({ length: 35 }, (_, i) => (
          <div key={i} className="h-24 bg-surface p-2">
            <div className="skeleton ml-auto h-3 w-4" />
            {i % 4 === 1 && <div className="skeleton mt-3 h-4 w-4/5" />}
          </div>
        ))}
      </div>
    </div>
  );
}

const CalendarView = dynamic(() => import("./CalendarView"), { ssr: false, loading: CalendarSkeleton });

const VIEWS = ["month", "week", "list", "semester"] as const;
const FILTERS = ["all", "eclass", "mine", "todo", "academic"] as const;
type Filter = (typeof FILTERS)[number];
const FILTER_ITEMS: { key: Filter; label: string }[] = [
  { key: "all", label: "전체" },
  { key: "eclass", label: "e클래스" },
  { key: "mine", label: "내 일정" },
  { key: "todo", label: "할 일" },
  { key: "academic", label: "학사" },
];

export default function Dashboard() {
  const { events, status, loading, error, refresh } = useAppData();
  const toast = useToast();
  const { list: academic, reviewCount } = useAcademic();
  const [view, setView] = useQueryParam<CalView>("view", "month", VIEWS);
  const [filter, setFilter] = useQueryParam<Filter>("filter", "all", FILTERS);
  const dateParam = useQueryValue("date");
  const newKind = useQueryValue("new");

  // URL 에 없으면 마지막으로 보던 뷰·필터로 (URL 이 이긴다, 4-2)
  useEffect(() => {
    const sp = new URLSearchParams(window.location.search);
    const saved = readStore<{ view?: CalView; filter?: Filter }>("calendar", {});
    const upd: Record<string, string> = {};
    if (!sp.get("view") && saved.view && saved.view !== "month") upd.view = saved.view;
    // 폰에서는 한 달 격자가 좁다 — 고른 적이 없으면 목록으로 시작(Frontend-Figma 4-13)
    else if (!sp.get("view") && !saved.view && window.innerWidth < 768) upd.view = "list";
    if (!sp.get("filter") && saved.filter && saved.filter !== "all") upd.filter = saved.filter;
    if (Object.keys(upd).length) navigateQuery(upd, "replace");
  }, []);
  useEffect(() => writeStore("calendar", { view, filter }), [view, filter]);

  const briefing = useMemo(() => (new Date().getHours() >= 8 ? composeBriefing(events) : null), [events]);

  const calEvents = useMemo(() => {
    switch (filter) {
      case "eclass":
        return events.filter((e) => e.extendedProps.kind === "deadline");
      case "mine":
        return events.filter((e) => e.extendedProps.kind === "user" && !e.extendedProps.isTodo);
      case "todo":
        return events.filter((e) => e.extendedProps.kind === "user" && e.extendedProps.isTodo);
      case "academic":
        return [];
      default:
        return events;
    }
  }, [events, filter]);
  const calAcademic = useMemo(
    () => (filter === "all" || filter === "academic" ? academic.filter((a) => a.status === "confirmed" && a.appliesToMe !== false) : []),
    [academic, filter],
  );

  const openNew = (kind: "event" | "todo", start?: string, end?: string, allDay?: boolean) =>
    navigateQuery({ new: kind, start, end, allDay: allDay ? "1" : null }, "push");

  // 새 일정 초안 — `?new=event&start=&end=&allDay=1`
  const draft = useMemo<EventDraft | null>(() => {
    if (newKind !== "event" && newKind !== "todo") return null;
    const sp = new URLSearchParams(typeof window === "undefined" ? "" : window.location.search);
    const s = sp.get("start");
    const e = sp.get("end");
    const allDay = sp.get("allDay") === "1" || newKind === "todo";
    let start: Date;
    if (s) start = parseLocal(s);
    else {
      start = new Date();
      start.setMinutes(0, 0, 0);
      start.setHours(start.getHours() + 1);
    }
    const end = e ? parseLocal(e) : allDay ? null : new Date(start.getTime() + 3_600_000);
    return { title: "", start, end, allDay, category: newKind === "todo" ? "study" : "personal", memo: "", isTodo: newKind === "todo", done: false };
  }, [newKind]);

  const today = new Date();
  const todayCount = briefing ? briefing.events.length : 0;
  const semester = view === "semester";

  return (
    <main id="main" className="mx-auto w-full max-w-[1600px] px-4 pt-6 pb-28 md:px-6 md:pt-8">
      <div className="mb-5 flex flex-wrap items-end gap-x-6 gap-y-2">
        <div>
          <p className="text-[13px] font-semibold tracking-wide text-primary" style={{ fontFamily: "var(--font-display)" }}>
            Univ-Us Planner
          </p>
          <h1 className="text-[26px] font-bold tracking-tight md:text-[30px]">
            {today.getMonth() + 1}월 {today.getDate()}일 {WEEKDAY_KO[today.getDay()]}요일
          </h1>
        </div>
        <p className="pb-1 text-[14px] text-muted">
          오늘 일정 <b className="num text-text">{todayCount}</b> · 3일 안 마감 <b className="num text-text">{briefing?.deadlines.length ?? 0}</b>
          {status && <> · 과목 <b className="num text-text">{status.counts.courses}</b></>}
        </p>
      </div>

      <div className="mb-5">
        <BriefingCard b={briefing} />
      </div>

      <div
        className={`grid grid-cols-1 gap-4 md:grid-cols-2 ${semester ? "" : "xl:grid-cols-[300px_minmax(0,1fr)_300px]"} xl:gap-5`}
      >
        {!semester && (
          <aside className="order-2 xl:order-1" aria-label="빠른 실행">
            <ActionPanel reviewCount={reviewCount} onNew={(k) => openNew(k)} />
          </aside>
        )}

        <section className="card order-1 min-w-0 p-3 md:col-span-2 md:p-4 xl:order-2 xl:col-span-1" aria-label="캘린더">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Tabs items={FILTER_ITEMS} value={filter} onChange={(f) => setFilter(f)} label="캘린더 필터" variant="line" size="sm" className="flex-1" />
            {semester && (
              <button type="button" className="btn btn-sm" onClick={() => setView("month")}>
                <PanelLeftOpen aria-hidden />
                패널 펼치기
              </button>
            )}
          </div>
          {error && events.length === 0 ? (
            <ErrorPanel message="캘린더를 불러오지 못했습니다" onRetry={refresh} />
          ) : loading ? (
            <CalendarSkeleton />
          ) : (
            <CalendarView
              events={calEvents}
              academic={calAcademic}
              view={view}
              initialDate={dateParam ? (dateParam.length === 7 ? `${dateParam}-01` : dateParam) : undefined}
              onViewChange={(v) => setView(v)}
              onDateChange={(key) => {
                const cur = toDateStr(new Date()).slice(0, key.length);
                navigateQuery({ date: key === cur ? null : key }, "replace");
              }}
              onNew={() => openNew(filter === "todo" ? "todo" : "event")}
              onSelectRange={(s, e, allDay) => {
                if (allDay) {
                  const last = addDays(e, -1);
                  openNew(filter === "todo" ? "todo" : "event", toDateStr(s), last > s ? toDateStr(last) : undefined, true);
                } else openNew(filter === "todo" ? "todo" : "event", toLocalIso(s), toLocalIso(e));
              }}
              onEventClick={(id) => navigateQuery({ event: id }, "push")}
              onLockedMove={() => toast("e클래스·학사에서 가져온 일정은 옮길 수 없습니다")}
              onEventMove={async (id, s, e, allDay, revert) => {
                try {
                  await api.updateEvent(id, {
                    start: allDay ? toDateStr(s) : toLocalIso(s),
                    end: e ? (allDay ? toDateStr(e) : toLocalIso(e)) : null,
                    all_day: allDay,
                  });
                  await refresh();
                } catch (err) {
                  revert();
                  toast(`옮기지 못했습니다: ${err instanceof Error ? err.message : String(err)}`, { tone: "error" });
                }
              }}
            />
          )}
        </section>

        {!semester && (
          <aside className="order-3 flex flex-col gap-4" aria-label="할 일">
            <TopPriority />
            <TodoPanel onNewTodo={() => openNew("todo")} />
          </aside>
        )}
      </div>

      <div className="mt-8">
        <FeatureTiles />
      </div>

      <footer className="mt-10 border-t border-border pt-5 text-[12px] text-faint">
        Univ-Us Local — 자격증명·강의자료는 이 PC 밖으로 나가지 않습니다. 단축키 <kbd className="rounded border border-border px-1">?</kbd>
      </footer>

      <EventDetailHost />
      <PlacementPreview />
      <EventForm
        open={!!draft}
        mode="create"
        draft={draft ?? { title: "", start: new Date(0), end: null, allDay: false, category: "personal", memo: "", isTodo: false, done: false }}
        categories={status?.categories ?? DEFAULT_CATEGORIES}
        onClose={() => closeQuery(["new", "start", "end", "allDay"])}
        onSave={async (input: UserEventInput) => {
          await api.createEvent(input);
          closeQuery(["new", "start", "end", "allDay"]);
          await refresh();
          toast(input.is_todo ? "할 일을 추가했습니다" : "일정을 추가했습니다", { tone: "success" });
        }}
      />
    </main>
  );
}
