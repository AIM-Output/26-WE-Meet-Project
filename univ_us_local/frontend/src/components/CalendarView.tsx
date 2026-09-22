"use client";

import { useMemo, useRef, useState } from "react";
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
import interactionPlugin from "@fullcalendar/react/interaction";
import breezyTheme from "@fullcalendar/react/themes/breezy";
import koLocale from "@fullcalendar/react/locales/ko";

import type { CalEvent, DeadlineProps, UserProps } from "@/lib/types";
import { daysUntil, parseLocal } from "@/lib/dates";

export interface CalendarViewProps {
  events: CalEvent[];
  onSelectRange: (start: Date, end: Date, allDay: boolean) => void;
  onEventClick: (id: string) => void;
  onEventMove: (id: string, start: Date, end: Date | null, allDay: boolean, revert: () => void) => void;
}

const DANGER = "#dc2626";
const TODO = "#ea580c";

const VIEWS = [
  { key: "dayGridMonth", label: "월" },
  { key: "timeGridWeek", label: "주" },
  { key: "listWeek", label: "목록" },
];

/** 백엔드 이벤트 → FullCalendar 입력. 마감은 과목 색, 사용자 일정은 분류 색, 할 일은 주황. 미제출·지난 마감은 빨강. */
function toInput(ev: CalEvent, now: Date): EventInput {
  const p = ev.extendedProps;
  let color = p.kind === "deadline" ? p.courseColor : p.color;
  const classNames: string[] = [];
  if (p.kind === "deadline") {
    classNames.push("ev-deadline");
    if (p.submitted) classNames.push("ev-done");
    else if (parseLocal(p.due) < now) {
      classNames.push("ev-overdue");
      color = DANGER;
    }
  } else {
    classNames.push("ev-user");
    if (p.isTodo) {
      classNames.push("ev-todo");
      color = TODO;
      if (p.done) classNames.push("ev-done");
    }
  }
  return {
    id: ev.id,
    title: ev.title,
    start: ev.start,
    end: ev.end ?? undefined,
    allDay: ev.allDay,
    editable: ev.editable,
    color,
    className: classNames.join(" "),
    extendedProps: p,
  };
}

function EventContent({ info }: { info: EventDisplayInfo }) {
  const p = info.event.extendedProps as DeadlineProps | UserProps;
  if (p.kind === "deadline") {
    const d = daysUntil(parseLocal(p.due));
    const tag = p.submitted ? "✓" : d < 0 ? "지남" : d === 0 ? "오늘" : `D-${d}`;
    return (
      <div className="fc-ev" title={`${p.courseShort} · ${info.event.title}${p.status ? ` · ${p.status}` : ""}`}>
        {info.timeText && <span className="fc-ev-time">{info.timeText}</span>}
        <span className="fc-ev-title">{info.event.title}</span>
        <span className="fc-ev-tag">{tag}</span>
      </div>
    );
  }
  return (
    <div className="fc-ev" title={p.isTodo ? `할 일 · ${info.event.title}` : info.event.title}>
      {p.isTodo && <span className="fc-ev-box">{p.done ? "☑" : "☐"}</span>}
      {info.timeText && <span className="fc-ev-time">{info.timeText}</span>}
      <span className="fc-ev-title">{info.event.title}</span>
    </div>
  );
}

export default function CalendarView({ events, onSelectRange, onEventClick, onEventMove }: CalendarViewProps) {
  const ref = useRef<CalendarRef>(null);
  const [title, setTitle] = useState("");
  const [view, setView] = useState("dayGridMonth");
  const inputs = useMemo(() => {
    const now = new Date();
    return events.map((e) => toInput(e, now));
  }, [events]);

  const api = () => ref.current?.getApi();

  return (
    <div>
      {/* 참고 페이지의 달력 머리: "2026년 9월" 왼쪽, "‹ 오늘 ›" 오른쪽 (+ 뷰 전환) */}
      <div className="cal-toolbar">
        <span className="cal-title">{title}</span>
        <div className="flex items-center gap-3">
          <div role="tablist" className="flex gap-0.5">
            {VIEWS.map((v) => (
              <button
                key={v.key}
                type="button"
                role="tab"
                aria-selected={view === v.key}
                className="tab"
                onClick={() => {
                  api()?.changeView(v.key);
                  setView(v.key);
                }}
              >
                {v.label}
              </button>
            ))}
          </div>
          <div className="cal-nav">
            <button type="button" onClick={() => api()?.prev()} aria-label="이전">
              ‹
            </button>
            <button type="button" onClick={() => api()?.today()}>
              오늘
            </button>
            <button type="button" onClick={() => api()?.next()} aria-label="다음">
              ›
            </button>
          </div>
        </div>
      </div>

      <FullCalendar
        ref={ref}
        plugins={[dayGridPlugin, timeGridPlugin, listPlugin, interactionPlugin, breezyTheme]}
        locale={koLocale}
        initialView="dayGridMonth"
        headerToolbar={false}
        datesSet={(info: DatesSetInfo) => setTitle(info.view.title)}
        // 참고 페이지 실측: 1023px 폭에 칸 146×140 → 요일 헤더 포함 가로/세로 ≈ 1.15
        height="auto"
        aspectRatio={1.21}
        events={inputs}
        eventDisplay="block"
        eventTimeFormat={{ hour: "2-digit", minute: "2-digit", hour12: false }}
        eventContent={(info) => <EventContent info={info} />}
        // 테마 글자 크기는 해시 클래스에 고정 → 날짜 숫자(오른쪽 위)·요일은 우리가 그린다
        dayCellTopClass="fc-top-right"
        dayCellTopContent={(info) => (
          <span className={`fc-daynum ${info.isOther ? "fc-daynum-other" : ""}`}>
            {info.date.getDate() === 1 ? `${info.date.getMonth() + 1}월 1일` : info.dayNumberText}
          </span>
        )}
        dayCellClass={(info) => (info.dow === 0 || info.dow === 6 ? "fc-weekend" : "")}
        dayHeaderContent={(info) => <span className="fc-dayhead">{info.text}</span>}
        dayMaxEvents={4}
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
          onEventClick(info.event.id);
        }}
        eventDrop={(info: EventDropInfo) =>
          onEventMove(info.event.id, info.event.start as Date, info.event.end, info.event.allDay, info.revert)
        }
        eventResize={(info: EventResizeDoneInfo) =>
          onEventMove(info.event.id, info.event.start as Date, info.event.end, info.event.allDay, info.revert)
        }
      />
    </div>
  );
}
