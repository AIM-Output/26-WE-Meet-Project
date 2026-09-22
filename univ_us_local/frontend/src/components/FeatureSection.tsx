"use client";

import { useMemo } from "react";
import { Icon, SectionTitle } from "./ui";
import type { CalEvent, DeadlineProps, Status } from "@/lib/types";
import { addDays, daysUntil, isSameDay, parseLocal, startOfDay } from "@/lib/dates";

interface Props {
  events: CalEvent[];
  status: Status | null;
}

/** 아래 전체 너비 — 참고 디자인의 H A B I T   T R A C K E R 자리. 아침 브리핑(F10)과 나중에 붙일 기능 타일. */
const FEATURES = [
  { id: "F7", name: "과제 우선순위", desc: "마감·비중·소요시간으로 순서 매기기", icon: "🎯" },
  { id: "F9", name: "자연어 일정·질의", desc: "\"이번 주 마감 뭐 남았어?\"", icon: "💬" },
  { id: "F4", name: "강의자료 요약", desc: "PDF 요약·예상 문제 (RAG)", icon: "📚" },
  { id: "F11", name: "장학 공지 매칭", desc: "내 프로필에 맞는 장학만 알림", icon: "🎓" },
  { id: "F2", name: "졸업요건 트래커", desc: "남은 전공·교양 학점 계산", icon: "🧭" },
  { id: "F8", name: "공강 학습 플랜", desc: "빈 시간에 학습 블록 배치", icon: "🗓️" },
  { id: "F5", name: "시험 공부 일정", desc: "시험일 역산 계획", icon: "📖" },
  { id: "F16", name: "팀플 일정 조율", desc: "팀원 공강 교집합 (서버 필요)", icon: "🤝" },
];

function eventOnDay(ev: CalEvent, day: Date): boolean {
  const s = parseLocal(ev.start);
  if (ev.allDay) {
    const endEx = ev.end ? parseLocal(ev.end) : addDays(startOfDay(s), 1);
    return startOfDay(s) <= day && day < endEx;
  }
  return isSameDay(s, day);
}

export default function FeatureSection({ events, status }: Props) {
  const today = useMemo(() => startOfDay(new Date()), []);
  const todayCount = useMemo(() => events.filter((e) => eventOnDay(e, today)).length, [events, today]);
  const soon = useMemo(
    () =>
      events.filter((e) => {
        if (e.extendedProps.kind !== "deadline") return false;
        const p = e.extendedProps as DeadlineProps;
        const d = daysUntil(parseLocal(p.due));
        return !p.submitted && d >= 0 && d <= 3;
      }).length,
    [events],
  );
  const overdue = useMemo(
    () =>
      events.filter((e) => {
        if (e.extendedProps.kind !== "deadline") return false;
        const p = e.extendedProps as DeadlineProps;
        return !p.submitted && daysUntil(parseLocal(p.due)) < 0;
      }).length,
    [events],
  );

  return (
    <section className="callout">
      <SectionTitle icon={<Icon name="grid" />} action={<span className="text-[12px] text-faint">참고 페이지의 HABIT TRACKER 자리 — 기능을 하나씩 채웁니다</span>}>
        Features
      </SectionTitle>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        {/* 아침 브리핑 자리 */}
        <div className="rounded-lg border border-border bg-surface p-5">
          <div className="flex items-center justify-between">
            <h3 className="text-[15px] font-bold">🌅 아침 브리핑</h3>
            <span className="text-[12px] font-semibold text-faint">F10 · 준비 중</span>
          </div>
          <div className="mt-4 grid grid-cols-3 gap-3">
            <Stat label="오늘 일정" value={todayCount} />
            <Stat label="D-3 이내 마감" value={soon} tone={soon > 0 ? "warn" : undefined} />
            <Stat label="지난 미제출" value={overdue} tone={overdue > 0 ? "danger" : undefined} />
          </div>
          <p className="mt-4 text-[13px] leading-relaxed text-muted">
            매일 아침 정해진 시각에 오늘의 강의·할 일·마감 임박 항목을 요약해 여기와 알림으로 보냅니다. 스케줄러는 백엔드에 내장할 예정.
          </p>
        </div>

        {/* 기능 타일 */}
        <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
          {FEATURES.map((f) => (
            <div key={f.id} aria-disabled className="rounded-lg border border-dashed border-border bg-surface px-4 py-4 text-muted">
              <div className="flex items-center gap-2">
                <span className="text-lg leading-none">{f.icon}</span>
                <span className="truncate text-[14px] font-bold text-gray-600">{f.name}</span>
              </div>
              <p className="mt-1 line-clamp-2 text-[12px] leading-snug text-faint">{f.desc}</p>
              <p className="mt-2 text-[11px] font-bold text-faint">{f.id} · 준비 중</p>
            </div>
          ))}
        </div>
      </div>

      {status && (
        <p className="mt-5 text-[12px] text-faint">
          과목 {status.counts.courses}개 · e클래스 마감 {status.counts.deadlines}건 · 내 일정 {status.counts.userEvents}건 · 자료 위치 {status.eclassDataDir}
        </p>
      )}
    </section>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone?: "danger" | "warn" }) {
  const color = tone === "danger" ? "text-danger" : tone === "warn" ? "text-warn" : "";
  return (
    <div className="rounded-lg bg-[#f7f7f5] px-3 py-3">
      <div className={`text-2xl font-extrabold tabular-nums ${color}`}>{value}</div>
      <div className="text-[12px] font-semibold text-muted">{label}</div>
    </div>
  );
}
