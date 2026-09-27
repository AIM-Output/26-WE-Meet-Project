"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowRight, CalendarPlus, ListTodo, Maximize2, RefreshCw, Send, Sparkles, TriangleAlert } from "lucide-react";
import { useAppData } from "@/components/app/AppData";
import { useToast } from "@/components/ui/Toast";
import { fmtRelative } from "@/lib/dates";
import { CHAT_EXAMPLES } from "@/lib/demo";
import { navigateQuery } from "@/lib/useQueryState";

// 왼쪽 컬럼 — 일정·할 일 등록 / 빠른 실행(원천별 동기화) / 확인 필요 / 대화 카드 (Frontend-Route 6-2 · 11-5 · 14-3).

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="card p-4">
      <h2 className="mb-3 text-[13px] font-bold tracking-wide text-muted">{title}</h2>
      {children}
    </section>
  );
}

function SyncRow({
  label,
  busy,
  busyText,
  meta,
  error,
  onClick,
  disabled,
  demo,
}: {
  label: string;
  busy: boolean;
  busyText: string;
  meta: string;
  error?: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  demo?: boolean;
}) {
  return (
    <div>
      <button
        type="button"
        onClick={onClick}
        disabled={busy || disabled}
        className="group flex w-full items-center gap-3 rounded-lg border border-border px-3 py-2.5 text-left transition-colors hover:border-border-strong hover:bg-surface-2 disabled:cursor-not-allowed"
      >
        <RefreshCw className={`size-4 flex-none ${busy ? "animate-spin text-primary" : "text-faint group-hover:text-primary"}`} aria-hidden />
        <span className="min-w-0 flex-1">
          <span className="block text-[14px] font-semibold">{busy ? busyText : label}</span>
          <span className="block truncate text-[12px] text-faint">
            {meta}
            {demo && " · 예시"}
          </span>
        </span>
      </button>
      {error && <p className="mt-1.5 flex items-start gap-1.5 px-1 text-[12px] font-medium text-danger-text">{error}</p>}
    </div>
  );
}

export default function ActionPanel({ reviewCount, onNew }: { reviewCount: number; onNew: (kind: "event" | "todo") => void }) {
  const { status, syncing, error, startSync } = useAppData();
  const toast = useToast();
  const [academicBusy, setAcademicBusy] = useState(false);
  const failed = status && !syncing && status.sync.exit_code !== null && status.sync.exit_code !== 0 && status.sync.exit_code !== 3;

  return (
    <div className="flex flex-col gap-4">
      <Block title="등록">
        <div className="grid grid-cols-2 gap-2">
          <button type="button" className="btn btn-sm justify-start" onClick={() => onNew("event")}>
            <CalendarPlus aria-hidden />새 일정
          </button>
          <button type="button" className="btn btn-sm justify-start" onClick={() => onNew("todo")}>
            <ListTodo aria-hidden />새 할 일
          </button>
        </div>
      </Block>

      <Block title="빠른 실행">
        <div className="space-y-2">
          <SyncRow
            label="e클래스 동기화"
            busy={syncing}
            busyText={status?.sync.source === "external" ? "예약 동기화 진행 중…" : "동기화 중…"}
            meta={status ? `${fmtRelative(status.updated_at)} · 과제 ${status.counts.deadlines}건` : "상태 확인 중"}
            disabled={!!error}
            onClick={startSync}
            error={
              failed ? (
                <>
                  <TriangleAlert className="mt-px size-3.5 flex-none" aria-hidden />
                  <span>
                    {status?.sync.exit_code === 2 ? "로그인이 필요합니다" : "마지막 동기화가 실패했습니다"} ·{" "}
                    <Link href="/settings/sources" className="underline">
                      수집 원천
                    </Link>
                  </span>
                </>
              ) : undefined
            }
          />
          <SyncRow
            label="학사일정 동기화"
            busy={academicBusy}
            busyText="학사일정 수집 중…"
            meta="오늘 06:00 · 24건"
            demo
            onClick={() => {
              setAcademicBusy(true);
              window.setTimeout(() => {
                setAcademicBusy(false);
                toast("학사일정 수집 API 가 아직 없습니다 — 예시 데이터를 보여 줍니다");
              }, 900);
            }}
          />
          <button
            type="button"
            className="flex w-full items-center gap-3 rounded-lg border border-border px-3 py-2.5 text-left transition-colors hover:border-border-strong hover:bg-surface-2"
            onClick={() => navigateQuery({ place: "preview" }, "push")}
          >
            <Sparkles className="size-4 flex-none text-study" aria-hidden />
            <span className="min-w-0 flex-1">
              <span className="block text-[14px] font-semibold">공강에 배치하기</span>
              <span className="block text-[12px] text-faint">과제·공부를 빈 시간에 · 미리보기 후 등록</span>
            </span>
          </button>
        </div>
      </Block>

      {reviewCount > 0 && (
        <Link
          href="/academic?tab=review"
          className="card flex items-center gap-3 border-[#f5dca6] bg-warn-soft p-4 transition-colors hover:border-warn"
        >
          <TriangleAlert className="size-5 flex-none text-warn-text" aria-hidden />
          <span className="min-w-0 flex-1">
            <span className="block text-[14px] font-bold text-warn-text">확인 필요 {reviewCount}건</span>
            <span className="block text-[12px] text-warn-text/80">공지에서 찾은 학사일정 — 등록 전 확인</span>
          </span>
          <ArrowRight className="size-4 flex-none text-warn-text" aria-hidden />
        </Link>
      )}

      <ChatCard />
    </div>
  );
}

/** F9 대화 카드 — 모달이 아니라 대시보드에 늘 떠 있다(14-3). 분석 서비스 연결 전이라 입력은 /chat 으로 넘긴다. */
function ChatCard() {
  const router = useRouter();
  const [text, setText] = useState("");
  const go = (q: string) => router.push(`/chat${q ? `?q=${encodeURIComponent(q)}` : ""}`);
  return (
    <section className="card p-4">
      <div className="mb-3 flex items-center gap-2">
        <h2 className="text-[13px] font-bold tracking-wide text-muted">무엇이든 물어보세요</h2>
        <Link href="/chat" className="btn btn-ghost btn-icon btn-sm ml-auto" aria-label="대화 전체 화면">
          <Maximize2 aria-hidden />
        </Link>
      </div>
      <div className="mb-3 flex flex-wrap gap-1.5">
        {CHAT_EXAMPLES.map((q) => (
          <button key={q} type="button" className="rounded-full bg-surface-3 px-2.5 py-1 text-[12px] font-medium text-muted transition-colors hover:bg-primary-soft hover:text-primary" onClick={() => go(q)}>
            {q}
          </button>
        ))}
      </div>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (text.trim()) go(text.trim());
        }}
      >
        <label htmlFor="chat-quick" className="sr-only">
          질문 또는 일정
        </label>
        <input id="chat-quick" className="field field-sm h-9 flex-1" placeholder="다음 주 목요일 발표 리허설 저녁 8시" value={text} onChange={(e) => setText(e.target.value)} />
        <button type="submit" className="btn btn-primary btn-icon btn-sm size-9" aria-label="보내기" disabled={!text.trim()}>
          <Send aria-hidden />
        </button>
      </form>
    </section>
  );
}
