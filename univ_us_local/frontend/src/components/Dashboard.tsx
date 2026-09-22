"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useState } from "react";
import ActionPanel from "./ActionPanel";
import EventDetail from "./EventDetail";
import EventModal, { type EventDraft } from "./EventModal";
import FeatureSection from "./FeatureSection";
import TodoList from "./TodoList";
import { Icon, SectionTitle } from "./ui";
import { api } from "@/lib/api";
import type { CalEvent, CategoryInfo, CategoryKey, Status, UserEventInput } from "@/lib/types";
import { addDays, fmtLongDate, fmtShortStamp, parseLocal, toDateStr, toLocalIso } from "@/lib/dates";

const CalendarView = dynamic(() => import("./CalendarView"), {
  ssr: false,
  loading: () => (
    <div className="flex h-[560px] items-center justify-center text-faint">
      <span className="spin spin-dark" />
    </div>
  ),
});

const DEFAULT_CATEGORIES: Record<CategoryKey, CategoryInfo> = {
  personal: { label: "개인", color: "#4f46e5" },
  study: { label: "학업", color: "#059669" },
  team: { label: "팀플", color: "#d97706" },
  etc: { label: "기타", color: "#64748b" },
};

type ModalState = { mode: "create"; draft: EventDraft } | { mode: "edit"; draft: EventDraft; id: string } | null;

// sync.py 종료 코드 → 토스트 문구 (코드 의미는 eclass_agent/sync.py 머리 주석)
function syncResultMessage(code: number | null): string {
  switch (code) {
    case 0:
      return "e클래스 동기화 완료";
    case 2:
      return "e클래스 세션 만료 — eclass_agent 에서 login.cmd 를 실행하세요";
    case 3:
      return "다른 동기화가 이미 진행 중이라 건너뛰었습니다";
    case null:
      return "동기화 종료 — sync.log 확인";
    default:
      return `동기화 종료 (코드 ${code}) — sync.log 확인`;
  }
}

// 참고 디자인의 캘린더 탭(일정+할일 / 일정 / 할일)에 해당
type CalFilter = "all" | "eclass" | "mine" | "todo";
const CAL_FILTERS: { key: CalFilter; label: string }[] = [
  { key: "all", label: "전체" },
  { key: "eclass", label: "e클래스" },
  { key: "mine", label: "내 일정" },
  { key: "todo", label: "할 일" },
];

export default function Dashboard() {
  const [events, setEvents] = useState<CalEvent[]>([]);
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [modal, setModal] = useState<ModalState>(null);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [calFilter, setCalFilter] = useState<CalFilter>("all");

  const categories = status?.categories ?? DEFAULT_CATEGORIES;
  const today = useMemo(() => new Date(), []);

  const refresh = useCallback(async () => {
    try {
      const [ev, st] = await Promise.all([api.events(), api.status()]);
      setEvents(ev);
      setStatus(st);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const showToast = (msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast(null), 3500);
  };

  // 동기화가 도는 동안 3초마다 상태를 본다 (끝나면 데이터를 다시 읽는다). 안 돌 때도 1분마다 봐서
  // 예약 작업(작업 스케줄러)이 시작한 동기화를 알아챈다 — 그때는 running 이 true 로 바뀌며 3초 간격이 된다.
  useEffect(() => {
    const running = !!status?.sync.running;
    const id = window.setInterval(async () => {
      try {
        const st = await api.status();
        setStatus(st);
        if (running && !st.sync.running) {
          await refresh();
          showToast(syncResultMessage(st.sync.exit_code));
        }
      } catch {
        /* 다음 틱에 재시도 */
      }
    }, running ? 3000 : 60_000);
    return () => window.clearInterval(id);
  }, [status?.sync.running, refresh]);

  // ---------- 일정 / 할 일 만들기 · 고치기 ----------
  const openCreate = (start: Date, end: Date | null, allDay: boolean, isTodo = false) =>
    setModal({
      mode: "create",
      draft: { title: "", start, end, allDay, category: isTodo ? "study" : "personal", memo: "", isTodo, done: false },
    });

  const onNewEvent = () => {
    const s = new Date();
    s.setMinutes(0, 0, 0);
    s.setHours(s.getHours() + 1);
    openCreate(s, new Date(s.getTime() + 3_600_000), false);
  };

  const onNewTodo = () => openCreate(new Date(), null, true, true);

  // 캘린더에서 날짜(범위)를 고르면. 종일 선택의 end 는 exclusive 라 하루 빼서 "마지막 날"로 넘긴다.
  const onSelectRange = (start: Date, end: Date, allDay: boolean) => {
    if (allDay) {
      const last = addDays(end, -1);
      openCreate(start, last > start ? last : null, true, calFilter === "todo");
    } else {
      openCreate(start, end, false, calFilter === "todo");
    }
  };

  const onEdit = (ev: CalEvent) => {
    if (ev.extendedProps.kind !== "user") return;
    const start = parseLocal(ev.start);
    let end: Date | null = ev.end ? parseLocal(ev.end) : null;
    if (ev.allDay && end) end = addDays(end, -1);
    setDetailId(null);
    setModal({
      mode: "edit",
      id: ev.id,
      draft: {
        title: ev.title,
        start,
        end,
        allDay: ev.allDay,
        category: ev.extendedProps.category,
        memo: ev.extendedProps.memo,
        isTodo: ev.extendedProps.isTodo,
        done: ev.extendedProps.done,
      },
    });
  };

  const onSave = async (input: UserEventInput) => {
    if (!modal) return;
    if (modal.mode === "create") await api.createEvent(input);
    else await api.updateEvent(modal.id, input);
    setModal(null);
    await refresh();
    showToast(modal.mode === "create" ? (input.is_todo ? "할 일을 추가했습니다" : "일정을 추가했습니다") : "저장했습니다");
  };

  const onDelete = async (ev: CalEvent) => {
    await api.deleteEvent(ev.id);
    setDetailId(null);
    await refresh();
    showToast("삭제했습니다");
  };

  const onToggleDone = async (ev: CalEvent, done: boolean) => {
    try {
      await api.updateEvent(ev.id, { done });
      await refresh();
    } catch (e) {
      showToast(`저장 실패: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  // 드래그로 옮기거나 늘렸을 때 — 실패하면 되돌린다.
  const onEventMove = async (id: string, start: Date, end: Date | null, allDay: boolean, revert: () => void) => {
    try {
      await api.updateEvent(id, {
        start: allDay ? toDateStr(start) : toLocalIso(start),
        end: end ? (allDay ? toDateStr(end) : toLocalIso(end)) : null,
        all_day: allDay,
      });
      await refresh();
    } catch (e) {
      revert();
      showToast(`옮기지 못했습니다: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const onSync = async () => {
    try {
      const st = await api.startSync();
      setStatus((prev) => (prev ? { ...prev, sync: st } : prev));
      if (st.error) showToast(st.error);
      else if (st.already_running)
        showToast(st.source === "external" ? "예약 동기화가 이미 진행 중입니다 — 끝나면 알려드립니다" : "이미 동기화가 진행 중입니다");
      else showToast("e클래스 동기화를 시작했습니다 (창 없이 백그라운드)");
    } catch (e) {
      showToast(`동기화 시작 실패: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const calendarEvents = useMemo(() => {
    switch (calFilter) {
      case "eclass":
        return events.filter((e) => e.extendedProps.kind === "deadline");
      case "mine":
        return events.filter((e) => e.extendedProps.kind === "user" && !e.extendedProps.isTodo);
      case "todo":
        return events.filter((e) => e.extendedProps.kind === "user" && e.extendedProps.isTodo);
      default:
        return events;
    }
  }, [events, calFilter]);

  const detail = detailId ? events.find((e) => e.id === detailId) ?? null : null;
  const syncing = !!status?.sync.running;

  return (
    <div className="min-h-screen">
      {/* 상단바 (고정) */}
      <header className="sticky top-0 z-40 flex h-16 items-center gap-4 border-b border-border bg-surface/90 px-5 backdrop-blur">
        <div className="flex items-center gap-2.5">
          <span className="grid size-8 place-items-center rounded-lg bg-accent text-[16px] font-black text-white">U</span>
          <span className="text-[16px] font-extrabold tracking-tight">유니버스</span>
          <span className="whitespace-nowrap text-[12px] font-semibold uppercase tracking-wider text-faint">Univ-Us · Local</span>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {error && (
            <span className="rounded-lg bg-danger-soft px-2.5 py-1 text-[13px] font-semibold text-danger" title={error}>
              백엔드 연결 안 됨
            </span>
          )}
          <span className="hidden whitespace-nowrap text-[13px] text-muted sm:inline">
            마지막 동기화 <b className="text-text">{fmtShortStamp(status?.updated_at)}</b>
          </span>
          <button type="button" className="btn btn-sm" onClick={onNewEvent}>
            + 일정 추가
          </button>
        </div>
      </header>

      {/* 커버 (참고: 280px 연노랑 띠 + 가운데 워드마크) */}
      <div className="cover">
        <div className="flex items-center gap-4">
          <span className="text-[56px] leading-none drop-shadow-sm">🎓</span>
          <div className="leading-tight">
            <div className="text-[44px] font-extrabold tracking-tight">
              <span className="text-[#e9a23b]">Univ-Us</span> <span className="text-[#2c2c2b]">Planner</span>{" "}
              <span className="text-[#8a8a86]">&amp;</span> <span className="text-[#e9a23b]">To Do</span>{" "}
              <span className="text-[#2c2c2b]">List</span>
            </div>
            <div className="mt-1 text-[20px] text-[#5a5955]">
              © 유니버스 <b>Univ-Us</b> · Local Dashboard
            </div>
          </div>
        </div>
      </div>

      {/* 참고 페이지 실측: 1920px 에서 좌우 여백 96px, 컬럼 간격 46px */}
      <main className="w-full px-5 pb-20 md:px-10 xl:px-16 2xl:px-24">
        <div className="-mt-9">
          <div className="grid size-[78px] place-items-center rounded-xl border border-border bg-surface text-[42px] shadow-sm">📋</div>
          <h1 className="mt-4 text-[36px] font-bold tracking-tight">유니버스 플래너</h1>
          <div className="divider mt-4" />
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1 py-3 text-[14px] text-muted">
            <span aria-hidden>⏱</span>
            <span>월간 일정과 할 일, e클래스 과제 마감을 통합 관리하는 대시보드입니다.</span>
            <span className="ml-auto font-medium text-text">{fmtLongDate(today)}</span>
          </p>
          <div className="divider mb-2" />
        </div>

        {/* 3컬럼: 참고 페이지 비율 341 : 1023 : 273 (= 20.8% : 62.5% : 16.7%), 간격 46px. 좁으면 캘린더 → 패널 순으로 쌓인다. */}
        <div className="grid grid-cols-1 gap-8 pt-4 md:grid-cols-2 xl:grid-cols-[minmax(0,341fr)_minmax(0,1023fr)_minmax(0,273fr)] xl:gap-[46px]">
          <div className="md:order-2 xl:order-1">
            <ActionPanel
              events={events}
              status={status}
              syncing={syncing}
              backendDown={!!error}
              onNewEvent={onNewEvent}
              onNewTodo={onNewTodo}
              onSync={onSync}
            />
          </div>

          <section className="min-w-0 md:order-1 md:col-span-2 xl:order-2 xl:col-span-1">
            <SectionTitle
              icon={<Icon name="calendar" />}
              action={
                <div role="tablist" className="flex gap-0.5">
                  {CAL_FILTERS.map((f) => (
                    <button
                      key={f.key}
                      type="button"
                      role="tab"
                      aria-selected={calFilter === f.key}
                      className="tab"
                      onClick={() => setCalFilter(f.key)}
                    >
                      {f.label}
                    </button>
                  ))}
                </div>
              }
            >
              Calendar
            </SectionTitle>
            <CalendarView events={calendarEvents} onSelectRange={onSelectRange} onEventClick={setDetailId} onEventMove={onEventMove} />
          </section>

          <div className="md:order-3 xl:order-3">
            <TodoList events={events} onOpenEvent={setDetailId} onToggleDone={onToggleDone} onNewTodo={onNewTodo} />
          </div>
        </div>

        <div className="divider my-10" />

        {/* 아래 전체 너비: 참고 디자인의 HABIT TRACKER 자리 → 브리핑 + 기능 */}
        <FeatureSection events={events} status={status} />

        <div className="divider my-8" />
        <footer className="text-[13px] text-faint">Univ-Us Local · 유니버스 개인 로컬 서버 웹 ver. 0.1 — 자격증명·강의자료는 이 PC 밖으로 나가지 않습니다.</footer>
      </main>

      {modal && (
        <EventModal mode={modal.mode} draft={modal.draft} categories={categories} onSave={onSave} onClose={() => setModal(null)} />
      )}
      {detail && (
        <EventDetail event={detail} onEdit={onEdit} onDelete={onDelete} onToggleDone={onToggleDone} onClose={() => setDetailId(null)} />
      )}

      {toast && (
        <div className="pointer-events-none fixed bottom-5 left-1/2 z-[60] -translate-x-1/2 rounded-xl bg-gray-900 px-4 py-2.5 text-[14px] font-semibold text-white shadow-lg">
          {toast}
        </div>
      )}
    </div>
  );
}
