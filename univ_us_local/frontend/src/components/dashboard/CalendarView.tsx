"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import FullCalendar, {
  type CalendarRef,
  type DateSelectInfo,
  type DatesSetInfo,
  type EventClickInfo,
  type EventDisplayInfo,
  type EventDropInfo,
  type EventInput,
  type EventResizeDoneInfo,
} from "@fullcalendar/react";
import dayGridPlugin from "@fullcalendar/react/daygrid";
import timeGridPlugin from "@fullcalendar/react/timegrid";
import listPlugin from "@fullcalendar/react/list";
import multiMonthPlugin from "@fullcalendar/react/multimonth";
import interactionPlugin from "@fullcalendar/react/interaction";
import breezyTheme from "@fullcalendar/react/themes/breezy";
import koLocale from "@fullcalendar/react/locales/ko";
import { ChevronLeft, ChevronRight, Keyboard, Landmark, School, Square, SquareCheck, Target } from "lucide-react";

import { Tabs } from "@/components/ui/Tabs";
import { Modal } from "@/components/ui/Modal";
import type { AcademicProps, CalEvent, ClassProps, DeadlineProps, ExamProps, UserProps } from "@/lib/types";
import { typeMeta } from "@/lib/academic";
import { ATT_LABEL } from "@/lib/attendance";
import { daysUntil, deadlineDay, parseLocal, toDateStr } from "@/lib/dates";

// C1 서비스 캘린더 — 월·주·목록·학기 뷰 (Frontend-Route 4절). FullCalendar 7 은 클래스명이 해시라
// 테마 변수(--fc-breezy-*)와 eventContent/className 훅으로만 스타일한다.

export type CalView = "month" | "week" | "list" | "semester";
const FC_VIEW: Record<CalView, string> = { month: "dayGridMonth", week: "timeGridWeek", list: "listWeek", semester: "semester" };
const VIEW_ITEMS: { key: CalView; label: string }[] = [
  { key: "month", label: "월" },
  { key: "week", label: "주" },
  { key: "list", label: "목록" },
  { key: "semester", label: "학기" },
];

type Extended = DeadlineProps | UserProps | AcademicProps | ClassProps | ExamProps;

function deadlineInput(ev: CalEvent, now: Date): EventInput {
  const p = ev.extendedProps as DeadlineProps;
  const done = p.submitted || p.userDone;
  const overdue = !done && parseLocal(p.due) < now;
  return {
    id: ev.id,
    title: ev.title,
    start: ev.start,
    end: ev.end ?? undefined,
    allDay: ev.allDay,
    editable: false,
    color: overdue ? "#dc2626" : p.courseColor,
    className: ["ev-deadline", done ? "ev-done" : ""].join(" "),
    extendedProps: p,
  };
}

function userInput(ev: CalEvent): EventInput {
  const p = ev.extendedProps as UserProps;
  return {
    id: ev.id,
    title: ev.title,
    start: ev.start,
    end: ev.end ?? undefined,
    allDay: ev.allDay,
    editable: ev.editable,
    color: p.isTodo ? "#c2410c" : p.color,
    className: [p.isTodo ? "ev-todo" : "ev-user", p.isTodo && p.done ? "ev-done" : ""].join(" "),
    extendedProps: p,
  };
}

/** 학사 일정(F1) — 원천이 만든 일정이라 옮길 수 없다(D6). 종일 일정의 end 는 이미 exclusive 로 온다. */
function academicInput(ev: CalEvent): EventInput {
  const p = ev.extendedProps as AcademicProps;
  return {
    id: ev.id,
    title: ev.title,
    start: ev.start,
    end: ev.end ?? undefined,
    allDay: ev.allDay,
    editable: false,
    color: typeMeta(p.type).color,
    className: "ev-academic",
    extendedProps: p,
  };
}

/** 시험(F5, C1 kind=exam) — 학습 블록과 구분되는 빨강 + 과녁 아이콘. 옮길 수 없다(원천은 공지·수기). */
function examInput(ev: CalEvent): EventInput {
  const p = ev.extendedProps as ExamProps;
  return {
    id: ev.id,
    title: ev.title,
    start: ev.start,
    end: ev.end ?? undefined,
    allDay: ev.allDay,
    editable: false,
    color: p.color,
    // 확인 필요·임의 일정은 점선 — 아직 확정이 아니다 (색만으로 구분하지 않게 태그도 붙인다)
    className: ["ev-exam", p.needsReview || p.isAuto ? "ev-review" : ""].join(" "),
    extendedProps: p,
  };
}

/** 수업 회차(F3, C1 kind=class) — 과목 색을 연하게 깐 배경 블록. 교시 대응표로 계산된 시각에 그려진다(8-6).
 *  결석으로 찍힌 회차는 빨강 테두리, 휴강은 흐리게+취소선. 옮길 수 없다(시간표가 원본). */
function classInput(ev: CalEvent): EventInput {
  const p = ev.extendedProps as ClassProps;
  return {
    id: ev.id,
    title: ev.title,
    start: ev.start,
    end: ev.end ?? undefined,
    allDay: false,
    editable: false,
    color: `${p.color}2e`, // FullCalendar 7 은 color · contrastColor 만 받는다 — 8자리 hex 로 연하게
    contrastColor: "#0f2724",
    className: ["ev-class", p.state === "canceled" ? "ev-done" : "", p.attendance === "absent" ? "ev-absent" : ""].join(" "),
    extendedProps: p,
  };
}

function EventContent({ info }: { info: EventDisplayInfo }) {
  const p = info.event.extendedProps as Extended;
  if (p.kind === "class") {
    const tag = p.state === "canceled" ? (p.cancelSource && p.cancelSource !== "user" ? "휴강·자동" : "휴강") : p.attendance ? ATT_LABEL[p.attendance] : p.sessionKind === "makeup" ? "보강" : "";
    return (
      <div
        className="fc-ev"
        style={{ "--ev-course": p.color } as React.CSSProperties}
        title={`수업 · ${info.event.title} ${p.periodsText}${p.room ? ` · ${p.room}` : ""}${p.sessionKind === "makeup" ? " · 보강" : ""}${
          p.state === "canceled" ? ` · 휴강${p.autoCancel ? ` (${p.autoCancel.reason ?? ""})` : ""}` : p.attendance ? ` · ${ATT_LABEL[p.attendance]}` : ""
        }`}
      >
        <School aria-hidden />
        {info.timeText && <span className="fc-ev-time">{info.timeText}</span>}
        <span className="fc-ev-title">{info.event.title}</span>
        {tag && <span className="fc-ev-tag">{tag}</span>}
      </div>
    );
  }
  if (p.kind === "deadline") {
    const d = daysUntil(deadlineDay(parseLocal(p.due)));
    const tag = p.submitted || p.userDone ? "✓" : d < 0 ? "지남" : d === 0 ? "오늘" : `D-${d}`;
    // 자정 마감은 전날 23:59~24:00 칸으로 온다(F6 to_event) — 시각은 '24:00' 으로
    const midnight = !info.event.allDay && /T00:00(:00)?$/.test(p.due) && info.event.startStr.slice(0, 10) !== p.due.slice(0, 10);
    const timeText = info.timeText && midnight ? "24:00" : info.timeText;
    return (
      <div className="fc-ev" title={`${p.courseShort} · ${info.event.title}${p.status ? ` · ${p.status}` : ""}`}>
        {timeText && <span className="fc-ev-time">{timeText}</span>}
        <span className="fc-ev-title">{info.event.title}</span>
        <span className="fc-ev-tag">{tag}</span>
      </div>
    );
  }
  if (p.kind === "exam") {
    return (
      <div
        className="fc-ev"
        title={`시험 · ${p.typeLabel} · ${info.event.title}${p.place ? ` · ${p.place}` : ""}${p.timeUnknown ? " · 시각 미정" : ""}${
          p.needsReview ? " · 확인 필요" : ""
        }${p.isAuto ? " · 임의 일정(공지가 나오면 바뀜)" : ""}`}
      >
        <Target aria-hidden />
        {info.timeText && <span className="fc-ev-time">{info.timeText}</span>}
        <span className="fc-ev-title">{info.event.title}</span>
        <span className="fc-ev-tag">{p.needsReview ? "확인" : p.isAuto ? "임의" : p.dday >= 0 ? `D-${p.dday}` : "지남"}</span>
      </div>
    );
  }
  if (p.kind === "academic") {
    return (
      <div className="fc-ev" title={`학사 · ${p.typeLabel} · ${info.event.title}${p.endTime ? ` (${p.endTime} 마감)` : ""}${p.changed ? " · 날짜 변경됨" : ""}`}>
        <Landmark aria-hidden />
        {info.timeText && <span className="fc-ev-time">{info.timeText}</span>}
        <span className="fc-ev-title">{info.event.title}</span>
        {p.changed && <span className="fc-ev-tag">변경</span>}
      </div>
    );
  }
  return (
    <div className="fc-ev" title={p.isTodo ? `할 일 · ${info.event.title}` : info.event.title}>
      {p.isTodo && (p.done ? <SquareCheck aria-label="완료" /> : <Square aria-label="할 일" />)}
      {info.timeText && <span className="fc-ev-time">{info.timeText}</span>}
      <span className="fc-ev-title">{info.event.title}</span>
    </div>
  );
}

export interface CalendarViewProps {
  events: CalEvent[];
  view: CalView;
  initialDate?: string;
  onViewChange: (v: CalView) => void;
  onDateChange: (key: string) => void;
  onSelectRange: (start: Date, end: Date, allDay: boolean) => void;
  onEventClick: (id: string) => void;
  onEventMove: (id: string, start: Date, end: Date | null, allDay: boolean, revert: () => void) => void;
  onLockedMove: () => void;
  onNew: () => void;
}

export default function CalendarView(props: CalendarViewProps) {
  const { events, view, initialDate, onViewChange, onDateChange, onSelectRange, onEventClick, onEventMove, onLockedMove, onNew } = props;
  const ref = useRef<CalendarRef>(null);
  const [title, setTitle] = useState("");
  const [help, setHelp] = useState(false);

  const inputs = useMemo(() => {
    const now = new Date();
    return events.map((e) =>
      e.extendedProps.kind === "deadline"
        ? deadlineInput(e, now)
        : e.extendedProps.kind === "academic"
          ? academicInput(e)
          : e.extendedProps.kind === "class"
            ? classInput(e)
            : e.extendedProps.kind === "exam"
              ? examInput(e)
              : userInput(e),
    );
  }, [events]);

  const api = () => ref.current?.getApi();

  // URL 의 view 가 바뀌면 캘린더도 바꾼다
  useEffect(() => {
    const a = api();
    if (a && a.view.type !== FC_VIEW[view]) a.changeView(FC_VIEW[view]);
  }, [view]);

  // 키보드 (4-7): T 오늘 · ←→ 이동 · M W L S 뷰 · N 새 일정 · ? 도움말. 입력창·모달에서는 잡지 않는다.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (t.closest("input, textarea, select, [contenteditable=true], [role=tablist]")) return;
      if (document.querySelector("[data-modal-panel]")) return;
      const k = e.key.toLowerCase();
      const map: Record<string, () => void> = {
        t: () => api()?.today(),
        arrowleft: () => api()?.prev(),
        arrowright: () => api()?.next(),
        m: () => onViewChange("month"),
        w: () => onViewChange("week"),
        l: () => onViewChange("list"),
        s: () => onViewChange("semester"),
        n: onNew,
        "?": () => setHelp(true),
      };
      const fn = map[k];
      if (fn) {
        e.preventDefault();
        fn();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onViewChange, onNew]);

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-2">
        <div className="flex items-center gap-1">
          <button type="button" className="btn btn-ghost btn-icon btn-sm" onClick={() => api()?.prev()} aria-label="이전 기간">
            <ChevronLeft aria-hidden />
          </button>
          <button type="button" className="btn btn-ghost btn-icon btn-sm" onClick={() => api()?.next()} aria-label="다음 기간">
            <ChevronRight aria-hidden />
          </button>
          <h3 className="num min-w-[112px] px-1 text-[17px] font-bold tracking-tight" aria-live="polite">
            {title}
          </h3>
          <button type="button" className="btn btn-sm ml-1" onClick={() => api()?.today()}>
            오늘
          </button>
        </div>
        <div className="ml-auto flex items-center gap-1">
          <Tabs items={VIEW_ITEMS} value={view} onChange={onViewChange} label="캘린더 보기" variant="pill" size="sm" />
          <button type="button" className="btn btn-ghost btn-icon btn-sm hidden md:inline-flex" onClick={() => setHelp(true)} aria-label="단축키 도움말">
            <Keyboard aria-hidden />
          </button>
        </div>
      </div>

      <FullCalendar
        ref={ref}
        plugins={[dayGridPlugin, timeGridPlugin, listPlugin, multiMonthPlugin, interactionPlugin, breezyTheme]}
        locale={koLocale}
        initialView={FC_VIEW[view]}
        initialDate={initialDate}
        views={{ semester: { type: "multiMonth", duration: { months: 4 }, multiMonthMaxColumns: 2 } }}
        headerToolbar={false}
        datesSet={(info: DatesSetInfo) => {
          setTitle(info.view.title);
          const cs = info.view.currentStart;
          onDateChange(info.view.type === "dayGridMonth" || info.view.type === "semester" ? toDateStr(cs).slice(0, 7) : toDateStr(cs));
        }}
        height="auto"
        aspectRatio={1.35}
        events={inputs}
        eventDisplay="block"
        eventTimeFormat={{ hour: "2-digit", minute: "2-digit", hour12: false }}
        eventContent={(info) => <EventContent info={info} />}
        dayCellTopClass="fc-top-right"
        dayCellTopContent={(info) => (
          <span className={`fc-daynum ${info.isOther ? "fc-daynum-other" : ""} ${info.isToday ? "fc-daynum-today" : ""}`}>
            {info.date.getDate() === 1 && !info.isToday ? `${info.date.getMonth() + 1}월 1일` : info.date.getDate()}
          </span>
        )}
        dayCellClass={(info) => (info.dow === 0 || info.dow === 6 ? "fc-weekend" : "")}
        dayHeaderContent={(info) => <span className="fc-dayhead">{info.text}</span>}
        dayMaxEvents={3}
        moreLinkText={(n) => `+${n}개 더`}
        noEventsText="일정이 없습니다"
        nowIndicator
        navLinks
        selectable
        selectMirror
        unselectAuto
        editable
        slotMinTime="07:00:00"
        slotMaxTime="24:00:00"
        scrollTime="08:00:00"
        slotDuration="00:30:00"
        select={(info: DateSelectInfo) => {
          onSelectRange(info.start, info.end, info.allDay);
          api()?.unselect();
        }}
        eventClick={(info: EventClickInfo) => {
          info.jsEvent.preventDefault();
          const p = info.event.extendedProps as Extended;
          onEventClick(p.kind === "academic" ? p.refId : info.event.id);
        }}
        eventDrop={(info: EventDropInfo) => {
          if (!info.event.startEditable) {
            info.revert();
            onLockedMove();
            return;
          }
          onEventMove(info.event.id, info.event.start as Date, info.event.end, info.event.allDay, info.revert);
        }}
        eventResize={(info: EventResizeDoneInfo) =>
          onEventMove(info.event.id, info.event.start as Date, info.event.end, info.event.allDay, info.revert)
        }
      />

      <Modal open={help} onClose={() => setHelp(false)} title="캘린더 단축키" size="sm">
        <dl className="grid grid-cols-[88px_1fr] gap-y-2 pt-2 text-[14px]">
          {[
            ["T", "오늘로"],
            ["← →", "이전·다음 기간"],
            ["M W L S", "월·주·목록·학기 보기"],
            ["N", "새 일정"],
            ["Esc", "창 닫기"],
            ["?", "이 도움말"],
          ].map(([k, v]) => (
            <div key={k} className="contents">
              <dt>
                <kbd className="num rounded-md border border-border bg-surface-2 px-1.5 py-0.5 text-[12px] font-bold">{k}</kbd>
              </dt>
              <dd className="text-muted">{v}</dd>
            </div>
          ))}
        </dl>
        <p className="hint mt-4">입력창에 글자를 쓰는 중에는 단축키가 동작하지 않습니다.</p>
      </Modal>
    </div>
  );
}
