"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ChevronLeft, RefreshCw, Settings, Sun } from "lucide-react";
import { Page, PageHeader, Section } from "@/components/ui/Layout";
import { Chip } from "@/components/ui/Chip";
import { EmptyState, ErrorPanel, SkeletonList } from "@/components/ui/Feedback";
import { useToast } from "@/components/ui/Toast";
import { BriefingGaps, BriefingSections, GeneratedChip } from "@/components/dashboard/BriefingCard";
import { api } from "@/lib/api";
import type { Briefing, BriefingHistory } from "@/lib/briefing";
import { useBriefingToday } from "@/lib/useBriefing";
import { useQueryValue, navigateQuery } from "@/lib/useQueryState";
import { useMediaQuery } from "@/lib/useMediaQuery";
import { parseLocal, WEEKDAY_KO } from "@/lib/dates";

// /briefing — 왼쪽 날짜 목록(보관 기간, 기본 30일) + 오른쪽 그날 스냅샷 (Frontend-Route 15-4). 폰은 목록 → 본문 2단계.
// 지난 날짜는 새로 만들지 않는다(F10-R03). '다시 만들기'는 오늘 것만.

const label = (date: string) => {
  const d = parseLocal(date);
  return `${d.getMonth() + 1}월 ${d.getDate()}일 ${WEEKDAY_KO[d.getDay()]}요일`;
};

export default function BriefingPage() {
  const toast = useToast();
  const date = useQueryValue("date");
  const wide = useMediaQuery("(min-width: 768px)");
  const today = useBriefingToday();
  const [hist, setHist] = useState<BriefingHistory | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  // 지난 날짜 스냅샷 — 받은 날짜와 함께 둔다(날짜를 바꾸면 이전 것은 저절로 안 보인다)
  const [past, setPast] = useState<{ date: string; b: Briefing | null; error: string | null } | null>(null);
  const [regenerating, setRegenerating] = useState(false);

  const todayDate = today.data?.date ?? hist?.today ?? null;
  const todayBriefing = today.data?.briefing ?? null;
  const loadHistory = useCallback(async () => {
    try {
      setHist(await api.briefings(30));
      setListError(null);
    } catch (e) {
      setListError(e instanceof Error ? e.message : String(e));
    }
  }, []);
  // 오늘 것이 새로 생기거나 바뀌면 목록도 다시 (생성 시각·놓침 칩)
  useEffect(() => {
    void Promise.resolve().then(loadHistory);
  }, [loadHistory, todayBriefing?.generatedAt]);

  // 고른 날짜 — 오늘이면 오늘 스냅샷, 아니면 그날 것을 받는다. 넓은 화면에서 안 골랐으면 맨 위(최신)
  const selected = date ?? (wide ? (todayBriefing?.date ?? hist?.items[0]?.date ?? todayDate) : null);
  const isToday = !!selected && selected === todayDate;
  useEffect(() => {
    if (!selected || isToday) return;
    let alive = true;
    api
      .briefing(selected)
      .then((b) => alive && setPast({ date: selected, b, error: null }))
      .catch((e: unknown) => alive && setPast({ date: selected, b: null, error: e instanceof Error ? e.message : String(e) }));
    return () => {
      alive = false;
    };
  }, [selected, isToday]);

  const shownPast = past && past.date === selected ? past : null;
  const pastError = shownPast?.error ?? null;
  const current = isToday ? todayBriefing : (shownPast?.b ?? null);
  const select = (d: string) => navigateQuery({ date: d === todayDate ? null : d }, wide ? "replace" : "push");

  const regenerate = async () => {
    setRegenerating(true);
    try {
      await today.regenerate();
      if (!isToday && todayDate) select(todayDate);
      toast("지금 기준으로 다시 만들었습니다", { tone: "success" });
    } catch (e) {
      toast(`만들지 못했습니다: ${e instanceof Error ? e.message : String(e)}`, { tone: "error" });
    } finally {
      setRegenerating(false);
    }
  };

  // 목록 = 서버 보관분. 오늘 것이 아직 없으면(예정 시각 전·꺼짐·수집 대기) 맨 위에 '오늘' 자리를 둔다
  const rows = hist?.items ?? [];
  const showTodaySlot = !!todayDate && !rows.some((r) => r.date === todayDate);

  return (
    <Page>
      <PageHeader
        icon={<Sun />}
        title="브리핑"
        subtitle={`매일 ${today.data?.scheduledFor ?? "08:00"} 에 만들어지는 오늘의 요약 — 지난 ${hist?.keepDays ?? 30}일 보관`}
        actions={
          <>
            <Link href="/settings/notifications" className="btn btn-ghost btn-sm">
              <Settings aria-hidden />
              설정
            </Link>
            <button type="button" className="btn btn-sm" disabled={regenerating || !today.data} onClick={() => void regenerate()}>
              <RefreshCw className={regenerating ? "animate-spin" : ""} aria-hidden />
              {todayBriefing ? "다시 만들기" : "지금 만들기"}
            </button>
          </>
        }
      />
      <div className="grid gap-5 md:grid-cols-[240px_minmax(0,1fr)]">
        {(wide || !selected) && (
          <nav aria-label="브리핑 날짜" className="card h-fit p-2">
            {listError && !hist ? (
              <ErrorPanel message="지난 브리핑을 불러오지 못했습니다" onRetry={() => void loadHistory()} />
            ) : !hist ? (
              <SkeletonList rows={4} />
            ) : (
              <ul>
                {showTodaySlot && (
                  <li>
                    <button
                      type="button"
                      aria-current={selected === todayDate ? "date" : undefined}
                      onClick={() => select(todayDate!)}
                      className={`flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-left text-[14px] transition-colors ${
                        selected === todayDate ? "bg-primary-soft font-semibold text-primary" : "hover:bg-surface-2"
                      }`}
                    >
                      <span className="flex-1">오늘</span>
                      <span className="text-[12px] text-faint">{today.data?.state === "pending" ? "만드는 중" : "아직 없음"}</span>
                    </button>
                  </li>
                )}
                {rows.map((b) => {
                  const on = b.date === selected;
                  return (
                    <li key={b.date}>
                      <button
                        type="button"
                        aria-current={on ? "date" : undefined}
                        onClick={() => select(b.date)}
                        className={`flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-left text-[14px] transition-colors ${
                          on ? "bg-primary-soft font-semibold text-primary" : "hover:bg-surface-2"
                        }`}
                      >
                        <span className="min-w-0 flex-1">
                          <span className="block">{b.date === todayDate ? "오늘" : label(b.date)}</span>
                          <span className="block truncate text-[12px] font-normal text-faint">{b.summary}</span>
                        </span>
                        {b.missed && <Chip tone="warn">놓침</Chip>}
                      </button>
                    </li>
                  );
                })}
                {rows.length === 0 && !showTodaySlot && <li className="px-3 py-2.5 text-[13px] text-faint">아직 만든 브리핑이 없습니다</li>}
              </ul>
            )}
          </nav>
        )}
        {selected && (
          <Section title={isToday ? `오늘 · ${label(selected)}` : label(selected)} action={current && <GeneratedChip b={current} />}>
            {!wide && (
              <button type="button" className="btn btn-ghost btn-sm mb-3" onClick={() => history.back()}>
                <ChevronLeft aria-hidden />
                날짜 목록
              </button>
            )}
            {current ? (
              <>
                {current.headline && <p className="mb-4 text-[16px] font-semibold">{current.headline}</p>}
                <BriefingSections b={current} compact />
                <BriefingGaps b={current} />
                <p className="hint mt-5">스냅샷입니다 — 이후 일정이 바뀌어도 이 내용은 그대로입니다.</p>
              </>
            ) : isToday ? (
              today.error && !today.data ? (
                <ErrorPanel message="브리핑을 불러오지 못했습니다" onRetry={() => void today.reload()} />
              ) : (
                <EmptyState
                  compact
                  icon={<Sun />}
                  title={
                    today.data?.state === "off"
                      ? "브리핑이 꺼져 있습니다"
                      : today.data?.state === "pending"
                        ? "수집이 끝나면 오늘 브리핑을 만듭니다"
                        : `오늘 브리핑은 ${today.data?.scheduledFor ?? "08:00"} 에 만들어집니다`
                  }
                  action={
                    <button type="button" className="btn btn-sm" disabled={regenerating || !today.data} onClick={() => void regenerate()}>
                      <RefreshCw aria-hidden />
                      지금 만들기
                    </button>
                  }
                >
                  {today.data?.state === "pending" ? `${today.data.waitingFor.join(" · ")} 수집 중 — 최대 5분 기다립니다` : "지금 기준으로 바로 만들 수도 있습니다."}
                </EmptyState>
              )
            ) : pastError ? (
              <ErrorPanel message={pastError} />
            ) : (
              <SkeletonList rows={3} />
            )}
          </Section>
        )}
      </div>
    </Page>
  );
}
