"use client";

import { useMemo, useState } from "react";
import { ChevronLeft, RefreshCw, Sun } from "lucide-react";
import { Page, PageHeader, Section } from "@/components/ui/Layout";
import { Chip } from "@/components/ui/Chip";
import { DemoNotice } from "@/components/ui/Feedback";
import { useAppData } from "@/components/app/AppData";
import { BriefingSections } from "@/components/dashboard/BriefingCard";
import { useQueryValue, navigateQuery } from "@/lib/useQueryState";
import { useMediaQuery } from "@/lib/useMediaQuery";
import { composeBriefing, demoPastBriefings, type Briefing } from "@/lib/demo";
import { parseLocal, WEEKDAY_KO } from "@/lib/dates";

// /briefing — 왼쪽 날짜 목록(최근 30일) + 오른쪽 그날 스냅샷(15-4). 폰은 목록 → 본문 2단계.

const label = (b: Briefing) => {
  const d = parseLocal(b.date);
  return `${d.getMonth() + 1}월 ${d.getDate()}일 ${WEEKDAY_KO[d.getDay()]}요일`;
};

export default function BriefingPage() {
  const { events, status } = useAppData();
  const date = useQueryValue("date");
  const wide = useMediaQuery("(min-width: 768px)");
  const [regenerating, setRegenerating] = useState(false);
  const today = useMemo(() => composeBriefing(events, status?.priority?.top), [events, status?.priority?.top]);
  const all = useMemo(() => [today, ...demoPastBriefings.filter((b) => b.date !== today.date)], [today]);
  const current = all.find((b) => b.date === date) ?? (wide ? all[0] : null);
  const select = (d: string) => navigateQuery({ date: d === today.date ? null : d }, wide ? "replace" : "push");

  return (
    <Page>
      <PageHeader
        icon={<Sun />}
        title="브리핑"
        subtitle="매일 08:00 에 만들어지는 오늘의 요약 — 지난 30일 보관"
        actions={
          current?.date === today.date && (
            <button
              type="button"
              className="btn btn-sm"
              disabled={regenerating}
              onClick={() => {
                setRegenerating(true);
                window.setTimeout(() => setRegenerating(false), 700);
              }}
            >
              <RefreshCw className={regenerating ? "animate-spin" : ""} aria-hidden />
              다시 만들기
            </button>
          )
        }
      />
      <div className="mb-5">
        <DemoNotice what="지난 브리핑 목록" />
      </div>
      <div className="grid gap-5 md:grid-cols-[240px_minmax(0,1fr)]">
        {(wide || !current) && (
          <nav aria-label="브리핑 날짜" className="card h-fit p-2">
            <ul>
              {all.map((b) => {
                const on = b.date === current?.date;
                return (
                  <li key={b.date}>
                    <button
                      type="button"
                      aria-current={on ? "date" : undefined}
                      onClick={() => select(b.date)}
                      className={`flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-left text-[14px] transition-colors ${on ? "bg-primary-soft font-semibold text-primary" : "hover:bg-surface-2"}`}
                    >
                      <span className="flex-1">{b.date === today.date ? "오늘" : label(b)}</span>
                      {b.source === "catchup" && <Chip tone="warn">놓침</Chip>}
                    </button>
                  </li>
                );
              })}
            </ul>
          </nav>
        )}
        {current && (
          <Section
            title={label(current)}
            action={
              current.live ? (
                <span className="text-[12px] text-faint">임시 조립 · 서버 생성 전</span>
              ) : (
                <span className="num text-[12px] text-faint">
                  {current.source === "catchup" ? `놓친 브리핑 · 08:00 예정 → ${current.generatedAt} 생성` : `${current.generatedAt} 생성`}
                </span>
              )
            }
          >
            {!wide && (
              <button type="button" className="btn btn-ghost btn-sm mb-3" onClick={() => history.back()}>
                <ChevronLeft aria-hidden />
                날짜 목록
              </button>
            )}
            {current.headline && <p className="mb-4 text-[16px] font-semibold">{current.headline}</p>}
            <BriefingSections b={current} compact />
            <p className="hint mt-5">스냅샷입니다 — 이후 일정이 바뀌어도 이 내용은 그대로입니다.</p>
          </Section>
        )}
      </div>
    </Page>
  );
}
