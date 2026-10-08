"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ChevronDown, Download, LogIn, Plus, Settings } from "lucide-react";
import { Page, PageHeader, Section, Toggle } from "@/components/ui/Layout";
import { Banner, DemoNotice, ErrorPanel } from "@/components/ui/Feedback";
import { Chip, StatusBadge, type Tone } from "@/components/ui/Chip";
import { Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { useAppData } from "@/components/app/AppData";
import { DeptPicker } from "@/components/profile/DeptPicker";
import { useProfile, useProfileImport } from "@/lib/useProfile";
import { useStored } from "@/lib/storage";
import { closeQuery, navigateQuery, useQueryValue } from "@/lib/useQueryState";
import { SETTINGS } from "@/lib/features";
import { demoBoards, demoSources, type SourceRow } from "@/lib/demo";
import { EclassSourceSection } from "@/components/assignments/EclassSource";
import type { FeedSettings, ReminderSettings } from "@/lib/assignments";
import { RequirementsEditor } from "@/components/graduation/RequirementsEditor";
import { useGradImport } from "@/lib/useGraduation";
import { ENROLLMENT, FIELD_LABEL, FLAG_LABEL, INCOME_BRACKETS, REGIONS, TRACK_LABEL, type Enrollment, type Track } from "@/lib/profile";
import { api } from "@/lib/api";
import { AcademicSourcesSection } from "@/components/academic/AcademicSources";
import { addDays, fmtRelative, fmtShortStamp, toDateStr } from "@/lib/dates";
import type { AvailabilitySettings as Avail, AvailabilityView } from "@/lib/placement";
import type { ExamSettings } from "@/lib/exams";

// 설정 5개 — 설정 허브 페이지는 만들지 않는다(헤더 ⚙ 드롭다운이 입구). 페이지 사이는 위쪽 링크로 옮겨 다닌다.

function SettingsShell({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  const path = usePathname();
  return (
    <Page>
      <PageHeader icon={<Settings />} title={title} subtitle={subtitle} />
      <nav aria-label="설정" className="no-scrollbar -mt-2 mb-6 flex gap-1 overflow-x-auto border-b border-border">
        {SETTINGS.map((s) => {
          const on = path?.replace(/\/$/, "") === s.href;
          return (
            <Link
              key={s.href}
              href={s.href}
              aria-current={on ? "page" : undefined}
              className={`relative flex h-10 flex-none items-center px-3 text-[14px] font-semibold ${on ? "text-text" : "text-muted hover:text-text"}`}
            >
              {s.label}
              {on && <motion.span layoutId="settings-tab" className="absolute inset-x-2 bottom-0 h-0.5 rounded-full bg-primary" />}
            </Link>
          );
        })}
      </nav>
      <div className="mx-auto max-w-[860px] space-y-5">{children}</div>
    </Page>
  );
}

function Row({ label, hint, children }: { label: ReactNode; hint?: ReactNode; children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-border py-3 last:border-b-0">
      <div className="min-w-[160px] flex-1">
        <p className="text-[14px] font-semibold">{label}</p>
        {hint && <p className="text-[12px] text-muted">{hint}</p>}
      </div>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
    </div>
  );
}

const SourceChip = ({ s }: { s: "auto" | "edited" | null }) =>
  s === "edited" ? (
    <Chip tone="accent" square>
      수정함
    </Chip>
  ) : s === "auto" ? (
    <Chip tone="primary" square>
      자동
    </Chip>
  ) : null;

/** 이 항목을 쓰는 기능 (C2-S05) */
const UsedBy = ({ f }: { f: string[] }) => (
  <span className="inline-flex gap-1 align-middle">
    {f.map((x) => (
      <span key={x} className="rounded bg-surface-3 px-1 text-[11px] font-semibold text-faint">
        {x}
      </span>
    ))}
  </span>
);

/** 숫자 칸 — 칸을 벗어날 때 저장. 서버 값이 바뀌면 칸도 다시 그린다(key). */
function NumField({
  value,
  onCommit,
  label,
  step = 1,
  min = 0,
  max,
}: {
  value: number | null;
  onCommit: (v: number | null) => void;
  label: string;
  step?: number;
  min?: number;
  max?: number;
}) {
  return (
    <input
      key={String(value)}
      type="number"
      inputMode="decimal"
      step={step}
      min={min}
      max={max}
      aria-label={label}
      className="field field-sm num w-24"
      defaultValue={value ?? ""}
      onBlur={(e) => {
        const raw = e.target.value.trim();
        const v = raw === "" ? null : Number(raw);
        if (v !== value && (v === null || !Number.isNaN(v))) onCommit(v);
      }}
    />
  );
}

/* ------------------------------------------------------------------ /settings/profile */

export function ProfileSettings() {
  const router = useRouter();
  const toast = useToast();
  const { doc, profile: p, error, update, refresh, source } = useProfile();
  const imp = useProfileImport();
  const picker = useQueryValue("picker") === "dept";
  const [sensOpen, setSensOpen] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const year = new Date().getFullYear();

  const shellProps = { title: "내 프로필", subtitle: "F1 학사일정 대상 판정 · F2 졸업요건 기준 · F11 장학 매칭에 쓰입니다 — 이 PC 안에만 저장됩니다" };
  if (!p || !doc) {
    return (
      <SettingsShell {...shellProps}>
        {error ? <ErrorPanel message="프로필을 불러오지 못했습니다" onRetry={() => void refresh()} /> : <p className="py-8 text-center text-[14px] text-muted">불러오는 중…</p>}
      </SettingsShell>
    );
  }
  const sens = [p.incomeBracket, p.residenceRegion, p.highSchoolRegion].some((x) => x !== null) || Object.keys(p.flags ?? {}).length > 0;

  return (
    <SettingsShell {...shellProps}>
      {!doc.complete && (
        <Banner tone="info">
          필수 항목 <b>{doc.missing.map((k) => FIELD_LABEL[k] ?? k).join(" · ")}</b> 을(를) 입력하면 졸업요건 기준이 붙고 학사일정 &lsquo;내 해당&rsquo;이 정확해집니다
        </Banner>
      )}
      <Section title="기본 정보">
        <Row
          label={
            <>
              소속 <UsedBy f={["F1", "F2", "F11"]} />
            </>
          }
          hint="학사일정 대상 판정 · 졸업요건 기준 · 장학 매칭"
        >
          <span className="text-[14px]">{p.deptPath ?? <span className="text-faint">미입력</span>}</span>
          <SourceChip s={source("deptCode")} />
          {p.affiliationRetired && (
            <Chip tone="warn" square>
              개편·폐지된 학과
            </Chip>
          )}
          <button type="button" className="btn btn-sm" onClick={() => navigateQuery({ picker: "dept" }, "push")}>
            {p.deptCode ? "바꾸기" : "고르기"}
          </button>
        </Row>
        <Row
          label={
            <>
              입학년도 <UsedBy f={["F2"]} />
            </>
          }
          hint="졸업요건은 입학년도 기준을 따릅니다"
        >
          <select
            className="field field-sm w-auto"
            aria-label="입학년도"
            value={p.admissionYear ?? ""}
            onChange={async (e) => {
              const v = e.target.value ? Number(e.target.value) : null;
              const d = await update({ admissionYear: v });
              if (d && v && d.profile.deptPath) toast(`졸업요건 기준이 ${v} ${d.profile.major ?? d.profile.department}(으)로 바뀌었습니다`);
            }}
          >
            <option value="">선택</option>
            {Array.from({ length: 10 }, (_, i) => year - i).map((y) => (
              <option key={y} value={y}>
                {y}학년도
              </option>
            ))}
          </select>
        </Row>
        <Row
          label={
            <>
              이수유형 <UsedBy f={["F2"]} />
            </>
          }
        >
          <select className="field field-sm w-auto" aria-label="이수유형" value={p.track ?? ""} onChange={(e) => void update({ track: (e.target.value || null) as Track | null })}>
            <option value="">선택</option>
            {(Object.keys(TRACK_LABEL) as Track[]).map((t) => (
              <option key={t} value={t}>
                {TRACK_LABEL[t]}
              </option>
            ))}
          </select>
        </Row>
        <Row
          label={
            <>
              학년 · 학적 <UsedBy f={["F1", "F11"]} />
            </>
          }
          hint="학사일정 '내 해당' 판정에 쓰입니다"
        >
          <select className="field field-sm w-auto" aria-label="학년" value={p.grade ?? ""} onChange={(e) => void update({ grade: e.target.value ? Number(e.target.value) : null })}>
            <option value="">학년</option>
            {[1, 2, 3, 4, 5, 6].map((g) => (
              <option key={g} value={g}>
                {g}학년
              </option>
            ))}
          </select>
          <SourceChip s={source("grade")} />
          <select
            className="field field-sm w-auto"
            aria-label="학적"
            value={p.enrollmentStatus ?? ""}
            onChange={(e) => void update({ enrollmentStatus: (e.target.value || null) as Enrollment | null })}
          >
            <option value="">학적</option>
            {ENROLLMENT.map((x) => (
              <option key={x}>{x}</option>
            ))}
          </select>
          <SourceChip s={source("enrollmentStatus")} />
        </Row>
      </Section>

      <Section
        title="성적·학점"
        action={
          <button type="button" className="btn btn-sm" disabled={imp.running} onClick={() => void imp.start()}>
            {imp.running ? <span className="spin" aria-hidden /> : <Download aria-hidden />}
            {imp.running ? "가져오는 중…" : "학사시스템에서 가져오기"}
          </button>
        }
      >
        <ImportProblem imp={imp} />
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="rounded-xl bg-surface-2 p-3">
            <span className="flex items-center gap-2 text-[13px] font-semibold text-muted">
              평점 <UsedBy f={["F2", "F11"]} />
              <SourceChip s={source("gpa")} />
            </span>
            <span className="mt-1 flex items-baseline gap-1">
              <NumField
                label="평점"
                step={0.01}
                max={p.gpa?.scale ?? 4.5}
                value={p.gpa?.value ?? null}
                onCommit={(v) => void update({ gpa: v === null ? null : { value: v, scale: p.gpa?.scale ?? 4.5, basis: p.gpa?.basis ?? "전체" } })}
              />
              <select
                className="field field-sm w-auto"
                aria-label="평점 만점"
                value={p.gpa?.scale ?? 4.5}
                disabled={!p.gpa}
                onChange={(e) => {
                  if (p.gpa) void update({ gpa: { ...p.gpa, scale: Number(e.target.value) } });
                }}
              >
                {[4.5, 4.3, 4.0].map((s) => (
                  <option key={s} value={s}>
                    / {s}
                  </option>
                ))}
              </select>
            </span>
          </label>
          {(
            [
              ["earnedCredits", "취득학점", "학점", ["F2", "F11"], 400],
              ["semestersCompleted", "이수학기", "학기", ["F11"], 20],
              ["lastSemesterCredits", "직전 학기 학점", "학점", ["F11"], 40],
            ] as const
          ).map(([k, l, u, f, max]) => (
            <label key={k} className="rounded-xl bg-surface-2 p-3">
              <span className="flex items-center gap-2 text-[13px] font-semibold text-muted">
                {l} <UsedBy f={[...f]} />
                <SourceChip s={source(k)} />
              </span>
              <span className="mt-1 flex items-baseline gap-1">
                <NumField label={l} max={max} value={p[k]} onCommit={(v) => void update({ [k]: v })} />
                <span className="text-[13px] text-faint">{u}</span>
              </span>
            </label>
          ))}
        </div>
        <p className="hint">
          {doc.importedAt ? `마지막으로 가져온 때: ${fmtShortStamp(doc.importedAt)} · ` : ""}학사시스템 값은 &lsquo;자동&rsquo;, 내가 고치면 &lsquo;수정함&rsquo; — 다시 가져와도 내가 고친 값은 덮지 않습니다. 공식 성적증명과 다를 수 있습니다.
        </p>
      </Section>

      <section className="card">
        <button type="button" className="flex w-full items-center gap-2 p-4 text-left md:p-5" aria-expanded={sensOpen} onClick={() => setSensOpen((v) => !v)}>
          <span className="flex-1 text-[15px] font-bold">장학 매칭용 정보 (선택)</span>
          <span className="text-[12px] text-faint">{sensOpen ? "" : sens ? "입력됨 · 접혀 있음" : "접혀 있음"}</span>
          <ChevronDown className={`size-4 text-faint transition-transform ${sensOpen ? "rotate-180" : ""}`} aria-hidden />
        </button>
        <AnimatePresence initial={false}>
          {sensOpen && (
            <motion.div initial={{ height: 0 }} animate={{ height: "auto" }} exit={{ height: 0 }} style={{ overflow: "hidden" }}>
              <div className="border-t border-border px-4 pb-4 md:px-5">
                <p className="py-3 text-[13px] text-muted">F11 장학 매칭에만 쓰이고 이 PC 밖으로 나가지 않습니다. 비워 두어도 다른 기능은 그대로 동작하며, 언제든 지울 수 있습니다.</p>
                <Row label="학자금 지원구간" hint="국가장학금·소득 연계 장학의 자격 판정에만 씁니다">
                  <select
                    className="field field-sm w-auto"
                    aria-label="학자금 지원구간"
                    value={p.incomeBracket ?? ""}
                    onChange={(e) => void update({ incomeBracket: e.target.value === "" ? null : Number(e.target.value) })}
                  >
                    <option value="">모름 / 입력 안 함</option>
                    {INCOME_BRACKETS.map((n) => (
                      <option key={n} value={n}>
                        {n === 0 ? "기초·차상위 (0구간)" : `${n}구간`}
                      </option>
                    ))}
                  </select>
                </Row>
                {(
                  [
                    ["residenceRegion", "거주 지역", "지자체 장학(주소지 요건) 판정에만 씁니다"],
                    ["highSchoolRegion", "출신 고교 지역", "지역인재 장학 판정에만 씁니다"],
                  ] as const
                ).map(([k, l, why]) => (
                  <Row key={k} label={l} hint={why}>
                    <select className="field field-sm w-auto" aria-label={l} value={p[k] ?? ""} onChange={(e) => void update({ [k]: e.target.value || null })}>
                      <option value="">입력 안 함</option>
                      {REGIONS.map((r) => (
                        <option key={r}>{r}</option>
                      ))}
                    </select>
                  </Row>
                ))}
                <Row label="해당 사항" hint="대상 장학 판정에만 씁니다">
                  {Object.entries(FLAG_LABEL).map(([k, l]) => {
                    const on = !!p.flags?.[k];
                    return (
                      <label key={k} className="flex items-center gap-1.5 text-[13px]">
                        <input type="checkbox" checked={on} onChange={() => void update({ flags: { ...(p.flags ?? {}), [k]: !on } })} />
                        {l}
                      </label>
                    );
                  })}
                </Row>
                <div className="flex justify-end pt-3">
                  <button
                    type="button"
                    className="btn btn-danger btn-sm"
                    disabled={!sens}
                    onClick={async () => {
                      try {
                        await api.deleteSensitive();
                        await refresh();
                        toast("장학용 정보를 지웠습니다");
                      } catch (e) {
                        toast(`지우지 못했습니다: ${e instanceof Error ? e.message : String(e)}`, { tone: "error" });
                      }
                    }}
                  >
                    장학용 정보 전부 지우기
                  </button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </section>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <button type="button" className="btn btn-ghost text-danger-text" disabled={!doc.exists} onClick={() => setConfirmClear(true)}>
          내 정보 전부 지우기
        </button>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => {
            toast("저장했습니다 — 바꾼 항목은 바로 반영됩니다", { tone: "success" });
            router.back();
          }}
        >
          완료
        </button>
      </div>

      <Modal open={picker} onClose={() => closeQuery(["picker"])} title="학과 고르기">
        <DeptPicker
          value={p.majorCode ?? p.deptCode}
          onChange={async (d) => {
            const r = await update({ affiliation: { deptCode: d.deptCode, majorCode: d.majorCode } });
            if (r) {
              closeQuery(["picker"]);
              toast(`소속: ${d.path}`, { tone: "success" });
            }
          }}
        />
      </Modal>
      <Modal
        open={confirmClear}
        onClose={() => setConfirmClear(false)}
        title="내 정보를 전부 지울까요?"
        footer={
          <>
            <button type="button" className="btn" onClick={() => setConfirmClear(false)}>
              취소
            </button>
            <button
              type="button"
              className="btn btn-danger"
              onClick={async () => {
                setConfirmClear(false);
                try {
                  await api.deleteProfile();
                  await refresh();
                  toast("프로필을 지웠습니다");
                } catch (e) {
                  toast(`지우지 못했습니다: ${e instanceof Error ? e.message : String(e)}`, { tone: "error" });
                }
              }}
            >
              전부 지우기
            </button>
          </>
        }
      >
        <p className="text-[14px] text-muted">소속·입학년도·학년·성적·장학용 정보가 이 PC 에서 바로 지워집니다. 학사일정 &lsquo;내 해당&rsquo; 판정과 졸업요건 기준도 비워집니다.</p>
      </Modal>
    </SettingsShell>
  );
}

/** 가져오기 문제 안내 — 로그인이 필요하면 로그인 창을 여는 버튼 (Frontend-Route 5-7) */
export function ImportProblem({ imp }: { imp: ReturnType<typeof useProfileImport> }) {
  if (!imp.problem) return null;
  return (
    <Banner
      tone={imp.problem.needLogin ? "warn" : "danger"}
      className="mb-3"
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

/* ------------------------------------------------------------------ /settings/sources */

const SRC_STATE: Record<SourceRow["state"], { tone: Tone; label: string }> = {
  ok: { tone: "ok", label: "정상" },
  retry: { tone: "info", label: "재시도 중" },
  login: { tone: "warn", label: "로그인 필요" },
  failed: { tone: "danger", label: "실패" },
};

function SourceList({ list, set, onSync }: { list: SourceRow[]; set: (f: (xs: SourceRow[]) => SourceRow[]) => void; onSync: (r: SourceRow) => void }) {
  return (
    <ul>
      {list.map((r) => (
        <li key={r.key} className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-border py-3 last:border-b-0">
          <div className="min-w-[200px] flex-1">
            <p className="flex flex-wrap items-center gap-2 text-[14px] font-semibold">
              {r.name}
              <Chip square>{r.builtin ? "기본" : "내 추가"}</Chip>
            </p>
            <p className="num text-[12px] text-muted">
              {r.kind} · {r.interval} · {r.last} · {r.count}
            </p>
            {r.error && <p className="text-[12px] font-medium text-danger-text">{r.error}</p>}
          </div>
          <StatusBadge tone={SRC_STATE[r.state].tone}>{SRC_STATE[r.state].label}</StatusBadge>
          {r.state === "login" && (
            <button type="button" className="btn btn-sm">
              <LogIn aria-hidden />
              로그인 창 열기
            </button>
          )}
          <button type="button" className="btn btn-sm" onClick={() => onSync(r)}>
            {r.state === "failed" ? "다시 시도" : "지금 수집"}
          </button>
          <Toggle checked={r.enabled} label={`${r.name} 사용`} onChange={(v) => set((xs) => xs.map((x) => (x.key === r.key ? { ...x, enabled: v } : x)))} />
        </li>
      ))}
    </ul>
  );
}

/* F2 학사정보시스템 기이수성적 — 실제 (GET /api/status 의 graduation, F2-R06) */

function GraduationSource() {
  const { status, refresh } = useAppData();
  const g = status?.graduation;
  const imp = useGradImport(refresh);
  const st = g?.import;
  const state: SourceRow["state"] = imp.problem?.needLogin || st?.needLogin ? "login" : st?.ok === false || imp.problem ? "failed" : "ok";
  return (
    <>
      {imp.problem && (
        <Banner
          tone={imp.problem.needLogin ? "warn" : "danger"}
          className="mb-3"
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
      )}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="min-w-[200px] flex-1">
          <p className="flex flex-wrap items-center gap-2 text-[14px] font-semibold">
            <Link href="/graduation?tab=courses" className="hover:underline">
              기이수성적 (이수 내역 → 졸업요건)
            </Link>
            <Chip square>기본</Chip>
          </p>
          <p className="num text-[12px] text-muted">
            학사시스템 · 수동 ·{" "}
            {g?.importedAt ? `${fmtShortStamp(g.importedAt)} (${fmtRelative(g.importedAt)})` : "아직 안 함"}
            {g?.hasData !== undefined && g.importedAt && ` · 남은 ${g.remaining ?? "—"}학점`}
          </p>
          {st?.error && state !== "ok" && <p className="text-[12px] font-medium text-danger-text">{st.error}</p>}
        </div>
        {g?.available === false ? (
          <StatusBadge tone="danger">F2 없음</StatusBadge>
        ) : (
          <StatusBadge tone={imp.running ? "info" : SRC_STATE[state].tone}>{imp.running ? "가져오는 중" : g?.importedAt ? SRC_STATE[state].label : "수집 전"}</StatusBadge>
        )}
        <button type="button" className="btn btn-sm" disabled={imp.running || g?.available === false} onClick={() => void imp.start()}>
          {imp.running ? <span className="spin spin-dark" aria-hidden /> : <Download aria-hidden />}
          지금 가져오기
        </button>
      </div>
      <p className="mt-2 text-[12px] text-faint">C3_Login_agent 의 학교 로그인 세션을 빌려 이 PC 에서만 읽습니다. 성적은 로그에 남기지 않습니다.</p>
    </>
  );
}

export function SourcesSettings() {
  const toast = useToast();
  const [rows, setRows] = useState(demoSources);
  const [boards, setBoards] = useState(demoBoards);
  const [adding, setAdding] = useState(false);

  return (
    <SettingsShell title="수집 원천" subtitle="어디서 무엇을 가져오는지, 마지막으로 언제 성공했는지">
      <EclassSourceSection />

      <AcademicSourcesSection />

      <Section title="학사정보시스템 (F2·F11)">
        <GraduationSource />
        <div className="mt-3 border-t border-border pt-3">
          <DemoNotice what="장학 카탈로그(F11) 원천" />
          <SourceList list={rows} set={setRows} onSync={(r) => toast(`${r.name} 수집 API 가 아직 없습니다`)} />
        </div>
      </Section>

      <Section
        title="공지 게시판 (F11·F12·F13)"
        action={
          <button type="button" className="btn btn-sm" onClick={() => setAdding(true)}>
            <Plus aria-hidden />
            게시판 추가
          </button>
        }
      >
        <SourceList list={boards} set={setBoards} onSync={(r) => toast(`${r.name} 수집 API 가 아직 없습니다`)} />
      </Section>

      <Modal
        open={adding}
        onClose={() => setAdding(false)}
        title="게시판 추가"
        footer={
          <>
            <button type="button" className="btn" onClick={() => setAdding(false)}>
              취소
            </button>
            <button type="button" className="btn btn-primary" onClick={() => toast("게시판 목록을 찾지 못했습니다 — 저장하지 않았습니다 (구조 인식 API 연결 전)", { tone: "error" })}>
              구조 인식
            </button>
          </>
        }
      >
        <label className="label" htmlFor="board-url">
          게시판 주소
        </label>
        <input id="board-url" data-autofocus className="field" placeholder="https://…" />
        <p className="hint">공개 게시판만 지원합니다. 인식에 성공하면 최근 글 3건을 미리 보여 드립니다.</p>
      </Modal>
    </SettingsShell>
  );
}

/* ------------------------------------------------------------------ /settings/requirements */

export function RequirementsSettings() {
  return (
    <SettingsShell title="졸업요건 기준" subtitle="룰셋 보기·수정 — 값마다 근거(학과 졸업안내·요람·학칙)를 옆에 둡니다">
      <RequirementsEditor />
    </SettingsShell>
  );
}

/* ------------------------------------------------------------------ /settings/availability */

// 가용 시간 (2026-10-07) — 하루를 둘로 나눠 쓴다.
//   낮(기본 09:00~18:00) = 공강 배치(F8): 과제·할 일을 먼저 넣고 남는 공강은 공부 블록. 서버 F8_Plan_agent data/settings.json
//   저녁(기본 19:00~24:00) = 시험 공부 계획(F5) 전용: 계획의 날짜별 분량이 차례로 놓인다. 서버 F5 exams.db meta.evening
// 바꾸면 바로 저장한다(기본값과 다른 값만). 하루 상한은 두 기능 모두 없다.

const DAY_STARTS = ["07:00", "08:00", "09:00", "10:00", "11:00"];
const DAY_ENDS = ["15:00", "16:00", "17:00", "18:00", "19:00"];
const EVENING_STARTS = ["17:00", "18:00", "18:30", "19:00", "19:30", "20:00", "21:00"];
const EVENING_ENDS = ["21:00", "22:00", "22:30", "23:00", "23:30", "24:00"];
const withCurrent = (list: string[], cur?: string) => [...new Set([...list, ...(cur ? [cur] : [])])].sort();

function TimeSelect({ label, value, options, onChange, disabled }: { label: string; value?: string; options: string[]; onChange: (v: string) => void; disabled?: boolean }) {
  return (
    <select className="field field-sm w-auto" aria-label={label} disabled={disabled} value={value ?? ""} onChange={(e) => onChange(e.target.value)}>
      {withCurrent(options, value).map((t) => (
        <option key={t} value={t}>
          {t}
        </option>
      ))}
    </select>
  );
}

export function AvailabilitySettings() {
  const toast = useToast();
  const { refresh } = useAppData();
  const [v, setV] = useState<AvailabilityView | null>(null);
  const [ev, setEv] = useState<ExamSettings["evening"] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [from, setFrom] = useState(() => toDateStr(new Date()));
  const [to, setTo] = useState(() => toDateStr(addDays(new Date(), 13)));
  const [clearing, setClearing] = useState(false);

  useEffect(() => {
    api.availability().then(setV).catch((e: unknown) => setErr(e instanceof Error ? e.message : String(e)));
    api.examSettings().then((s) => setEv(s.evening)).catch(() => setEv(null));
  }, []);

  const save = async (patch: Parameters<typeof api.patchAvailability>[0], ok = "저장했습니다") => {
    const before = v;
    if (v && !patch.reset) setV({ ...v, ...(patch as Partial<AvailabilityView>) });
    try {
      setV(await api.patchAvailability(patch));
      toast(ok, { tone: "success" });
    } catch (e) {
      setV(before);
      toast(`저장하지 못했습니다: ${e instanceof Error ? e.message : String(e)}`, { tone: "error" });
    }
  };

  const saveEvening = async (patch: { start?: string | null; end?: string | null } | null, ok = "저녁 시간대를 바꿨습니다") => {
    try {
      setEv((await api.putEvening(patch)).evening);
      toast(ok, { tone: "success" });
    } catch (e) {
      toast(`저장하지 못했습니다: ${e instanceof Error ? e.message : String(e)}`, { tone: "error" });
    }
  };

  const clear = async () => {
    setClearing(true);
    try {
      const out = await api.clearPlacement(from || undefined, to || undefined);
      await refresh();
      toast(out.deleted ? `자동 배치 블록 ${out.deleted}개를 지웠습니다` : "지울 자동 배치 블록이 없습니다", { tone: out.deleted ? "success" : "default" });
    } catch (e) {
      toast(`지우지 못했습니다: ${e instanceof Error ? e.message : String(e)}`, { tone: "error" });
    } finally {
      setClearing(false);
    }
  };

  if (err)
    return (
      <SettingsShell title="가용 시간">
        <ErrorPanel message={`설정을 불러오지 못했습니다 — ${err}`} />
      </SettingsShell>
    );
  const changed = (k: keyof Avail) => !!v?.changed.includes(k);
  const dflt = (k: keyof Avail) => (v ? String(v.defaults[k]) : "");

  return (
    <SettingsShell title="가용 시간" subtitle="낮 공강은 공강 배치(F8)가, 저녁은 시험 공부 계획(F5)이 씁니다">
      <Section
        title="낮 — 공강 배치"
        action={
          v && v.changed.length > 0 ? (
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => save({ reset: true }, "기본값으로 되돌렸습니다")}>
              기본값으로
            </button>
          ) : undefined
        }
      >
        <Row label="배치 범위" hint={`기본 ${dflt("dayStart")} ~ ${dflt("dayEnd")} · 이 안에서 수업·일정을 뺀 빈 시간이 공강입니다`}>
          <TimeSelect label="낮 시작" value={v?.dayStart} options={DAY_STARTS} disabled={!v} onChange={(t) => save({ dayStart: t })} />
          <span className="text-muted">~</span>
          <TimeSelect label="낮 끝" value={v?.dayEnd} options={DAY_ENDS} disabled={!v} onChange={(t) => save({ dayEnd: t })} />
          {(changed("dayStart") || changed("dayEnd")) && (
            <Chip tone="accent" square>
              수정함
            </Chip>
          )}
        </Row>
        <Row label="남는 공강에 공부 블록" hint="과제·할 일을 넣고 남은 공강을 시험 공부로 채웁니다 — 과목은 남은 진도율 ÷ 시험까지 남은 날수가 큰 순">
          <Toggle checked={v?.fillStudy ?? true} disabled={!v} onChange={(x) => save({ fillStudy: x })} label="남는 공강에 공부 블록" />
        </Row>
        <Row label="점심 제외" hint={v ? `${v.lunchStart} ~ ${v.lunchEnd} 에는 넣지 않습니다` : "12:00 ~ 13:00"}>
          <Toggle checked={v?.lunchBreak ?? true} disabled={!v} onChange={(x) => save({ lunchBreak: x })} label="점심 제외" />
        </Row>
        <Row label="주말 사용" hint="켜면 토·일 낮도 같은 규칙으로 채웁니다">
          <Toggle checked={v?.useWeekend ?? false} disabled={!v} onChange={(x) => save({ useWeekend: x })} label="주말 사용" />
        </Row>
        <Row label="수업 앞뒤 여유" hint="이동·준비 시간 — 수업 끝나자마자 시작하는 블록을 만들지 않습니다">
          <select className="field field-sm w-auto" aria-label="여유" disabled={!v} value={v?.bufferMinutes ?? 10} onChange={(e) => save({ bufferMinutes: Number(e.target.value) })}>
            {(v?.choices.bufferMinutes ?? [0, 5, 10, 15, 20, 30]).map((m) => (
              <option key={m} value={m}>
                {m}분
              </option>
            ))}
          </select>
        </Row>
        <Row label="블록 길이" hint="이보다 짧은 공강은 버리고, 긴 작업은 최대 길이로 쪼갭니다">
          <select className="field field-sm w-auto" aria-label="최소 블록" disabled={!v} value={v?.minSlotMinutes ?? 30} onChange={(e) => save({ minSlotMinutes: Number(e.target.value) })}>
            {[15, 20, 30, 45, 60].map((m) => (
              <option key={m} value={m}>
                최소 {m}분
              </option>
            ))}
          </select>
          <select className="field field-sm w-auto" aria-label="최대 블록" disabled={!v} value={v?.maxBlockMinutes ?? 120} onChange={(e) => save({ maxBlockMinutes: Number(e.target.value) })}>
            {[60, 90, 120, 150, 180].map((m) => (
              <option key={m} value={m}>
                최대 {m / 60}시간
              </option>
            ))}
          </select>
        </Row>
        <Row label="배치 기간" hint="미리보기를 열 때 계산하는 기간 (미리보기에서도 바꿀 수 있습니다)">
          <select className="field field-sm w-auto" aria-label="배치 기간" disabled={!v} value={v?.rangeDays ?? 7} onChange={(e) => save({ rangeDays: Number(e.target.value) })}>
            {(v?.choices.rangeDays ?? [7, 14]).map((n) => (
              <option key={n} value={n}>
                {n}일
              </option>
            ))}
          </select>
        </Row>
      </Section>
      <Section
        title="저녁 — 시험 공부 계획"
        action={
          ev?.changed ? (
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => saveEvening(null, "기본값으로 되돌렸습니다")}>
              기본값으로
            </button>
          ) : undefined
        }
      >
        <Row label="저녁 시간대" hint={`기본 ${ev?.defaults.start ?? "19:00"} ~ ${ev?.defaults.end ?? "24:00"} · 계획의 날짜별 분량이 시험이 가까운 과목부터 이 시간에 차례로 놓입니다 (공부 캘린더)`}>
          <TimeSelect label="저녁 시작" value={ev?.start} options={EVENING_STARTS} disabled={!ev} onChange={(t) => saveEvening({ start: t })} />
          <span className="text-muted">~</span>
          <TimeSelect label="저녁 끝" value={ev?.end} options={EVENING_ENDS} disabled={!ev} onChange={(t) => saveEvening({ end: t })} />
          {ev?.changed && (
            <Chip tone="accent" square>
              수정함
            </Chip>
          )}
        </Row>
        <Row label="하루 상한" hint="두지 않습니다 — 하루에 몇 시간을 할지는 계획 만들기에서 정하고, 경고하지 않습니다">
          <span className="text-[13px] text-muted">없음</span>
        </Row>
      </Section>
      <Section title="자동 배치 블록 지우기">
        <p className="mb-3 text-[13px] text-muted">기간을 골라 공강 배치로 자동으로 넣은 블록만 지웁니다. 내가 옮긴(고정) 블록과 완료한 블록, 이미 시작한 블록은 남깁니다.</p>
        <div className="flex flex-wrap items-center gap-2">
          <input type="date" className="field field-sm w-auto" aria-label="시작 날짜" value={from} onChange={(e) => setFrom(e.target.value)} />
          <span className="text-muted">~</span>
          <input type="date" className="field field-sm w-auto" aria-label="끝 날짜" value={to} min={from} onChange={(e) => setTo(e.target.value)} />
          <button type="button" className="btn btn-danger btn-sm" disabled={clearing} onClick={clear}>
            자동 배치 블록 지우기
          </button>
        </div>
      </Section>
    </SettingsShell>
  );
}

/* ------------------------------------------------------------------ /settings/notifications */

const NOTI_DEFAULT = { briefingOn: true, briefingAt: "08:00", keepDays: 30 };

// 학사 유형별 기본 알림 (F1_Bachelor_agent config.DEFAULT_REMINDERS) — 일정마다 상세에서 바꾼다
const REMINDER_WORD: Record<string, string> = { d7: "D-7", d3: "D-3", d1: "D-1", end1: "종료 전날", m30: "30분 전" };
const DEFAULT_ROWS: [string, string[]][] = [
  ["등록·납부 · 수강신청 · 학적", ["tuition"]],
  ["성적", ["grade"]],
  ["시험", ["exam"]],
  ["개강·방학 · 행사", ["vacation", "event"]],
];

function AlertTimeRow() {
  const toast = useToast();
  const [cfg, setCfg] = useState<{ alertTime: string; defaults: Record<string, string[]> } | null>(null);
  useEffect(() => {
    api.academicSettings().then(setCfg).catch(() => setCfg(null));
  }, []);
  return (
    <>
      <Row label="알림 기본 시각" hint="D-7·D-3·D-1·종료 전날 알림이 이 시각에 울립니다">
        <input
          type="time"
          className="field field-sm w-auto"
          aria-label="알림 기본 시각"
          value={cfg?.alertTime ?? "09:00"}
          disabled={!cfg}
          onChange={async (e) => {
            const t = e.target.value;
            if (!t) return;
            setCfg((c) => (c ? { ...c, alertTime: t } : c));
            try {
              setCfg(await api.putAcademicSettings(t));
              toast("알림 시각을 바꿨습니다", { tone: "success" });
            } catch (err) {
              toast(`저장하지 못했습니다: ${err instanceof Error ? err.message : String(err)}`, { tone: "error" });
            }
          }}
        />
      </Row>
      <Row label="학사일정 (F1)" hint="유형별 기본값 — 일정마다 상세 창에서 켜고 끌 수 있습니다. 시각이 있는 일정은 30분 전에도 울립니다">
        <ul className="space-y-1 text-[13px]">
          {DEFAULT_ROWS.map(([label, types]) => (
            <li key={label} className="flex flex-wrap items-center gap-1.5">
              <span className="w-44 text-muted">{label}</span>
              {(cfg?.defaults[types[0]] ?? []).filter((c) => c !== "m30").map((c) => (
                <Chip key={c} tone="primary" square>
                  {REMINDER_WORD[c] ?? c}
                </Chip>
              ))}
            </li>
          ))}
          <li className="text-faint">휴업일·수업일수·보강일은 알림 없음</li>
        </ul>
      </Row>
    </>
  );
}

/** 과제 마감 알림 (F6-R40·R41) — D-3 · D-1 · 당일 아침 09:00. 서버(F6 원장)에 저장하고, 서버가 때가 되면 알림 센터에 넣는다. */
/** E클래스 새 글·자료 알림 — 공지는 한 건씩, 자료실 글·강의자료는 하루치 묶음 (서버 저장) */
function EclassFeedNotifyRow() {
  const toast = useToast();
  const [cfg, setCfg] = useState<FeedSettings | null>(null);
  useEffect(() => {
    api.feedSettings().then(setCfg).catch(() => setCfg(null));
  }, []);
  const set = async (k: keyof FeedSettings, v: boolean) => {
    if (!cfg) return;
    const before = cfg;
    setCfg({ ...cfg, [k]: v });
    try {
      setCfg(await api.putFeedSettings({ [k]: v }));
    } catch (e) {
      setCfg(before);
      toast(`저장하지 못했습니다: ${e instanceof Error ? e.message : String(e)}`, { tone: "error" });
    }
  };
  return (
    <Row label="E클래스 새 글·자료 (F6)" hint="수집할 때 새로 올라온 것만 — 공지는 한 건씩, 자료실 글·강의자료는 하루치를 한 줄로 묶습니다">
      <span className="flex items-center gap-2 text-[13px]">
        새 공지
        <Toggle checked={!!cfg?.notices} disabled={!cfg} onChange={(v) => void set("notices", v)} label="새 공지 알림" />
      </span>
      <span className="flex items-center gap-2 text-[13px]">
        자료실 글·강의자료
        <Toggle checked={!!cfg?.materials} disabled={!cfg} onChange={(v) => void set("materials", v)} label="새 자료 알림" />
      </span>
    </Row>
  );
}

function DeadlineReminderRow() {
  const toast = useToast();
  const [cfg, setCfg] = useState<ReminderSettings | null>(null);
  useEffect(() => {
    api.reminderSettings().then(setCfg).catch(() => setCfg(null));
  }, []);
  const toggle = async (code: string) => {
    if (!cfg) return;
    const next = cfg.reminders.includes(code) ? cfg.reminders.filter((c) => c !== code) : [...cfg.reminders, code];
    setCfg({ ...cfg, reminders: next });
    try {
      setCfg(await api.putReminderSettings(next));
    } catch (e) {
      setCfg(cfg);
      toast(`저장하지 못했습니다: ${e instanceof Error ? e.message : String(e)}`, { tone: "error" });
    }
  };
  const next = cfg?.planned?.[0];
  return (
    <Row
      label="과제 마감 (F6)"
      hint={`${cfg?.alertTime ?? "09:00"} 에 울립니다 · 마감이 09시 이전이면 당일 알림은 ${cfg?.earlyDueHours ?? 3}시간 전 · 자정 마감은 전날 밤으로 봅니다 · 제출하면 남은 알림은 취소${
        next ? ` · 다음 ${fmtShortStamp(next.at)} ${next.title}` : ""
      }`}
    >
      {(cfg?.choices ?? [
        { code: "d3", label: "D-3" },
        { code: "d1", label: "D-1" },
        { code: "d0", label: "당일 아침" },
      ]).map((c) => {
        const on = !!cfg?.reminders.includes(c.code);
        return (
          <button
            key={c.code}
            type="button"
            aria-pressed={on}
            disabled={!cfg}
            onClick={() => void toggle(c.code)}
            className={`btn btn-sm ${on ? "border-primary bg-primary-soft text-primary" : ""}`}
          >
            {c.label}
          </button>
        );
      })}
    </Row>
  );
}

export function NotificationSettings() {
  const [v, setV] = useStored("notification-settings", NOTI_DEFAULT);
  return (
    <SettingsShell title="알림·브리핑" subtitle="PC 화면 안에서 끝나는 알림 — 헤더 종 + 놓친 알림 모아보기">
      <Section title="아침 브리핑 (F10)">
        <Row label="브리핑 받기">
          <Toggle checked={v.briefingOn} onChange={(x) => setV((p) => ({ ...p, briefingOn: x }))} label="브리핑 받기" />
        </Row>
        <Row label="브리핑 시각" hint="PC 가 꺼져 있었으면 켤 때 그 시점 기준으로 만듭니다">
          <input type="time" className="field field-sm w-auto" aria-label="브리핑 시각" value={v.briefingAt} disabled={!v.briefingOn} onChange={(e) => setV((p) => ({ ...p, briefingAt: e.target.value }))} />
        </Row>
        <Row label="보관 기간">
          <select className="field field-sm w-auto" aria-label="보관 기간" value={v.keepDays} onChange={(e) => setV((p) => ({ ...p, keepDays: Number(e.target.value) }))}>
            {[7, 14, 30].map((d) => (
              <option key={d} value={d}>
                {d}일
              </option>
            ))}
          </select>
        </Row>
      </Section>
      <Section title="알림 시점">
        <AlertTimeRow />
        <DeadlineReminderRow />
        <EclassFeedNotifyRow />
      </Section>
      <p className="text-[12px] text-faint">모바일 알림(Web Push·메신저)은 추후 검토입니다(전역 결정 G2). 알림 시각·과제 마감 알림은 서버에, 브리핑은 이 브라우저에 저장됩니다.</p>
    </SettingsShell>
  );
}
