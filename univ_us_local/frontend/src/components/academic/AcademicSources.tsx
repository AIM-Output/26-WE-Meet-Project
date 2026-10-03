"use client";

import Link from "next/link";
import { useState, type ReactNode } from "react";
import { Building2, CalendarDays, Clock, ExternalLink, GraduationCap, Link2, Megaphone, RefreshCw, TriangleAlert, UserRound } from "lucide-react";
import { Section, Toggle } from "@/components/ui/Layout";
import { Banner } from "@/components/ui/Feedback";
import { Chip, StatusBadge, type Tone } from "@/components/ui/Chip";
import { Modal } from "@/components/ui/Modal";
import { useAppData } from "@/components/app/AppData";
import { sourceTitle, useAcademicSources } from "@/lib/useAcademicSources";
import { closeQuery, navigateQuery, useQueryValue } from "@/lib/useQueryState";
import { fmtRelative, fmtShortStamp } from "@/lib/dates";
import type { AcademicSchedule, AcademicSync, SourceRowApi } from "@/lib/types";
import { api } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";

// F1 학사 수집 원천 4곳 켜고 끄기 (F1-S12).
//   AcademicSourcesSection — 설정 › 수집 원천: 원천마다 카드(무엇을 어디서 읽는지 · 상태 · 켜기 · 지금 수집 · 게시판 지정)
//   AcademicSourceStrip    — /academic 머리: 4개 알약 스위치(누르면 바로 켜고 끔)
// 게시판 직접 지정 모달은 ?board=my_dept (모달 = 쿼리 + push).

const META: Record<string, { icon: ReactNode; short: string; desc: string }> = {
  jnu_calendar: { icon: <CalendarDays />, short: "학사일정 표", desc: "전남대 학사일정 표 — 개강·등록·수강신청·시험처럼 학교 전체 일정" },
  jnu_notice: { icon: <Megaphone />, short: "학사안내", desc: "전남대 홈페이지 공지사항 › 학사안내 — 표에 없는 신청 기간과 시각" },
  my_dept: { icon: <GraduationCap />, short: "내 학부", desc: "프로필의 학과(학부) 홈페이지 학사 공지 — 졸업논문·전공 신청처럼 학과에서만 알리는 일정" },
  my_college: { icon: <Building2 />, short: "내 단과대학", desc: "프로필의 단과대학 홈페이지 학사 공지 — 단과대학 단위 신청·행사 일정" },
};
const meta = (key: string) => META[key] ?? { icon: <CalendarDays />, short: key, desc: "" };
/** '프로필에 ○○ 없어' 의 주어 (조사까지) */
const scopeSubject = (r: SourceRowApi) => (r.scope === "college" ? "단과대학이" : "학과가");
const host = (url: string | null) => (url ? url.replace(/^https?:\/\//, "").replace(/\/.*$/, "") : "");

type Problem = "needs_profile" | "not_found" | null;
const problemOf = (r: SourceRowApi): Problem => (r.resolve === "needs_profile" || r.resolve === "not_found" ? r.resolve : null);

function badge(r: SourceRowApi, running: boolean): { tone: Tone; label: string } {
  if (!r.enabled) return { tone: "neutral", label: "꺼짐" };
  if (running) return { tone: "info", label: "수집 중" };
  const p = problemOf(r);
  if (p === "needs_profile") return { tone: "warn", label: "소속 필요" };
  if (p === "not_found") return { tone: "warn", label: "홈페이지 못 찾음" };
  switch (r.state) {
    case "ok":
      return { tone: "ok", label: "정상" };
    case "failed":
      return { tone: "danger", label: "실패" };
    case "format_changed":
      return { tone: "danger", label: "형식 변경 의심" };
    default:
      return { tone: "neutral", label: "수집 전" };
  }
}

/** 수집이 지금 이 원천을 돌고 있나 (key=academic 이면 켜진 전부) */
function useRunning() {
  const { status, academicSyncing } = useAppData();
  const keys = status?.academic?.sync?.keys ?? null;
  return (key: string) => academicSyncing && (!keys || keys.includes(key));
}

/* ------------------------------------------------------------------ 설정 › 수집 원천 */

export function AcademicSourcesSection() {
  const src = useAcademicSources();
  const running = useRunning();
  const boardKey = useQueryValue("board");
  const editing = src.sources.find((r) => r.key === boardKey && r.scope) ?? null;
  const school = src.sources.filter((r) => !r.scope);
  const mine = src.sources.filter((r) => r.scope);
  const dir = src.data?.directory;

  return (
    <Section
      title="학사일정 (F1)"
      action={
        <button type="button" className="btn btn-primary btn-sm" disabled={src.syncing} onClick={() => void src.sync()}>
          <RefreshCw className={src.syncing ? "animate-spin" : ""} aria-hidden />
          {src.syncing ? "수집 중…" : "켜진 곳 전부 수집"}
        </button>
      }
    >
      <p className="-mt-1 mb-4 text-[13px] text-muted">
        네 곳에서 학사 일정을 모읍니다. 끄면 그곳에서 새로 받지 않고, 그곳에서만 온 일정은 목록·캘린더에서 빠집니다. 다시 켜면 그대로 돌아옵니다.
      </p>
      {src.error && !src.data ? (
        <Banner tone="danger">수집 원천을 불러오지 못했습니다 — {src.error}</Banner>
      ) : !src.data ? (
        <p className="py-4 text-[14px] text-muted">불러오는 중…</p>
      ) : (
        <div className="space-y-5">
          <SourceGroup title="학교 전체">
            {school.map((r) => (
              <SourceCard key={r.key} r={r} running={running(r.key)} src={src} />
            ))}
          </SourceGroup>
          <SourceGroup
            title="내 소속"
            hint={
              <>
                <Link href="/settings/profile" className="font-semibold text-primary hover:underline">
                  내 프로필
                </Link>
                의 단과대학·학과로 홈페이지를 찾고, 그 사이트의 학사 공지 게시판을 읽습니다
              </>
            }
          >
            {mine.map((r) => (
              <SourceCard key={r.key} r={r} running={running(r.key)} src={src} />
            ))}
          </SourceGroup>
        </div>
      )}
      {src.data && <ScheduleRow schedule={src.data.schedule} retry={src.data.sync.retry} onChange={() => void src.reload()} />}
      <div className="mt-4 flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-[12px] text-faint">
        <span>예약 수집은 켜진 원천만 받습니다</span>
        {dir && dir.colleges > 0 && (
          <span className="num">
            홈페이지 목록: 단과대학 {dir.colleges} · 학부(과) {dir.departments}
            {dir.updatedAt && ` · ${dir.updatedAt.slice(0, 10)}`}
          </span>
        )}
      </div>
      {src.data && src.data.log.length > 0 && (
        <details className="mt-3">
          <summary className="cursor-pointer text-[13px] font-semibold text-muted">sync.log 끝부분</summary>
          <pre className="thin-scroll mt-2 max-h-48 overflow-auto rounded-lg bg-surface-2 p-3 text-[12px] leading-relaxed whitespace-pre-wrap">{src.data.log.join("\n")}</pre>
        </details>
      )}
      <BoardModal r={editing} src={src} />
    </Section>
  );
}

/** 예약 수집 — 매일 08:00 한 번 + 놓치면 켜질 때 + 실패하면 5·15·45분 뒤 재시도 (작업 스케줄러) */
function ScheduleRow({ schedule, retry, onChange }: { schedule: AcademicSchedule; retry?: AcademicSync["retry"]; onChange: () => void }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const on = schedule.registered && schedule.scheduled !== false && schedule.pathOk !== false;
  const stale = schedule.registered && !on; // 예전 방식(06·18시)이나 옛 경로로 등록돼 있음
  const set = async (v: boolean) => {
    setBusy(true);
    try {
      await api.setAcademicSchedule(v);
      toast(v ? `예약 수집을 켰습니다 — 매일 ${schedule.at}` : "예약 수집을 껐습니다", { tone: "success" });
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), { tone: "error" });
    } finally {
      setBusy(false);
      onChange();
    }
  };
  const fmt = (s?: string | null) => (s ? `${fmtShortStamp(s)}` : "—");
  return (
    <div className={`mt-4 rounded-xl border px-3 py-3 md:px-4 ${on ? "border-border" : "border-[#f5dca6] bg-warn-soft"}`}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <Clock className={`size-4 flex-none ${on ? "text-primary" : "text-warn-text"}`} aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="text-[14px] font-semibold">
            예약 수집 · 매일 {schedule.at}
            {!schedule.available ? " — 이 서버에서는 쓰지 않음" : on ? "" : stale ? " — 예전 설정이라 다시 켜야 합니다" : " — 꺼져 있음"}
          </p>
          <p className="num text-[12px] text-muted">
            {retry?.next_at
              ? `수집 실패 — ${retry.next_at.slice(11, 16)}에 다시 시도합니다 (${retry.attempt - 1}/3)`
              : on
                ? `다음 ${fmt(schedule.nextRun)} · 마지막 ${fmt(schedule.lastRun)}`
                : "PC 가 꺼져 있던 시각은 켜질 때 한 번 따라잡고, 실패하면 5·15·45분 뒤 다시 시도합니다"}
          </p>
        </div>
        {schedule.available && (
          <Toggle checked={on} disabled={busy} label="학사일정 예약 수집" onChange={(v) => void set(v)} />
        )}
      </div>
    </div>
  );
}

function SourceGroup({ title, hint, children }: { title: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <div>
      <p className="mb-2 text-[13px] font-bold text-muted">{title}</p>
      {hint && <p className="-mt-1 mb-2 text-[12px] text-faint">{hint}</p>}
      <ul className="space-y-2">{children}</ul>
    </div>
  );
}

type Src = ReturnType<typeof useAcademicSources>;

function SourceCard({ r, running, src }: { r: SourceRowApi; running: boolean; src: Src }) {
  const m = meta(r.key);
  const b = badge(r, running);
  const problem = problemOf(r);
  const busy = src.busy === r.key;
  const canSync = r.enabled && !problem && !src.syncing;
  const openBoard = () => navigateQuery({ board: r.key }, "push");

  return (
    <li className={`rounded-xl border px-3 py-3 transition-colors md:px-4 ${r.enabled ? "border-border bg-surface" : "border-dashed border-border-strong bg-surface-2"}`}>
      <div className="flex items-start gap-3">
        <span
          className={`mt-0.5 grid size-9 flex-none place-items-center rounded-lg [&>svg]:size-[18px] ${r.enabled ? "bg-primary-soft text-primary" : "bg-surface-3 text-faint"}`}
          aria-hidden
        >
          {m.icon}
        </span>
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className={`text-[15px] font-bold ${r.enabled ? "" : "text-muted"}`}>{r.name}</span>
            {r.scope && r.target && (
              <Chip tone="primary" square icon={<UserRound className="size-3" aria-hidden />}>
                {r.target}
              </Chip>
            )}
            <StatusBadge tone={b.tone}>{b.label}</StatusBadge>
          </p>
          <p className="mt-0.5 text-[13px] text-muted">{m.desc}</p>
          {r.scope && <BoardLine r={r} />}
          <p className="num mt-1 text-[12px] text-faint">
            {r.interval} · {r.lastRunAt ? `마지막 ${fmtShortStamp(r.lastRunAt)} (${fmtRelative(r.lastRunAt)})` : "아직 받지 않음"} · 보이는 일정{" "}
            <span className={r.enabled ? "font-semibold text-muted" : "line-through"}>{r.items}건</span>
            {!r.enabled && r.items > 0 && " (꺼서 숨김)"}
          </p>
        </div>
        <div className="flex flex-none items-center pt-1">
          <Toggle checked={r.enabled} disabled={busy} label={`${sourceTitle(r)} 수집`} onChange={(v) => void src.toggle(r, v)} />
        </div>
      </div>

      {r.enabled && (problem || r.stale || ((r.state === "failed" || r.state === "format_changed") && r.error)) && (
        <div className="mt-3 pl-12">
          {problem === "needs_profile" ? (
            <Banner
              tone="warn"
              action={
                <Link href="/settings/profile" className="btn btn-sm">
                  프로필에서 고르기
                </Link>
              }
            >
              프로필에 {scopeSubject(r)} 없어 기다리는 중입니다
            </Banner>
          ) : problem === "not_found" ? (
            <Banner
              tone="warn"
              action={
                <button type="button" className="btn btn-sm" onClick={openBoard}>
                  게시판 직접 지정
                </button>
              }
            >
              &lsquo;{r.target}&rsquo; 홈페이지를 학교 목록에서 찾지 못했습니다
            </Banner>
          ) : r.stale ? (
            <Banner
              tone="info"
              action={
                <button type="button" className="btn btn-sm" disabled={!canSync} onClick={() => void src.sync(r.key)}>
                  지금 받기
                </button>
              }
            >
              {r.overrideUrl ? "지정한 게시판이 바뀌었습니다" : "소속이 바뀌었습니다"} — 새 게시판에서 받으면 이전 게시판의 일정은 정리됩니다
            </Banner>
          ) : (
            <p className="text-[12px] font-medium text-danger-text">{r.error}</p>
          )}
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2 pl-12">
        <button type="button" className="btn btn-sm" disabled={!canSync} onClick={() => void src.sync(r.key)}>
          <RefreshCw className={running ? "animate-spin" : ""} aria-hidden />
          {r.state === "failed" || r.state === "format_changed" ? "다시 시도" : "지금 수집"}
        </button>
        {r.url && (
          <a href={r.url} target="_blank" rel="noopener noreferrer" className="btn btn-ghost btn-sm">
            <ExternalLink aria-hidden />
            원문 보기
          </a>
        )}
        {r.scope && problem !== "needs_profile" && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={openBoard}>
            <Link2 aria-hidden />
            {r.overrideUrl ? "지정한 게시판 바꾸기" : "게시판 직접 지정"}
          </button>
        )}
      </div>
    </li>
  );
}

/** ③·④ — 어느 홈페이지의 어느 게시판을 읽는지 */
function BoardLine({ r }: { r: SourceRowApi }) {
  if (r.resolve === "needs_profile" && !r.board) return null;
  const listed = r.listedAs && r.target && r.listedAs !== r.target ? ` (학교 목록: ${r.listedAs})` : "";
  if (!r.board)
    return r.homepage ? (
      <p className="mt-1 text-[13px]">
        <span className="font-semibold">{host(r.homepage)}</span>
        <span className="text-muted">
          {listed} — 다음 수집 때 이 홈페이지에서 학사 공지 게시판을 찾습니다
        </span>
      </p>
    ) : null;
  return (
    <p className="mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[13px]">
      <span className="font-semibold">
        {host(r.board.url)} › {r.board.label ?? "공지"}
      </span>
      <span className="text-muted">
        {r.board.category ? `· 말머리 '${r.board.category}'만` : "· 제목으로 학사 글만"}
        {listed}
      </span>
      <Chip square tone={r.board.via === "manual" ? "accent" : "neutral"}>
        {r.board.via === "manual" ? "직접 지정" : `자동으로 찾음${r.board.checkedAt ? ` · ${r.board.checkedAt.slice(5, 10).replace("-", "/")}` : ""}`}
      </Chip>
    </p>
  );
}

const BOARD_URL = /^https?:\/\/[\w.-]+\/bbs\/[\w-]+\/\d+(\/|$)/;

function BoardModal({ r, src }: { r: SourceRowApi | null; src: Src }) {
  return (
    <Modal open={!!r} onClose={() => closeQuery(["board"])} title={r ? `${r.name} — 게시판 직접 지정` : ""}>
      {r && <BoardForm key={r.key} r={r} src={src} />}
    </Modal>
  );
}

function BoardForm({ r, src }: { r: SourceRowApi; src: Src }) {
  const [url, setUrl] = useState(r.overrideUrl ?? "");
  const [saving, setSaving] = useState(false);
  const v = url.trim();
  const valid = BOARD_URL.test(v);
  const save = async (value: string | null) => {
    setSaving(true);
    const ok = await src.setOverride(r, value);
    setSaving(false);
    if (ok) closeQuery(["board"]);
  };
  return (
    <>
      <p className="mb-3 text-[13px] text-muted">
        {r.target ? `${r.target} ` : ""}홈페이지에서 학사 공지 게시판을 열고, 주소창의 주소를 붙여 넣으세요. 말머리(예: 학사)를 고른 뒤의 주소면 그 말머리 글만 읽습니다.
      </p>
      <label className="label" htmlFor="board-url">
        게시판 주소
      </label>
      <input
        id="board-url"
        data-autofocus
        className="field"
        inputMode="url"
        placeholder="https://aisw.jnu.ac.kr/bbs/aisw/64/artclList.do"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && valid && !saving) void save(v);
        }}
        aria-invalid={v.length > 0 && !valid}
      />
      {v.length > 0 && !valid ? (
        <p className="hint text-danger-text">
          <TriangleAlert className="mr-1 inline size-3.5 align-[-2px]" aria-hidden />
          학과·단과대학 홈페이지 게시판 주소(…/bbs/…/artclList.do)가 아닙니다
        </p>
      ) : (
        <p className="hint">
          {r.board?.via === "auto" ? `지금은 자동으로 찾은 ${host(r.board.url)} › ${r.board.label ?? "공지"} 를 읽고 있습니다.` : "비워 두면 프로필 소속으로 자동으로 찾습니다."}
        </p>
      )}
      <div className="mt-5 flex flex-wrap items-center justify-end gap-2">
        {r.overrideUrl && (
          <button type="button" className="btn btn-ghost mr-auto" disabled={saving} onClick={() => void save(null)}>
            자동으로 되돌리기
          </button>
        )}
        <button type="button" className="btn" onClick={() => closeQuery(["board"])}>
          취소
        </button>
        <button type="button" className="btn btn-primary" disabled={!valid || saving || v === r.overrideUrl} onClick={() => void save(v)}>
          저장하고 받기
        </button>
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ /academic 머리 */

export function AcademicSourceStrip() {
  const src = useAcademicSources();
  const running = useRunning();
  if (!src.data) return null;
  return (
    <div className="flex flex-wrap items-center gap-2" role="group" aria-label="학사일정 수집 원천">
      <span className="mr-1 text-[13px] font-semibold text-muted">가져오는 곳</span>
      {src.sources.map((r) => {
        const m = meta(r.key);
        const problem = r.enabled ? problemOf(r) : null;
        const failed = r.enabled && (r.state === "failed" || r.state === "format_changed");
        const label = r.scope && r.target ? r.target : m.short;
        const why = !r.enabled
          ? "꺼짐 — 누르면 켭니다"
          : problem === "needs_profile"
            ? `프로필에 ${scopeSubject(r)} 없습니다`
            : problem === "not_found"
              ? "홈페이지를 찾지 못했습니다 — 수집 원천에서 게시판을 지정하세요"
              : failed
                ? (r.error ?? "마지막 수집 실패")
                : `켜짐 · 보이는 일정 ${r.items}건 — 누르면 끕니다`;
        return (
          <button
            key={r.key}
            type="button"
            role="switch"
            aria-checked={r.enabled}
            aria-label={`${sourceTitle(r)} ${r.enabled ? "켜짐" : "꺼짐"}`}
            title={why}
            disabled={src.busy === r.key}
            onClick={() => void src.toggle(r, !r.enabled)}
            className={`inline-flex h-8 max-w-full items-center gap-1.5 rounded-full border px-3 text-[13px] font-semibold transition-colors disabled:opacity-60 [&>svg]:size-3.5 [&>svg]:flex-none ${
              r.enabled ? "border-primary/40 bg-primary-soft text-primary hover:border-primary" : "border-dashed border-border-strong text-faint hover:text-muted"
            }`}
          >
            {running(r.key) ? <RefreshCw className="animate-spin" aria-hidden /> : problem || failed ? <TriangleAlert className="text-warn-text" aria-hidden /> : m.icon}
            <span className={`truncate ${r.enabled ? "" : "line-through decoration-1"}`}>{label}</span>
            {r.enabled && <span className="num text-[12px] font-medium opacity-75">{r.items}</span>}
          </button>
        );
      })}
      <Link href="/settings/sources" className="ml-1 text-[13px] font-semibold text-muted underline-offset-2 hover:text-text hover:underline">
        관리
      </Link>
    </div>
  );
}
