"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  BookOpenCheck,
  ChevronRight,
  CircleCheck,
  CircleHelp,
  CircleX,
  Download,
  ExternalLink,
  GraduationCap,
  LogIn,
  Plus,
  RotateCcw,
  Save,
  Trash2,
  Undo2,
} from "lucide-react";
import { Page, PageHeader, Section } from "@/components/ui/Layout";
import { Tabs } from "@/components/ui/Tabs";
import { Banner, EmptyState, ErrorPanel, SkeletonCards, SyncBanner } from "@/components/ui/Feedback";
import { Chip, StatusBadge } from "@/components/ui/Chip";
import { Donut, ProgressBar } from "@/components/ui/Progress";
import { Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { closeQuery, navigateQuery, useQueryParam, useQueryValue } from "@/lib/useQueryState";
import { useGradImport, useGraduation } from "@/lib/useGraduation";
import { useProfile } from "@/lib/useProfile";
import { api } from "@/lib/api";
import { fmtRelative, fmtShortStamp } from "@/lib/dates";
import { TRACK_LABEL, type Track } from "@/lib/profile";
import {
  CERT_LABEL,
  LEVEL_TONE,
  num,
  SEMESTER_OPTIONS,
  termKey,
  termLabel,
  termSort,
  VERDICT_TONE,
  type Assumptions,
  type CertState,
  type CurriculumState,
  type GradArea,
  type GradCert,
  type GradCourseRow,
  type GraduationStatus,
  type Plan,
  type SimSide,
} from "@/lib/graduation";

// /graduation — 요약 / 이수 과목 / 가정 계산 (Frontend-Route 7절).
// 계산은 백엔드 규칙 코드(F2_Graduation_agent/graduation/calc.py) 한 곳에서만 한다 — 화면에 규칙을 복제하지 않는다.

const TABS = ["summary", "courses", "whatif"] as const;
const TRACKS = ["single", "double", "minor"] as const;
const FILTERS = ["all", "unmapped", "manual"] as const;

type G = ReturnType<typeof useGraduation>;

export default function GraduationPage() {
  const { profile } = useProfile();
  const [tab, setTab] = useQueryParam("tab", "summary", TABS);
  const [track, setTrack] = useQueryParam<Track>("track", (profile?.track as Track) ?? "single", TRACKS);
  const areaKey = useQueryValue("area");
  const newCourse = useQueryValue("new") === "course";
  const g = useGraduation(track);
  const imp = useGradImport(g.reload);
  const d = g.data;

  if (g.loading)
    return (
      <Page>
        <PageHeader icon={<GraduationCap />} title="졸업요건" />
        <SkeletonCards count={3} />
      </Page>
    );
  if (!d)
    return (
      <Page>
        <PageHeader icon={<GraduationCap />} title="졸업요건" />
        <ErrorPanel message={`계산하지 못했습니다 — ${g.error ?? ""}`} onRetry={() => void g.reload()} />
      </Page>
    );

  const rs = d.ruleset;
  const who = [d.profile.department, d.profile.major].filter(Boolean).join(" ") || "학과 미입력";
  const year = d.profile.admissionYear ? `${d.profile.admissionYear} 입학` : "입학년도 미입력";
  const verdictTone = VERDICT_TONE[d.verdict];
  const area = areaKey ? d.areas.find((a) => a.key === areaKey) ?? null : null;

  return (
    <Page>
      <PageHeader
        icon={<GraduationCap />}
        title="졸업요건"
        subtitle={
          <span className="inline-flex flex-wrap items-center gap-2">
            기준: {rs.label}
            <Chip tone={LEVEL_TONE[rs.level]} square>
              {rs.levelLabel}
            </Chip>
            {rs.edited && (
              <Chip tone="accent" square>
                내가 고침
              </Chip>
            )}
          </span>
        }
        actions={
          <>
            <label className="sr-only" htmlFor="track">
              이수유형
            </label>
            <select id="track" className="field field-sm w-auto" value={track} onChange={(e) => setTrack(e.target.value as Track)}>
              {TRACKS.map((t) => (
                <option key={t} value={t}>
                  {year} · {who} · {TRACK_LABEL[t]}
                </option>
              ))}
            </select>
            <Link href="/settings/requirements" className="btn btn-sm">
              기준 보기
            </Link>
          </>
        }
      />

      {g.busy && <div className="fixed inset-x-0 top-16 z-30 h-0.5 animate-pulse bg-primary" aria-hidden />}

      <div className="mb-5 space-y-3">
        <Banner tone="neutral">참고용입니다 · 공식 졸업사정이 아닙니다. 최종 확인은 학과 사무실·학사정보시스템에서 하세요.</Banner>
        {d.profileMissing.length > 0 && (
          <Banner
            tone="primary"
            action={
              <Link href="/onboarding?step=1" className="btn btn-sm">
                입력하기
              </Link>
            }
          >
            학과·입학년도를 입력하면 졸업요건 기준이 자동으로 붙습니다
          </Banner>
        )}
        {rs.warnings.map((w) => (
          <Banner
            key={w}
            tone="warn"
            action={
              <Link href="/settings/requirements" className="btn btn-sm">
                기준 확인
              </Link>
            }
          >
            {w}
          </Banner>
        ))}
        <CurriculumBanner d={d} reload={g.reload} />
        {imp.running && <SyncBanner state="running">학사정보시스템에서 이수 내역을 가져오는 중입니다 — 1분쯤 걸립니다</SyncBanner>}
        <ImportProblemBanner imp={imp} />
        {d.unmapped.length > 0 && (
          <Banner
            tone="warn"
            action={
              <button type="button" className="btn btn-sm" onClick={() => navigateQuery({ tab: "courses", filter: "unmapped" }, "replace")}>
                지정하기
              </button>
            }
          >
            분류하지 못한 과목 {d.unmapped.length}건 — 지정해야 정확해집니다
          </Banner>
        )}
      </div>

      <Tabs
        className="mb-5"
        label="졸업요건 보기"
        value={tab}
        onChange={(t) => setTab(t)}
        items={[
          { key: "summary", label: "요약" },
          { key: "courses", label: "이수 과목", count: d.courses.length },
          { key: "whatif", label: "가정 계산" },
        ]}
      />

      {tab === "summary" && (
        <div className="space-y-4">
          {d.data.count === 0 && (
            <EmptyState
              icon={<BookOpenCheck />}
              title="학사정보시스템에서 이수 내역을 가져오세요"
              action={
                <>
                  <button type="button" className="btn btn-primary btn-sm" disabled={imp.running} onClick={() => void imp.start()}>
                    <Download aria-hidden />
                    가져오기
                  </button>
                  <button type="button" className="btn btn-sm" onClick={() => navigateQuery({ tab: "courses", new: "course" }, "push")}>
                    직접 입력
                  </button>
                </>
              }
            >
              들은 과목을 읽어 영역별로 남은 학점을 계산합니다. 로그인 정보는 이 PC 를 떠나지 않습니다.
            </EmptyState>
          )}
          {rs.level === "none" && d.profileMissing.length === 0 ? (
            <NoRuleset d={d} />
          ) : (
            <>
              <SummaryCard d={d} tone={verdictTone} />
              <AreaList areas={d.areas} />
              {d.checks.length > 0 && <CheckList d={d} />}
              <CertList certs={d.certifications} onSet={g.setCert} />
              <Basis d={d} />
            </>
          )}
        </div>
      )}

      {tab === "courses" && <CourseTable d={d} g={g} imp={imp} track={track} />}
      {tab === "whatif" && <WhatIf d={d} track={track} />}

      <Modal open={!!area} onClose={() => closeQuery(["area"])} title={area ? `${area.label}에 들어간 과목` : ""} size="md">
        {area && <AreaDetail a={area} areas={d.areas} />}
      </Modal>
      <AddCourseModal open={newCourse} d={d} onAdd={g.addCourse} />
    </Page>
  );
}

/* ------------------------------------------------------------------ 배너 */

function ImportProblemBanner({ imp }: { imp: ReturnType<typeof useGradImport> }) {
  if (!imp.problem) return null;
  return (
    <Banner
      tone={imp.problem.needLogin ? "warn" : "danger"}
      action={
        imp.problem.needLogin && (
          <button type="button" className="btn btn-sm" disabled={imp.running} onClick={() => void imp.start(true)}>
            <LogIn aria-hidden />
            로그인 창 열기
          </button>
        )
      }
    >
      {imp.problem.message}
    </Banner>
  );
}

/** 과목 목록(교육과정)을 아직 받지 않았으면 — 전공필수 '남은 과목'을 알 수 없다 */
function CurriculumBanner({ d, reload }: { d: GraduationStatus; reload: () => Promise<void> }) {
  const toast = useToast();
  const [running, setRunning] = useState(false);
  const missing = d.ruleset.curriculum?.missing ?? [];
  if (!missing.length || d.ruleset.level === "none") return null;
  const start = async () => {
    setRunning(true);
    try {
      let st: CurriculumState["sync"] = await api.syncCurriculum();
      if (st.error && !st.running) throw new Error(st.error);
      for (let i = 0; i < 60 && st.running; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        st = (await api.curriculum()).sync;
      }
      if (st.ok) {
        await reload();
        toast("교육과정을 받았습니다 — 남은 과목을 다시 계산했습니다", { tone: "success" });
      } else toast(`교육과정을 받지 못했습니다: ${st.error ?? "알 수 없는 오류"}`, { tone: "error" });
    } catch (e) {
      toast(`교육과정을 받지 못했습니다: ${e instanceof Error ? e.message : String(e)}`, { tone: "error" });
    } finally {
      setRunning(false);
    }
  };
  return (
    <Banner
      tone="info"
      action={
        <button type="button" className="btn btn-sm" disabled={running} onClick={() => void start()}>
          {running ? <span className="spin spin-dark" aria-hidden /> : <Download aria-hidden />}
          교육과정 받기
        </button>
      }
    >
      {d.ruleset.curriculum?.year}학년도 교육과정(전공필수 과목 목록)을 아직 받지 않았습니다 — 받으면 남은 과목을 이름으로 알려 드립니다
    </Banner>
  );
}

function NoRuleset({ d }: { d: GraduationStatus }) {
  const who = [d.profile.department, d.profile.major].filter(Boolean).join(" ");
  return (
    <EmptyState
      icon={<CircleHelp />}
      title={`${who} ${d.profile.admissionYear ?? ""} 기준이 아직 없습니다`}
      action={
        <>
          <Link href="/settings/requirements" className="btn btn-primary btn-sm">
            직접 입력하기
          </Link>
          <Link href="/settings/requirements?copy=1" className="btn btn-sm">
            비슷한 학과에서 복사
          </Link>
        </>
      }
    >
      학과 홈페이지의 &lsquo;졸업소요학점&rsquo; 표를 보고 직접 입력하면 바로 계산됩니다. 지금은 총 취득학점 {num(d.total.earned)}학점만 셉니다.
    </EmptyState>
  );
}

/* ------------------------------------------------------------------ 요약 */

function SummaryCard({ d, tone }: { d: GraduationStatus; tone: "ok" | "accent" | "warn" }) {
  const t = d.total;
  const g = d.gpa;
  const pct = t.required ? Math.round((t.earned / t.required) * 100) : null;
  const reasons = [...d.reasons.doubts, ...d.reasons.shorts, ...d.reasons.unknowns];
  return (
    <Section>
      <div className="flex flex-col items-center gap-6 md:flex-row">
        <Donut value={t.earned} max={t.required ?? Math.max(1, t.earned)} size={148}>
          <span className="num text-[28px] font-bold">{pct === null ? "—" : `${pct}%`}</span>
          <span className="num text-[13px] text-muted">
            {num(t.earned)}/{num(t.required)}
          </span>
        </Donut>
        <div className="flex-1 text-center md:text-left">
          <p className="text-[14px] text-muted">졸업까지</p>
          <p className="num text-[36px] leading-tight font-bold">{t.remaining === null ? "—" : `${num(t.remaining)} 학점`}</p>
          {d.headline && <p className="mt-1 text-[14px] text-muted">{d.headline}</p>}
          {t.short !== null && t.short > 0 && t.areaShort > 0 && t.short !== t.areaShort && (
            <p className="mt-1 text-[12px] text-faint">
              총 학점 기준 {num(t.short)}학점 · 영역 기준 {num(t.areaShort)}학점 — 더 큰 쪽을 들어야 합니다
            </p>
          )}
          <p className="mt-1 text-[14px]">
            평점 <b className="num">{g.current ? `${g.current.value.toFixed(2)} / ${g.current.scale}` : "—"}</b>
            {g.required ? (
              <>
                {" "}
                / 최저 {g.required.value}{" "}
                {g.ok === true ? (
                  <CircleCheck className="inline size-4 text-ok" aria-label="충족" />
                ) : g.ok === false ? (
                  <CircleX className="inline size-4 text-danger" aria-label="미달" />
                ) : (
                  <CircleHelp className="inline size-4 text-warn" aria-label="확인 필요" />
                )}
              </>
            ) : null}
            {g.note && <span className="ml-2 text-[12px] text-faint">{g.note}</span>}
          </p>
        </div>
        <div className="text-center">
          <p className="mb-1 text-[13px] text-muted">판정</p>
          <StatusBadge tone={tone} unknown={d.verdict === "확인 필요"}>
            {d.verdict}
          </StatusBadge>
        </div>
      </div>
      {reasons.length > 0 && (
        <details className="mt-4 border-t border-border pt-3">
          <summary className="cursor-pointer text-[13px] font-semibold text-muted">판정 근거 {reasons.length}가지</summary>
          <ul className="mt-2 space-y-1 text-[13px]">
            {d.reasons.doubts.map((r) => (
              <li key={`d${r}`} className="text-warn-text">
                ⚠ {r}
              </li>
            ))}
            {d.reasons.shorts.map((r) => (
              <li key={`s${r}`} className="text-accent-text">
                ● 부족 — {r}
              </li>
            ))}
            {d.reasons.unknowns.map((r) => (
              <li key={`u${r}`} className="text-muted">
                ? {r}
              </li>
            ))}
          </ul>
        </details>
      )}
    </Section>
  );
}

function AreaList({ areas }: { areas: GradArea[] }) {
  return (
    <Section title="영역별">
      <ul className="divide-y divide-border">
        {areas.map((a) => {
          const free = a.required === 0;
          return (
            <li key={a.key}>
              <button
                type="button"
                className="grid w-full grid-cols-[88px_1fr_auto] items-center gap-3 py-3 text-left hover:bg-surface-2 md:grid-cols-[100px_1fr_120px_190px_20px] md:px-2"
                onClick={() => navigateQuery({ area: a.key }, "push")}
              >
                <span className="text-[14px] font-semibold">{a.label}</span>
                <ProgressBar value={a.earned} max={free ? Math.max(1, a.earned) : a.required} tone={a.ok ? "ok" : "primary"} label={`${a.label} ${a.earned}/${a.required}`} />
                <span className="num text-right text-[14px]">{free ? `${num(a.earned)}학점` : `${num(a.earned)}/${num(a.required)}`}</span>
                <span className="hidden text-[13px] md:block">
                  {free ? (
                    <span className="text-muted">나머지 학점</span>
                  ) : a.ok ? (
                    <StatusBadge tone="ok">충족</StatusBadge>
                  ) : (
                    <span className="text-accent-text">
                      {a.short > 0 && `부족 ${num(a.short)}`}
                      {a.missingCourses.length > 0 && `${a.short > 0 ? " · " : ""}남은 과목 ${a.missingCourses.length}`}
                    </span>
                  )}
                  {a.listUnknown && (
                    <Chip square className="ml-1">
                      과목 목록 모름
                    </Chip>
                  )}
                  {a.outflow > 0 && <span className="ml-1 text-[12px] text-faint">(초과 {num(a.outflow)} 이월)</span>}
                </span>
                <ChevronRight className="hidden size-4 text-faint md:block" aria-hidden />
              </button>
            </li>
          );
        })}
      </ul>
    </Section>
  );
}

function AreaDetail({ a, areas }: { a: GradArea; areas: GradArea[] }) {
  const label = (k: string | null) => areas.find((x) => x.key === k)?.label ?? k;
  const from = areas.filter((x) => x.overflowTo === a.key && x.outflow > 0);
  return (
    <div className="space-y-4 pt-1">
      <p className="text-[14px]">
        <b className="num">{num(a.earned)}</b>
        {a.required > 0 && <span className="text-muted"> / 기준 {num(a.required)}학점</span>}
        {a.short > 0 && <span className="ml-2 text-accent-text">부족 {num(a.short)}</span>}
      </p>
      {(a.outflow > 0 || from.length > 0) && (
        <p className="rounded-lg bg-surface-2 px-3 py-2 text-[13px] text-muted">
          {a.outflow > 0 && `기준을 넘은 ${num(a.outflow)}학점은 ${label(a.overflowTo)}으로 인정했습니다. `}
          {from.map((x) => `${x.label}에서 넘어온 ${num(x.outflow)}학점을 더했습니다. `)}
        </p>
      )}
      <div>
        <p className="label">들어간 과목 {a.courses.length}</p>
        {a.courses.length ? (
          <ul className="space-y-1">
            {a.courses.map((c) => (
              <li key={c.id} className="flex items-center gap-2 rounded-lg bg-surface-2 px-3 py-2 text-[14px]">
                <span className="min-w-0 flex-1 truncate">{c.name}</span>
                <span className="num text-[12px] text-muted">
                  {c.year}-{c.semester} · {c.grade ?? "-"} · {num(c.credits)}학점
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[13px] text-muted">아직 없습니다</p>
        )}
      </div>
      {a.requiredCourses.length > 0 && (
        <div>
          <p className="label">
            반드시 들을 과목 — 남은 {a.missingCourses.length} / {a.requiredCourses.length}
            {a.coursesSource === "curriculum" && <span className="ml-1 font-normal text-faint">(교육과정검색)</span>}
          </p>
          <ul className="grid gap-1 sm:grid-cols-2">
            {a.requiredCourses.map((c) => (
              <li key={c.code ?? c.name} className={`flex items-center gap-2 rounded-lg px-3 py-1.5 text-[13px] ${c.done ? "text-muted" : "bg-accent-soft/60 font-semibold"}`}>
                {c.done ? <CircleCheck className="size-4 flex-none text-ok" aria-label="이수" /> : <CircleX className="size-4 flex-none text-accent-text" aria-label="남음" />}
                <span className="min-w-0 flex-1 truncate">{c.name}</span>
                <span className="num text-[11px] text-faint">
                  {c.grade ? `${c.grade}-${c.term} · ` : ""}
                  {num(c.credits)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {a.evidence && <p className="text-[12px] text-muted">근거: {a.evidence}</p>}
    </div>
  );
}

function CheckList({ d }: { d: GraduationStatus }) {
  return (
    <Section title="교양 영역 조건" action={<span className="text-[12px] text-faint">대학 공통 · 교양영역 칸으로 셉니다</span>}>
      <ul className="divide-y divide-border">
        {d.checks.map((c) => (
          <li key={c.key} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2.5">
            <span className="w-40 text-[14px] font-semibold">{c.label}</span>
            <span className="num text-[14px]">
              {num(c.earned)}/{num(c.required)}
            </span>
            <span className="ml-auto">
              {c.state === "ok" ? (
                <StatusBadge tone="ok">충족</StatusBadge>
              ) : c.state === "short" ? (
                <StatusBadge tone="accent">부족 {num(c.short)}</StatusBadge>
              ) : (
                <StatusBadge tone="warn" unknown>
                  확인 필요
                </StatusBadge>
              )}
            </span>
            {c.state === "unknown" && (
              <p className="w-full text-[12px] text-faint">
                {c.approximate ? "이 영역 과목을 넉넉히 세었습니다 — 인정 과목인지 학과에 확인하세요" : "교양영역 정보가 없어 모자란지 알 수 없습니다 — 이수 내역을 다시 가져오세요"}
              </p>
            )}
          </li>
        ))}
      </ul>
    </Section>
  );
}

const CERT_ICON: Record<CertState, React.ReactNode> = {
  done: <CircleCheck className="size-4 text-ok" aria-hidden />,
  todo: <CircleX className="size-4 text-danger" aria-hidden />,
  unknown: <CircleHelp className="size-4 text-faint" aria-hidden />,
};

function CertList({ certs, onSet }: { certs: GradCert[]; onSet: (key: string, body: { state?: CertState; memo?: string }) => Promise<void> }) {
  if (!certs.length)
    return (
      <Section title="졸업인증">
        <p className="text-[14px] text-muted">이 기준에는 졸업인증 항목이 없습니다. 있으면 기준 보기에서 더하세요.</p>
      </Section>
    );
  return (
    <Section title="졸업인증" action={<span className="text-[12px] text-faint">학교 시스템에서 못 읽습니다 — 직접 확인해 표시하세요</span>}>
      <ul className="divide-y divide-border">
        {certs.map((c) => (
          <li key={c.key} className={`py-3 ${c.state === "todo" ? "text-danger-text" : ""}`}>
            <div className="flex flex-wrap items-center gap-3">
              <span className="flex items-center gap-2 text-[14px] font-semibold text-text">
                {CERT_ICON[c.state]}
                {c.label}
                {!c.required && <Chip square>선택</Chip>}
              </span>
              <div role="radiogroup" aria-label={`${c.label} 충족 여부`} className="ml-auto inline-flex overflow-hidden rounded-lg border border-border">
                {(["done", "todo", "unknown"] as const).map((s) => (
                  <button
                    key={s}
                    type="button"
                    role="radio"
                    aria-checked={c.state === s}
                    className={`h-8 px-3 text-[13px] font-semibold ${c.state === s ? (s === "done" ? "bg-ok-soft text-ok-text" : s === "todo" ? "bg-danger-soft text-danger-text" : "bg-surface-3 text-text") : "bg-surface text-muted hover:bg-surface-2"}`}
                    onClick={() => void onSet(c.key, { state: s })}
                  >
                    {CERT_LABEL[s]}
                  </button>
                ))}
              </div>
            </div>
            {c.detail && <p className="mt-1 text-[13px] text-muted">{c.detail}</p>}
            {c.hintFound.length > 0 && c.state !== "done" && (
              <p className="mt-1 text-[12px] text-primary">이수 과목에 &lsquo;{c.hintFound.join("·")}&rsquo;이(가) 있습니다 — 확인되면 충족으로 표시하세요</p>
            )}
            <input
              key={c.memo}
              className="field field-sm mt-2"
              aria-label={`${c.label} 메모`}
              placeholder="점수·시간·취득일 (예: TOEIC 780, 2025-04)"
              defaultValue={c.memo}
              maxLength={300}
              onBlur={(e) => {
                const v = e.target.value.trim();
                if (v !== c.memo) void onSet(c.key, { memo: v });
              }}
            />
          </li>
        ))}
      </ul>
    </Section>
  );
}

function Basis({ d }: { d: GraduationStatus }) {
  const rs = d.ruleset;
  return (
    <details className="card p-4 text-[13px] md:p-5">
      <summary className="cursor-pointer font-semibold text-muted">기준 근거와 메모</summary>
      <ul className="mt-3 space-y-1.5 text-muted">
        {rs.source?.url && (
          <li>
            졸업소요학점·인증:{" "}
            <a href={rs.source.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-primary hover:underline">
              {rs.source.docName}
              <ExternalLink className="size-3" aria-hidden />
            </a>
            {rs.source.checkedAt && <span className="text-faint"> · {rs.source.checkedAt} 확인</span>}
          </li>
        )}
        {rs.totalEvidence && <li>졸업 학점: {rs.totalEvidence}</li>}
        {rs.minGpaEvidence && <li>최저 평점: {rs.minGpaEvidence}</li>}
        {rs.commonSources.map((c) => (
          <li key={c.id}>
            대학 공통:{" "}
            <a href={c.url} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
              {c.docName}
            </a>
          </li>
        ))}
        {rs.curriculum?.sources.map((s) => (
          <li key={s.code}>
            과목 목록: 교육과정검색 {s.code} · {s.year}학년도 {s.origin === "bundled" ? "(기본 스냅숏)" : "(내려받음)"}
          </li>
        ))}
        {rs.notes.map((n) => (
          <li key={n}>· {n}</li>
        ))}
      </ul>
    </details>
  );
}

/* ------------------------------------------------------------------ 이수 과목 탭 */

function CourseTable({ d, g, imp, track }: { d: GraduationStatus; g: G; imp: ReturnType<typeof useGradImport>; track: Track }) {
  const toast = useToast();
  const [filter, setFilter] = useQueryParam("filter", "all", FILTERS);
  const areaLabel = (k: string | null) => d.ruleset.areas.find((a) => a.key === k)?.label ?? k ?? "미분류";
  const isUnmapped = (c: GradCourseRow) => c.area === null && !c.excluded;
  const shown = d.courses.filter((c) => (filter === "unmapped" ? isUnmapped(c) : filter === "manual" ? c.source === "manual" : true));
  const terms = useMemo(() => {
    const m = new Map<string, GradCourseRow[]>();
    for (const c of shown) m.set(termKey(c), [...(m.get(termKey(c)) ?? []), c]);
    return [...m.entries()].sort(([a], [b]) => termSort(a, b));
  }, [shown]);

  const changeArea = async (c: GradCourseRow, v: string) => {
    if (!v) {
      await g.patchCourse(c.id, { area: null });
      return;
    }
    const toCategory = c.areaSetBy === "none" && !!c.rawCategory;
    const r = await g.patchCourse(c.id, { area: v, applyToCategory: toCategory });
    if (r?.mapped) toast(`앞으로 '${r.mapped.raw}' 과목은 자동으로 ${areaLabel(r.mapped.area)}(으)로 분류합니다`, { tone: "success" });
    else if (r) toast("구분을 바꿨습니다 — 요약 숫자를 다시 계산했습니다");
  };

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Tabs
          variant="pill"
          size="sm"
          label="과목 필터"
          value={filter}
          onChange={(f) => setFilter(f)}
          items={[
            { key: "all", label: "전체" },
            { key: "unmapped", label: "미분류", count: d.courses.filter(isUnmapped).length },
            { key: "manual", label: "직접 입력", count: d.data.manualCount },
          ]}
        />
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <span className="num text-[12px] text-muted">
            {d.data.importedAt ? `가져온 시각 ${fmtShortStamp(d.data.importedAt)} (${fmtRelative(d.data.importedAt)}) · ${d.data.hakstdCount}과목` : "아직 가져오지 않음"}
          </span>
          <button type="button" className="btn btn-sm" disabled={imp.running} onClick={() => void imp.start()}>
            {imp.running ? <span className="spin spin-dark" aria-hidden /> : <Download aria-hidden />}
            이수 내역 가져오기
          </button>
          <button type="button" className="btn btn-primary btn-sm" onClick={() => navigateQuery({ new: "course" }, "push")}>
            <Plus aria-hidden />
            과목 추가
          </button>
        </div>
      </div>
      <div className="space-y-5">
        {terms.map(([k, list]) => (
          <section key={k}>
            <h3 className="num mb-2 text-[13px] font-bold text-muted">
              {termLabel(k)} <span className="font-normal">· {num(list.filter((c) => !c.excluded).reduce((s, c) => s + c.credits, 0))}학점</span>
            </h3>
            <div className="overflow-hidden rounded-xl border border-border bg-surface">
              <table className="w-full text-[14px]">
                <thead className="bg-surface-2 text-left text-[12px] text-muted max-md:hidden">
                  <tr>
                    <th className="px-4 py-2 font-semibold">과목</th>
                    <th className="w-16 px-2 py-2 font-semibold">학점</th>
                    <th className="w-14 px-2 py-2 font-semibold">성적</th>
                    <th className="w-48 px-2 py-2 font-semibold">구분 → 영역</th>
                    <th className="w-24" />
                  </tr>
                </thead>
                <tbody>
                  {list.map((c) => (
                    <tr
                      key={c.id}
                      className={`border-t border-border first:border-t-0 max-md:flex max-md:flex-wrap max-md:items-center max-md:gap-2 max-md:px-4 max-md:py-2 ${
                        isUnmapped(c) ? "bg-warn-soft/50" : ""
                      } ${c.excluded ? "text-muted" : ""}`}
                    >
                      <td className="px-4 py-2 max-md:w-full max-md:p-0">
                        <span className={`font-medium ${c.excluded ? "line-through" : ""}`}>{c.name}</span>
                        {c.code && <span className="num ml-2 text-[11px] text-faint">{c.code}</span>}
                        {c.source === "manual" && (
                          <Chip tone="primary" square className="ml-2">
                            직접 입력
                          </Chip>
                        )}
                        {c.excludedReason && <span className="block text-[12px] text-danger-text">계산 제외 — {c.excludedReason}</span>}
                        {c.memo && <span className="block text-[12px] text-faint">{c.memo}</span>}
                      </td>
                      <td className="num px-2 py-2 max-md:p-0">{num(c.credits)}학점</td>
                      <td className="num px-2 py-2 max-md:p-0">{c.grade ?? "-"}</td>
                      <td className="px-2 py-2 max-md:p-0">
                        <div className="flex items-center gap-1.5">
                          {c.rawCategory && (
                            <code className="rounded bg-surface-3 px-1.5 text-[12px] font-semibold" title="학사시스템 교과구분">
                              {c.rawCategory}
                            </code>
                          )}
                          <label className="sr-only" htmlFor={`area-${c.id}`}>
                            {c.name} 영역
                          </label>
                          <select
                            id={`area-${c.id}`}
                            className="field field-sm min-w-0 flex-1"
                            value={c.areaSetBy === "user" ? (c.area ?? "") : ""}
                            aria-invalid={isUnmapped(c)}
                            disabled={c.excluded && !c.excludedByUser}
                            onChange={(e) => void changeArea(c, e.target.value)}
                          >
                            <option value="">{c.areaSetBy === "map" ? `구분대로 · ${areaLabel(c.area)}` : c.areaSetBy === "user" ? "구분대로" : "미분류"}</option>
                            {d.ruleset.areas.map((a) => (
                              <option key={a.key} value={a.key}>
                                {a.label}
                              </option>
                            ))}
                          </select>
                        </div>
                      </td>
                      <td className="px-2 py-2 text-right max-md:ml-auto max-md:p-0">
                        {c.source === "manual" ? (
                          <button
                            type="button"
                            className="btn btn-ghost btn-icon btn-sm"
                            aria-label={`${c.name} 삭제`}
                            onClick={async () => {
                              if (await g.deleteCourse(c.id)) toast(`'${c.name}'을(를) 지웠습니다`);
                            }}
                          >
                            <Trash2 aria-hidden />
                          </button>
                        ) : (
                          (!c.excluded || c.excludedByUser) && (
                            <button
                              type="button"
                              className="btn btn-ghost btn-sm"
                              title={c.excludedByUser ? "다시 계산에 넣기" : "계산에서 빼기 — 원본은 학사시스템이라 지우지 않습니다"}
                              onClick={() => void g.patchCourse(c.id, { excluded: !c.excludedByUser })}
                            >
                              {c.excludedByUser ? <Undo2 aria-hidden /> : <CircleX aria-hidden />}
                              {c.excludedByUser ? "넣기" : "빼기"}
                            </button>
                          )
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ))}
        {terms.length === 0 && (
          <p className="rounded-xl border border-dashed border-border-strong px-4 py-8 text-center text-[14px] text-muted">
            {filter === "all" ? "아직 이수 과목이 없습니다 — 가져오거나 직접 추가하세요" : "해당하는 과목이 없습니다"}
          </p>
        )}
      </div>
      <p className="mt-3 text-[12px] text-faint">
        F·NP·W 와 포기 과목은 자동으로 빠지고, 재수강 과목은 성적이 가장 높은 1건만 셉니다. {TRACK_LABEL[track]} 기준으로 분류했습니다.
      </p>
    </div>
  );
}

function AddCourseModal({ open, d, onAdd }: { open: boolean; d: GraduationStatus; onAdd: G["addCourse"] }) {
  const toast = useToast();
  const now = new Date().getFullYear();
  const [f, setF] = useState({ name: "", credits: 3, year: now, semester: "1", grade: "P", code: "", area: "free", memo: "" });
  const [saving, setSaving] = useState(false);
  const close = () => closeQuery(["new"]);
  const set = (k: keyof typeof f, v: string | number) => setF((x) => ({ ...x, [k]: v }));
  const submit = async () => {
    setSaving(true);
    const id = await onAdd({
      name: f.name.trim(),
      credits: Number(f.credits),
      year: Number(f.year) || null,
      semester: f.semester,
      grade: f.grade.trim() || null,
      code: f.code.trim() || null,
      area: f.area,
      memo: f.memo.trim(),
    });
    setSaving(false);
    if (id) {
      toast(`'${f.name.trim()}'을(를) 더했습니다 — 다시 가져와도 남습니다`, { tone: "success" });
      setF((x) => ({ ...x, name: "", code: "", memo: "" }));
      close();
    }
  };
  return (
    <Modal
      open={open}
      onClose={close}
      title="과목 추가"
      footer={
        <>
          <button type="button" className="btn" onClick={close}>
            취소
          </button>
          <button type="button" className="btn btn-primary" disabled={!f.name.trim() || saving || !(Number(f.credits) >= 0)} onClick={() => void submit()}>
            추가
          </button>
        </>
      }
    >
      <div className="space-y-4 pt-1">
        <p className="text-[13px] text-muted">학사시스템에 안 잡힌 것(타대 학점인정·편입·누락된 계절학기)만 더하세요. 직접 입력한 과목은 다시 가져와도 남습니다.</p>
        <div>
          <label className="label" htmlFor="cn">
            과목명
          </label>
          <input id="cn" data-autofocus className="field" value={f.name} onChange={(e) => set("name", e.target.value)} placeholder="예) 편입 인정 학점, 교내 AI 캠프(학점인정)" maxLength={80} />
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div>
            <label className="label" htmlFor="cy">
              년도
            </label>
            <input id="cy" type="number" min={1990} max={2100} className="field num" value={f.year} onChange={(e) => set("year", Number(e.target.value))} />
          </div>
          <div>
            <label className="label" htmlFor="cs">
              학기
            </label>
            <select id="cs" className="field" value={f.semester} onChange={(e) => set("semester", e.target.value)}>
              {SEMESTER_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="cc">
              학점
            </label>
            <input id="cc" type="number" min={0} max={30} step={0.5} className="field num" value={f.credits} onChange={(e) => set("credits", Number(e.target.value))} />
          </div>
          <div>
            <label className="label" htmlFor="cg">
              성적
            </label>
            <input id="cg" className="field" value={f.grade} onChange={(e) => set("grade", e.target.value)} placeholder="A+ · P" maxLength={5} />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label" htmlFor="ca">
              영역
            </label>
            <select id="ca" className="field" value={f.area} onChange={(e) => set("area", e.target.value)}>
              {d.ruleset.areas.map((a) => (
                <option key={a.key} value={a.key}>
                  {a.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="ck">
              학수번호 <span className="font-normal text-faint">(선택)</span>
            </label>
            <input id="ck" className="field num" value={f.code} onChange={(e) => set("code", e.target.value)} placeholder="CIS3001" maxLength={20} />
          </div>
        </div>
        <p className="hint">전공필수 과목이면 학수번호를 넣어야 &lsquo;남은 과목&rsquo;에서 빠집니다.</p>
        <div>
          <label className="label" htmlFor="cm">
            메모 <span className="font-normal text-faint">(선택)</span>
          </label>
          <input id="cm" className="field" value={f.memo} onChange={(e) => set("memo", e.target.value)} placeholder="예) 2024 편입 인정" maxLength={300} />
        </div>
      </div>
    </Modal>
  );
}

/* ------------------------------------------------------------------ 가정 계산 탭 */

const EMPTY: Assumptions = { areas: {}, courses: [] };

function WhatIf({ d, track }: { d: GraduationStatus; track: Track }) {
  const toast = useToast();
  const planId = useQueryValue("plan");
  const [a, setA] = useState<Assumptions>(EMPTY);
  const [res, setRes] = useState<{ current: SimSide; assumed: SimSide } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [name, setName] = useState("");
  const loadedPlan = useRef<string | null>(null);

  useEffect(() => {
    void api
      .plans()
      .then(setPlans)
      .catch(() => {});
  }, []);

  // ?plan=<id> 로 들어오면 그 계획을 불러온다 (F2-R53)
  useEffect(() => {
    if (!planId || loadedPlan.current === planId) return;
    const p = plans.find((x) => x.id === planId);
    if (p) {
      loadedPlan.current = planId;
      void Promise.resolve().then(() => setA({ areas: { ...p.assumptions.areas }, courses: [...p.assumptions.courses] }));
    }
  }, [planId, plans]);

  // 입력 즉시(200ms 디바운스) 백엔드 계산기로 — 화면은 계산하지 않는다 (Frontend-Route 7-5)
  useEffect(() => {
    const t = window.setTimeout(async () => {
      try {
        const r = await api.simulate(track, a);
        setRes({ current: r.current, assumed: r.assumed });
        setErr(null);
      } catch (e) {
        setErr(e instanceof Error ? e.message : String(e));
      }
    }, 200);
    return () => window.clearTimeout(t);
  }, [a, track, d.updatedAt]);

  const missing = d.areas.flatMap((ar) => ar.missingCourses.map((c) => ({ ...c, area: ar.label })));
  const toggle = (code: string) =>
    setA((x) => ({ ...x, courses: x.courses.includes(code) ? x.courses.filter((c) => c !== code) : [...x.courses, code] }));

  const save = async () => {
    try {
      const p = await api.savePlan({ name: name.trim() || "내 계획", track, assumptions: a });
      setPlans((xs) => [p, ...xs]);
      loadedPlan.current = p.id;
      navigateQuery({ plan: p.id }, "replace");
      setName("");
      toast(`'${p.name}'으로 저장했습니다`, { tone: "success" });
    } catch (e) {
      toast(`저장하지 못했습니다: ${e instanceof Error ? e.message : String(e)}`, { tone: "error" });
    }
  };

  const row = (label: string, cur: React.ReactNode, next: React.ReactNode, changed: boolean) => (
    <tr key={label}>
      <th className="py-2 text-left font-medium text-muted">{label}</th>
      <td className="num py-2">{cur}</td>
      <td className={`num py-2 ${changed ? "font-bold text-primary" : ""}`}>{next}</td>
    </tr>
  );

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="space-y-4">
        <Section title="가정을 넣어 보세요" action={<span className="text-[12px] text-faint">과목을 추천하지는 않습니다</span>}>
          <ul className="space-y-3">
            {d.areas.map((ar) => (
              <li key={ar.key} className="flex items-center gap-3">
                <span className="w-20 text-[14px] font-semibold">{ar.label}</span>
                <span className="text-[14px] text-muted">+</span>
                <input
                  type="number"
                  min={0}
                  max={60}
                  aria-label={`${ar.label} 가정 학점`}
                  className="field field-sm num w-20"
                  value={a.areas[ar.key] ?? ""}
                  placeholder="0"
                  onChange={(e) => {
                    const v = Math.max(0, Math.min(60, Number(e.target.value) || 0));
                    setA((x) => ({ ...x, areas: { ...x.areas, [ar.key]: v } }));
                  }}
                />
                <span className="text-[14px] text-muted">학점</span>
                {ar.short > 0 && <span className="text-[12px] text-faint">부족 {num(ar.short)}</span>}
              </li>
            ))}
          </ul>
          {missing.length > 0 && (
            <div className="mt-4 border-t border-border pt-3">
              <p className="label">남은 과목을 들으면</p>
              <ul className="grid gap-1 sm:grid-cols-2">
                {missing.map((c) => {
                  const k = c.code ?? c.name;
                  return (
                    <li key={k}>
                      <label className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-[13px] hover:bg-surface-2">
                        <input type="checkbox" checked={a.courses.includes(k)} onChange={() => toggle(k)} />
                        <span className="min-w-0 flex-1 truncate">{c.name}</span>
                        <span className="text-[11px] text-faint">
                          {c.area} · {num(c.credits)}
                        </span>
                      </label>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </Section>
        {plans.length > 0 && (
          <Section title="내 계획">
            <ul className="space-y-1">
              {plans.map((p) => (
                <li key={p.id} className={`flex items-center gap-2 rounded-lg px-2 py-1.5 text-[14px] ${planId === p.id ? "bg-primary-soft" : ""}`}>
                  <button
                    type="button"
                    className="min-w-0 flex-1 truncate text-left font-semibold hover:underline"
                    onClick={() => {
                      loadedPlan.current = p.id;
                      setA({ areas: { ...p.assumptions.areas }, courses: [...p.assumptions.courses] });
                      navigateQuery({ plan: p.id }, "replace");
                    }}
                  >
                    {p.name}
                  </button>
                  <span className="text-[12px] text-faint">{fmtShortStamp(p.createdAt)}</span>
                  <button
                    type="button"
                    className="btn btn-ghost btn-icon btn-sm"
                    aria-label={`${p.name} 삭제`}
                    onClick={async () => {
                      await api.deletePlan(p.id).catch(() => {});
                      setPlans((xs) => xs.filter((x) => x.id !== p.id));
                      if (planId === p.id) navigateQuery({ plan: null }, "replace");
                    }}
                  >
                    <Trash2 aria-hidden />
                  </button>
                </li>
              ))}
            </ul>
          </Section>
        )}
      </div>
      <Section title="현재 → 가정 후" action={<Chip square>백엔드 계산</Chip>}>
        {err && <Banner tone="danger">{err}</Banner>}
        {res ? (
          <table className="w-full text-[14px]">
            <thead className="text-left text-[12px] text-muted">
              <tr>
                <th className="py-1 font-semibold" />
                <th className="py-1 font-semibold">현재</th>
                <th className="py-1 font-semibold">가정 후</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {row(
                "총 학점",
                `${num(res.current.total.earned)}/${num(res.current.total.required)}`,
                `${num(res.assumed.total.earned)}/${num(res.assumed.total.required)}`,
                res.current.total.earned !== res.assumed.total.earned,
              )}
              {row("남은 학점", num(res.current.total.remaining), num(res.assumed.total.remaining), res.current.total.remaining !== res.assumed.total.remaining)}
              {res.current.areas.map((ca, i) => {
                const aa = res.assumed.areas[i];
                const txt = (x: typeof ca) => (x.ok ? "충족 ✓" : [x.short > 0 ? `부족 ${num(x.short)}` : "", x.missing.length ? `${x.missing.length}과목 남음` : ""].filter(Boolean).join(" · ") || "—");
                return row(ca.label, txt(ca), txt(aa), txt(ca) !== txt(aa));
              })}
              {row("판정", res.current.verdict, res.assumed.verdict, res.current.verdict !== res.assumed.verdict)}
            </tbody>
          </table>
        ) : (
          <p className="text-[14px] text-muted">계산 중…</p>
        )}
        <p className="hint">가정은 저장하지 않으면 탭을 떠날 때 사라집니다.</p>
        <div className="mt-4 flex flex-wrap items-center justify-end gap-2">
          <button
            type="button"
            className="btn btn-sm"
            onClick={() => {
              setA(EMPTY);
              navigateQuery({ plan: null }, "replace");
            }}
          >
            <RotateCcw aria-hidden />
            초기화
          </button>
          <input className="field field-sm w-36" aria-label="계획 이름" placeholder="계획 이름" value={name} onChange={(e) => setName(e.target.value)} maxLength={40} />
          <button type="button" className="btn btn-primary btn-sm" disabled={!Object.values(a.areas).some(Boolean) && !a.courses.length} onClick={() => void save()}>
            <Save aria-hidden />내 계획으로 저장
          </button>
        </div>
      </Section>
    </div>
  );
}
