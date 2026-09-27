"use client";

import { useState } from "react";
import { X } from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { WeekGrid } from "@/components/ui/WeekGrid";
import { Banner, DemoNotice } from "@/components/ui/Feedback";
import { useToast } from "@/components/ui/Toast";
import { closeQuery, useQueryValue } from "@/lib/useQueryState";

// F8 공강 배치 미리보기 — `/?place=preview` 전체 화면 모달(Frontend-Route 13-3).
// 수업 = 회색, 기존 일정 = 옅게, 새 블록 = 연두. 색만으로 구분하지 않게 블록에 이름을 쓴다. 배치하기 전엔 캘린더가 바뀌지 않는다.

const DAYS = ["월", "화", "수", "목", "금", "토", "일"] as const;
const HOURS = [9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22] as const;

type Cell = { kind: "class" | "event" | "block"; label: string; id?: string; why?: string };

const BASE: Record<string, Cell> = {
  "0-13": { kind: "class", label: "수업" },
  "0-14": { kind: "class", label: "수업" },
  "1-11": { kind: "class", label: "수업" },
  "1-12": { kind: "class", label: "수업" },
  "2-9": { kind: "class", label: "수업" },
  "2-10": { kind: "class", label: "수업" },
  "2-13": { kind: "class", label: "수업" },
  "3-15": { kind: "event", label: "내 일정" },
  "4-18": { kind: "event", label: "스터디" },
};

const BLOCKS: (Cell & { key: string; hours: number })[] = [
  { key: "0-19", kind: "block", id: "b1", label: "품질 보고서", why: "소프트웨어공학론 · 9/28 마감 · 저녁 60분", hours: 1 },
  { key: "0-20", kind: "block", id: "b2", label: "운영체제 15쪽", why: "운영체제 3주차 · 중간고사 계획분 · 60분", hours: 1 },
  { key: "1-10", kind: "block", id: "b3", label: "3주차 실습", why: "운영체제 · 내일 23:59 · 공강 60분", hours: 1 },
  { key: "1-19", kind: "block", id: "b4", label: "3주차 실습", why: "운영체제 · 이어서 60분", hours: 1 },
  { key: "2-11", kind: "block", id: "b5", label: "퀴즈 2회", why: "컴퓨터네트워크 · 30분", hours: 0.5 },
  { key: "3-19", kind: "block", id: "b6", label: "팀 보고서", why: "캡스톤 · 9/30 마감 · 저녁 120분", hours: 2 },
  { key: "3-20", kind: "block", id: "b7", label: "팀 보고서", why: "캡스톤 · 이어서", hours: 0 },
];

export default function PlacementPreview() {
  const open = useQueryValue("place") === "preview";
  const toast = useToast();
  const [removed, setRemoved] = useState<string[]>([]);
  const close = () => closeQuery(["place", "range"]);

  const blocks = BLOCKS.filter((b) => !removed.includes(b.id!));
  const cells: Record<string, Cell> = { ...BASE, ...Object.fromEntries(blocks.map((b) => [b.key, b])) };
  const perDay = DAYS.map((_, d) => blocks.filter((b) => b.key.startsWith(`${d}-`)).reduce((s, b) => s + b.hours, 0));

  return (
    <Modal
      open={open}
      onClose={close}
      size="xl"
      title="공강에 배치하기"
      footer={
        <>
          <button type="button" className="btn" onClick={() => setRemoved([])}>
            다시 계산
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => {
              close();
              toast(`${blocks.length}개 블록을 캘린더에 넣었습니다 (예시 — 배치 API 연결 전)`, { tone: "success" });
            }}
          >
            배치하기
          </button>
        </>
      }
    >
      <div className="space-y-4 pt-1">
        <DemoNotice what="공강 배치" />
        <div className="flex flex-wrap gap-3 text-[12px] text-muted">
          <Legend cls="bg-surface-3 border-border" label="수업" />
          <Legend cls="bg-primary-soft border-primary-soft-2" label="기존 일정" />
          <Legend cls="bg-study-soft border-study" label="새로 배치될 블록" />
        </div>
        <WeekGrid
          caption="이번 주 배치 미리보기"
          days={DAYS}
          hours={HOURS}
          cellHeight={30}
          renderCell={(d, h) => {
            const c = cells[`${d}-${h}`];
            if (!c) return <div className="h-full rounded-md bg-surface-2" />;
            if (c.kind === "block")
              return (
                <div className="group relative flex h-full items-center gap-1 rounded-md border border-study bg-study-soft px-1.5 text-[11px] font-semibold text-study" title={c.why}>
                  <span className="min-w-0 flex-1 truncate">{c.label}</span>
                  <button
                    type="button"
                    className="grid size-4 flex-none place-items-center rounded opacity-60 hover:bg-study hover:text-white hover:opacity-100"
                    aria-label={`${c.label} 빼기`}
                    onClick={() => setRemoved((r) => [...r, c.id!])}
                  >
                    <X className="size-3" aria-hidden />
                  </button>
                </div>
              );
            return (
              <div className={`flex h-full items-center truncate rounded-md border px-1.5 text-[11px] ${c.kind === "class" ? "border-border bg-surface-3 text-faint" : "border-primary-soft-2 bg-primary-soft text-primary"}`}>
                {c.label}
              </div>
            );
          }}
        />
        <div className="flex flex-wrap gap-2 text-[13px]">
          <span className="font-semibold text-muted">하루 합계</span>
          {DAYS.map((d, i) => (
            <span key={d} className={`num rounded-md px-2 py-0.5 ${perDay[i] >= 4 ? "bg-warn-soft font-bold text-warn-text" : "bg-surface-3 text-muted"}`}>
              {d} {perDay[i]}h{perDay[i] >= 4 ? "(상한)" : ""}
            </span>
          ))}
        </div>
        <Banner
          tone="warn"
          action={
            <>
              <button type="button" className="btn btn-sm">하루 상한 올리기</button>
              <button type="button" className="btn btn-sm">저녁 시간 늘리기</button>
              <button type="button" className="btn btn-sm">주말 켜기</button>
            </>
          }
        >
          <b>배치하지 못함 1건</b> — 팀 프로젝트 보고서 30시간 중 22시간: 마감까지 빈 시간이 부족합니다
        </Banner>
      </div>
    </Modal>
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
