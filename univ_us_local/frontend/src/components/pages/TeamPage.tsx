"use client";

import { useState } from "react";
import { Copy, Info, Star, Users, Vote as VoteIcon, WifiOff } from "lucide-react";
import { Page, PageHeader, Section } from "@/components/ui/Layout";
import { Tabs } from "@/components/ui/Tabs";
import { Banner, DemoNotice } from "@/components/ui/Feedback";
import { Chip, DdayChip, StatusBadge } from "@/components/ui/Chip";
import { Modal } from "@/components/ui/Modal";
import { ProgressBar } from "@/components/ui/Progress";
import { WeekGrid } from "@/components/ui/WeekGrid";
import { useToast } from "@/components/ui/Toast";
import { closeQuery, navigateQuery, useQueryParam, useQueryValue } from "@/lib/useQueryState";
import { demoBusy, demoCandidates, demoPoll, demoTeam, demoTeamTasks, TEAM_DAYS, TEAM_HOURS, type Vote } from "@/lib/demo";
import { parseLocal } from "@/lib/dates";

// /team — 일정 조율 / 할 일 / 팀원 (Frontend-Route 18절). 서버가 필요한 첫 화면 — 실패를 이 화면 안에 가둔다.
// '정보 없음'을 가능으로 세지 않는다.

const TABS = ["schedule", "tasks", "members"] as const;
const initials = (n: string) => n.slice(0, 1);

export default function TeamPage() {
  const toast = useToast();
  const [tab, setTab] = useQueryParam("tab", "schedule", TABS);
  const [offline, setOffline] = useState(false);
  const t = demoTeam;

  return (
    <Page wide>
      <PageHeader
        icon={<Users />}
        title={t.name}
        subtitle="팀플 일정 조율"
        actions={
          <>
            <select className="field field-sm w-auto" aria-label="팀 선택" defaultValue={t.id}>
              <option value={t.id}>{t.name}</option>
            </select>
            <button
              type="button"
              className="btn btn-sm"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(`${window.location.origin}/team?join=${t.code}`);
                  toast(`초대 링크를 복사했습니다 · 코드 ${t.code}`, { tone: "success" });
                } catch {
                  toast(`초대 코드: ${t.code}`);
                }
              }}
            >
              <Copy aria-hidden />
              초대 링크 복사
            </button>
          </>
        }
      />
      <div className="mb-5 space-y-3">
        {/* 공유 고지 — 접히지 않는다 */}
        <div className="flex gap-3 rounded-xl border border-primary-soft-2 bg-primary-soft px-4 py-3 text-[14px] text-primary">
          <Info className="mt-0.5 size-4 flex-none" aria-hidden />
          <p>
            <b>공유되는 것:</b> 바쁜 시간대(시각만) · 표시 이름 · 팀 할 일
            <br />
            <b>공유되지 않는 것:</b> 일정 제목 · 과목명 · 성적 · 이름 · 학번
          </p>
        </div>
        <DemoNotice what="팀플(서버)" />
        {offline && (
          <Banner
            tone="danger"
            icon={<WifiOff aria-hidden />}
            action={
              <button type="button" className="btn btn-sm" onClick={() => setOffline(false)}>
                다시 시도
              </button>
            }
          >
            팀 기능은 인터넷 연결이 필요합니다 — 다른 화면은 그대로 쓸 수 있습니다
          </Banner>
        )}
      </div>
      <Tabs
        className="mb-5"
        label="팀 보기"
        value={tab}
        onChange={(x) => setTab(x)}
        items={[
          { key: "schedule", label: "일정 조율" },
          { key: "tasks", label: "할 일", count: demoTeamTasks.filter((x) => !x.done).length },
          { key: "members", label: "팀원", count: t.members.length },
        ]}
      />
      {tab === "schedule" && <Schedule />}
      {tab === "tasks" && <Tasks />}
      {tab === "members" && <Members onLeave={() => toast("팀 나가기는 팀 서버가 연결된 뒤에 할 수 있습니다", { tone: "error" })} />}
      <PollPanel />
    </Page>
  );
}

function Schedule() {
  const stale = demoTeam.members.filter((m) => m.stale || !m.sharing).length;
  const total = demoTeam.members.length;
  const best = (d: number, h: number) => demoCandidates.find((c) => c.day === d && c.hour === h);
  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
      <Section title="바쁜 시간 겹쳐 보기" action={<span className="text-[12px] text-faint">진할수록 바쁜 사람이 많음 · 이름·제목 없음</span>}>
        <div className="mb-3 flex flex-wrap items-center gap-2 text-[13px]">
          <select className="field field-sm w-auto" aria-label="길이" defaultValue="1">
            <option value="1">1시간</option>
            <option value="2">2시간</option>
          </select>
          <select className="field field-sm w-auto" aria-label="기간" defaultValue="7">
            <option value="7">다음 7일</option>
          </select>
          <select className="field field-sm w-auto" aria-label="시간대" defaultValue="a">
            <option value="a">평일 09~22시</option>
          </select>
          <button type="button" className="btn btn-primary btn-sm">
            찾기
          </button>
        </div>
        {stale > 0 && (
          <Banner tone="warn" className="mb-3">
            {stale}명의 정보가 오래되었거나 없어 정확하지 않을 수 있습니다
          </Banner>
        )}
        <WeekGrid
          caption="팀원 바쁜 시간 히트맵"
          days={TEAM_DAYS}
          hours={TEAM_HOURS}
          cellHeight={24}
          renderCell={(d, hi) => {
            const n = demoBusy[d][TEAM_HOURS.indexOf(hi as (typeof TEAM_HOURS)[number])];
            const c = best(d, hi);
            return (
              <div
                className="relative grid h-full place-items-center rounded"
                style={{ background: n === 0 ? "var(--surface-2)" : `color-mix(in oklab, var(--primary) ${Math.round((n / total) * 85) + 8}%, var(--surface))` }}
                title={`${TEAM_DAYS[d]} ${hi}시 — ${n}명 바쁨`}
                aria-label={`${TEAM_DAYS[d]} ${hi}시 ${n}명 바쁨${c ? ", 후보" : ""}`}
              >
                {c && <Star className="size-3.5 fill-accent text-accent" aria-hidden />}
              </div>
            );
          }}
        />
      </Section>
      <Section title="후보">
        <ul className="space-y-2">
          {demoCandidates.map((c) => (
            <li key={c.id} className={`flex flex-wrap items-center gap-3 rounded-xl border p-3 ${c.best ? "border-primary bg-primary-soft/40" : "border-border"}`}>
              {c.best && <Star className="size-4 fill-accent text-accent" aria-label="최선" />}
              <span className="min-w-0 flex-1">
                <span className="num block text-[14px] font-semibold">{c.label}</span>
                <span className="text-[13px] text-muted">{c.note}</span>
              </span>
              <span className="num text-[13px] font-bold">
                {c.available}/{c.total}
              </span>
            </li>
          ))}
        </ul>
        <div className="mt-3 flex justify-end">
          <button type="button" className="btn btn-primary btn-sm" onClick={() => navigateQuery({ poll: demoPoll.id }, "push")}>
            <VoteIcon aria-hidden />
            투표 열기
          </button>
        </div>
      </Section>
    </div>
  );
}

function PollPanel() {
  const poll = useQueryValue("poll");
  const toast = useToast();
  const [mine, setMine] = useState<Vote[]>(demoPoll.votes.m1);
  const members = demoTeam.members;
  const votes: Record<string, Vote[]> = { ...demoPoll.votes, m1: mine };
  const POINT: Record<string, number> = { 가능: 2, 어려움: 1, 불가: 0 };
  const score = demoPoll.options.map((_, i) => members.reduce((s, m) => s + (POINT[votes[m.id]?.[i] ?? ""] ?? 0), 0));
  const notVoted = members.filter((m) => (votes[m.id] ?? []).every((v) => v === null));
  const cell = (v: Vote) =>
    v === "가능" ? <StatusBadge tone="ok">가능</StatusBadge> : v === "어려움" ? <StatusBadge tone="warn">어려움</StatusBadge> : v === "불가" ? <StatusBadge tone="danger">불가</StatusBadge> : <span className="text-faint">—</span>;
  return (
    <Modal open={!!poll} onClose={() => closeQuery(["poll"])} size="lg" title={`회의 시간 투표 · ${demoPoll.closes} 마감`}>
      <div className="overflow-x-auto pt-1">
        <table className="w-full min-w-[520px] text-[14px]">
          <thead>
            <tr className="text-left text-[12px] text-muted">
              <th className="py-2 pr-2 font-semibold">팀원</th>
              {demoPoll.options.map((o) => (
                <th key={o} className="num px-2 py-2 font-semibold">
                  {o}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {members.map((m) => (
              <tr key={m.id} className={m.me ? "bg-primary-soft/40" : ""}>
                <td className="py-2 pr-2 font-semibold">{m.me ? "나" : m.name}</td>
                {demoPoll.options.map((o, i) => (
                  <td key={o} className="px-2 py-2">
                    {m.me ? (
                      <select
                        className="field field-sm w-auto"
                        aria-label={`${o} 내 투표`}
                        value={mine[i] ?? ""}
                        onChange={(e) => setMine((xs) => xs.map((x, j) => (j === i ? ((e.target.value || null) as Vote) : x)))}
                      >
                        <option value="">선택</option>
                        <option>가능</option>
                        <option>어려움</option>
                        <option>불가</option>
                      </select>
                    ) : (
                      cell(votes[m.id]?.[i] ?? null)
                    )}
                  </td>
                ))}
              </tr>
            ))}
            <tr className="font-bold">
              <td className="py-2 pr-2">점수</td>
              {score.map((s, i) => (
                <td key={i} className="num px-2 py-2">
                  {s}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-border pt-3">
        <span className="text-[13px] text-muted">
          {notVoted.length}명 미투표 — {notVoted.map((m) => (m.me ? "(나)" : m.name)).join(", ")}
        </span>
        <button
          type="button"
          className="btn btn-primary btn-sm ml-auto"
          onClick={() => {
            closeQuery(["poll"]);
            toast("10/1(목) 14:00 회의를 확정했습니다 — 전원 캘린더에 들어갑니다 (예시)", { tone: "success" });
          }}
        >
          확정 (팀장)
        </button>
      </div>
    </Modal>
  );
}

function Tasks() {
  const [tasks, setTasks] = useState(demoTeamTasks);
  const done = tasks.filter((t) => t.done).length;
  const name = (id: string) => demoTeam.members.find((m) => m.id === id);
  return (
    <div className="space-y-4">
      <Section>
        <p className="num mb-2 text-[14px] font-semibold">
          {tasks.length}건 중 {done}건 완료
        </p>
        <ProgressBar value={done} max={tasks.length} tone="ok" label="팀 할 일 진행" />
      </Section>
      <ul className="overflow-hidden rounded-xl border border-border bg-surface">
        {tasks.map((t) => {
          const overdue = !t.done && t.due < new Date().toISOString().slice(0, 10);
          const mineTask = t.owners.includes("m1");
          return (
            <li key={t.id} className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3 last:border-b-0">
              <input
                type="checkbox"
                className="size-4 accent-[var(--primary)]"
                checked={t.done}
                aria-label={`${t.title} 완료`}
                onChange={(e) => setTasks((xs) => xs.map((x) => (x.id === t.id ? { ...x, done: e.target.checked } : x)))}
              />
              <span className={`min-w-0 flex-1 text-[14px] font-medium ${t.done ? "text-faint line-through" : ""}`}>
                {t.title}
                {"doneBy" in t && t.done && t.doneBy && <span className="ml-2 text-[12px] font-normal text-faint">{t.doneBy}이 {t.doneAt} 완료</span>}
              </span>
              {mineTask && <Chip tone="primary">나</Chip>}
              <span className="flex -space-x-1.5">
                {t.owners.map((o) => (
                  <span key={o} className="grid size-7 place-items-center rounded-full border-2 border-surface bg-surface-3 text-[12px] font-bold" title={name(o)?.name}>
                    {initials(name(o)?.name ?? "?")}
                  </span>
                ))}
              </span>
              {overdue ? <span className="text-[12px] font-semibold text-danger-text">마감 지남 · {name(t.owners[0])?.name}</span> : <DdayChip date={parseLocal(t.due)} done={t.done} />}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function Members({ onLeave }: { onLeave: () => void }) {
  return (
    <div className="space-y-4">
      <ul className="overflow-hidden rounded-xl border border-border bg-surface">
        {demoTeam.members.map((m) => (
          <li key={m.id} className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3 last:border-b-0">
            <span className="grid size-9 place-items-center rounded-full bg-primary-soft text-[14px] font-bold text-primary">{initials(m.name)}</span>
            <span className="min-w-0 flex-1">
              <span className="block text-[14px] font-semibold">
                {m.name}
                {m.me && " (나)"}
              </span>
              <span className="text-[12px] text-muted">
                {m.role} · 마지막 갱신 {m.updated}
              </span>
            </span>
            {m.stale && <StatusBadge tone="warn">정보 오래됨</StatusBadge>}
            {!m.sharing && <StatusBadge tone="neutral">공유 안 함</StatusBadge>}
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap justify-end gap-2">
        <button type="button" className="btn btn-sm">
          공유 일시 중지
        </button>
        <button type="button" className="btn btn-sm">
          복구 코드 재발급
        </button>
        <button type="button" className="btn btn-danger btn-sm" onClick={onLeave}>
          팀 나가기 (내 공유 데이터 즉시 삭제)
        </button>
      </div>
    </div>
  );
}
