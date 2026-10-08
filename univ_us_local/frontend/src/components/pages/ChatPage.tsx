"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ArrowRight, CalendarCheck, MessageCircle, Send, Trash2, TriangleAlert } from "lucide-react";
import { Page, PageHeader } from "@/components/ui/Layout";
import { Banner, DemoNotice } from "@/components/ui/Feedback";
import { Chip } from "@/components/ui/Chip";
import { useToast } from "@/components/ui/Toast";
import { useQueryValue } from "@/lib/useQueryState";
import { CHAT_EXAMPLES, demoChat, type ChatMsg } from "@/lib/demo";
import { fmtDateTime, parseLocal, toInputDateTime } from "@/lib/dates";

// /chat — 날짜 구분선이 있는 전체 내역 + 같은 입력창(14-5). 쓰기는 미리보기 카드를 확인해야만 실행된다(14-4).

export default function ChatPage() {
  const toast = useToast();
  const q = useQueryValue("q");
  const [msgs, setMsgs] = useState<ChatMsg[]>(demoChat);
  const [text, setText] = useState("");
  const [thinking, setThinking] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  const sentQ = useRef(false);

  const send = (t: string) => {
    const at = toInputDateTime(new Date());
    setMsgs((m) => [...m, { id: `u${Date.now()}`, role: "user", text: t, at }]);
    setText("");
    setThinking(true);
    window.setTimeout(() => {
      setThinking(false);
      setMsgs((m) => [...m, { id: `a${Date.now()}`, role: "assistant", at, text: "분석 서비스가 아직 연결되지 않아 답할 수 없습니다. 연결되면 일정 등록·조회·화면 이동을 도와드립니다." }]);
    }, 700);
  };

  useEffect(() => {
    if (q && !sentQ.current) {
      sentQ.current = true;
      send(q);
    }
  }, [q]);

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [msgs, thinking]);


  return (
    <Page>
      <PageHeader
        icon={<MessageCircle />}
        title="대화"
        actions={
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setMsgs([])}>
            <Trash2 aria-hidden />
            대화 지우기
          </button>
        }
      />
      <div className="mb-4">
        <DemoNotice what="대화" />
      </div>
      <div className="card flex min-h-[60vh] flex-col">
        <div className="flex-1 space-y-3 p-4 md:p-6" aria-live="polite">
          {msgs.length === 0 && (
            <div className="py-10 text-center">
              <p className="mb-3 text-[14px] text-muted">이렇게 물어보세요</p>
              <div className="flex flex-wrap justify-center gap-2">
                {CHAT_EXAMPLES.map((e) => (
                  <button key={e} type="button" className="btn btn-sm" onClick={() => send(e)}>
                    {e}
                  </button>
                ))}
              </div>
            </div>
          )}
          <AnimatePresence initial={false}>
            {msgs.map((m, i) => {
              const day = m.at.slice(0, 10);
              const divider = i === 0 || msgs[i - 1].at.slice(0, 10) !== day;
              return (
                <motion.div key={m.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }}>
                  {divider && (
                    <p className="my-4 flex items-center gap-3 text-[12px] font-semibold text-faint">
                      <span className="h-px flex-1 bg-border" />
                      {fmtDateTime(parseLocal(day), false)}
                      <span className="h-px flex-1 bg-border" />
                    </p>
                  )}
                  <Message m={m} onResolve={(state) => {
                    setMsgs((xs) => xs.map((x) => (x.id === m.id && x.role === "preview" ? { ...x, state } : x)));
                    if (state === "confirmed") toast("일정을 등록했습니다 (예시)", { tone: "success" });
                  }} />
                </motion.div>
              );
            })}
          </AnimatePresence>
          {thinking && (
            <p className="flex items-center gap-1 px-2 text-faint" aria-label="답을 만드는 중">
              <span className="size-1.5 animate-bounce rounded-full bg-faint" />
              <span className="size-1.5 animate-bounce rounded-full bg-faint [animation-delay:0.15s]" />
              <span className="size-1.5 animate-bounce rounded-full bg-faint [animation-delay:0.3s]" />
            </p>
          )}
          <div ref={end} />
        </div>
        <form
          className="sticky bottom-0 flex gap-2 rounded-b-xl border-t border-border bg-surface p-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (text.trim()) send(text.trim());
          }}
        >
          <label htmlFor="chat-in" className="sr-only">
            메시지
          </label>
          <textarea
            id="chat-in"
            rows={1}
            className="field min-h-[42px] flex-1 resize-none py-2.5"
            placeholder="다음 주 목요일 발표 리허설 저녁 8시"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                if (text.trim()) send(text.trim());
              }
            }}
          />
          <button type="submit" className="btn btn-primary btn-icon" aria-label="보내기" disabled={!text.trim()}>
            <Send aria-hidden />
          </button>
        </form>
      </div>
    </Page>
  );
}

function Message({ m, onResolve }: { m: ChatMsg; onResolve: (s: "confirmed" | "canceled") => void }) {
  if (m.role === "user")
    return <p className="ml-auto w-fit max-w-[80%] rounded-2xl rounded-br-md bg-primary px-4 py-2 text-[14px] text-on-primary">{m.text}</p>;
  if (m.role === "system")
    return (
      <p className="flex items-center justify-center gap-1.5 text-[12px] text-faint">
        <CalendarCheck className="size-3.5" aria-hidden />
        {m.text}
      </p>
    );
  if (m.role === "assistant")
    return (
      <div className="w-fit max-w-[85%] rounded-2xl rounded-bl-md bg-surface-3 px-4 py-3 text-[14px]">
        <p className="font-semibold">{m.text}</p>
        {m.list && (
          <ul className="mt-2 space-y-1">
            {m.list.map((x) => (
              <li key={x.title} className="flex gap-3">
                <span className="font-medium">{x.title}</span>
                <span className="num text-muted">{x.when}</span>
                <span className="text-faint">{x.sub}</span>
              </li>
            ))}
          </ul>
        )}
        {m.link && (
          <Link href={m.link.href} className="mt-2 inline-flex items-center gap-1 font-semibold text-primary hover:underline">
            {m.link.label}
            <ArrowRight className="size-3.5" aria-hidden />
          </Link>
        )}
      </div>
    );
  // 미리보기 카드 — 확인 전에는 아무것도 바뀌지 않는다
  const done = m.state !== "pending";
  return (
    <div className={`w-full max-w-[460px] rounded-2xl border-2 bg-surface p-4 ${done ? "border-border opacity-70" : "border-primary"}`}>
      <p className="mb-3 flex items-center gap-2 text-[14px] font-bold">
        이렇게 등록할까요?
        {m.state === "confirmed" && <Chip tone="ok">등록함</Chip>}
        {m.state === "canceled" && <Chip>취소함</Chip>}
      </p>
      <dl className="grid grid-cols-[48px_1fr] gap-x-3 gap-y-2 text-[14px]">
        <dt className="text-muted">제목</dt>
        <dd>
          <input className="field field-sm" defaultValue={m.title} disabled={done} aria-label="제목" />
        </dd>
        <dt className="text-muted">일시</dt>
        <dd className="flex flex-wrap gap-1">
          <input type="datetime-local" className="field field-sm w-auto" defaultValue={m.start} disabled={done} aria-label="시작" />
          <input type="time" className="field field-sm w-auto" defaultValue={m.end.slice(11, 16)} disabled={done} aria-label="끝" />
        </dd>
        <dt className="text-muted">분류</dt>
        <dd>
          <select className="field field-sm w-auto" defaultValue={m.category} disabled={done} aria-label="분류">
            <option>개인</option>
            <option>학업</option>
            <option>팀플</option>
          </select>
        </dd>
      </dl>
      {m.conflict && !done && (
        <Banner tone="warn" className="mt-3" icon={<TriangleAlert aria-hidden />}>
          겹치는 일정 1건 — {m.conflict}
        </Banner>
      )}
      {!done && (
        <div className="mt-3 flex justify-end gap-2">
          <button type="button" className="btn btn-sm" onClick={() => onResolve("canceled")}>
            취소
          </button>
          <button type="button" className="btn btn-primary btn-sm" onClick={() => onResolve("confirmed")}>
            확인
          </button>
        </div>
      )}
    </div>
  );
}
