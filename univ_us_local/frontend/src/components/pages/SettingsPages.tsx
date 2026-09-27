"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ChevronDown, Download, LogIn, Plus, RefreshCw, RotateCcw, Settings } from "lucide-react";
import { Page, PageHeader, Section, Toggle } from "@/components/ui/Layout";
import { Banner, DemoNotice } from "@/components/ui/Feedback";
import { Chip, StatusBadge, type Tone } from "@/components/ui/Chip";
import { Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { useAppData } from "@/components/app/AppData";
import { DeptPicker } from "@/components/profile/DeptPicker";
import { useProfile } from "@/lib/useProfile";
import { useStored } from "@/lib/storage";
import { closeQuery, navigateQuery, useQueryValue } from "@/lib/useQueryState";
import { SETTINGS } from "@/lib/features";
import { AREA_LABEL, demoBoards, demoImported, demoRuleset, demoRunHistory, demoSources, deptPath, TRACK_LABEL, type SourceRow, type Track } from "@/lib/demo";
import { fmtRelative, fmtShortStamp } from "@/lib/dates";

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

const AutoChip = ({ auto, edited }: { auto: boolean; edited: boolean }) =>
  edited ? (
    <Chip tone="accent" square>
      수정함
    </Chip>
  ) : auto ? (
    <Chip tone="primary" square>
      자동
    </Chip>
  ) : null;

/* ------------------------------------------------------------------ /settings/profile */

export function ProfileSettings() {
  const router = useRouter();
  const toast = useToast();
  const { profile, setProfile, dept } = useProfile();
  const picker = useQueryValue("picker") === "dept";
  const [sensOpen, setSensOpen] = useState(false);
  const year = new Date().getFullYear();
  const auto = (k: string) => profile.auto.includes(k);
  const edited = (k: string) => profile.edited.includes(k);
  const setAutoField = (k: "grade" | "gpa" | "credits" | "semesters", v: number | null) =>
    setProfile((p) => ({ ...p, [k]: v, edited: p.auto.includes(k) && !p.edited.includes(k) ? [...p.edited, k] : p.edited }));

  return (
    <SettingsShell title="내 프로필" subtitle="F1 학사일정 대상 판정 · F2 졸업요건 기준 · F11 장학 매칭에 쓰입니다">
      <DemoNotice what="프로필 저장(이 브라우저에만 저장)" />
      <Section title="기본 정보">
        <Row label="소속" hint="F1 학사일정 대상 판정, F2 졸업요건 기준에 쓰입니다">
          <span className="text-[14px]">{dept ? deptPath(dept) : <span className="text-faint">미입력</span>}</span>
          <button type="button" className="btn btn-sm" onClick={() => navigateQuery({ picker: "dept" }, "push")}>
            바꾸기
          </button>
        </Row>
        <Row label="입학년도">
          <select
            className="field field-sm w-auto"
            aria-label="입학년도"
            value={profile.admissionYear ?? ""}
            onChange={(e) => {
              setProfile((p) => ({ ...p, admissionYear: e.target.value ? Number(e.target.value) : null }));
              if (dept && e.target.value) toast(`졸업요건 기준이 ${e.target.value} ${dept.major ?? dept.dept}으로 바뀌었습니다`);
            }}
          >
            <option value="">선택</option>
            {Array.from({ length: 8 }, (_, i) => year - i).map((y) => (
              <option key={y} value={y}>
                {y}학년도
              </option>
            ))}
          </select>
        </Row>
        <Row label="이수유형">
          <select
            className="field field-sm w-auto"
            aria-label="이수유형"
            value={profile.track ?? ""}
            onChange={(e) => setProfile((p) => ({ ...p, track: (e.target.value || null) as Track | null }))}
          >
            <option value="">선택</option>
            {(Object.keys(TRACK_LABEL) as Track[]).map((t) => (
              <option key={t} value={t}>
                {TRACK_LABEL[t]}
              </option>
            ))}
          </select>
        </Row>
        <Row label="학년 · 학적">
          <select className="field field-sm w-auto" aria-label="학년" value={profile.grade ?? ""} onChange={(e) => setAutoField("grade", e.target.value ? Number(e.target.value) : null)}>
            <option value="">학년</option>
            {[1, 2, 3, 4, 5].map((g) => (
              <option key={g} value={g}>
                {g === 5 ? "초과" : `${g}학년`}
              </option>
            ))}
          </select>
          <AutoChip auto={auto("grade")} edited={edited("grade")} />
          <select
            className="field field-sm w-auto"
            aria-label="학적"
            value={profile.enrollment ?? ""}
            onChange={(e) => setProfile((p) => ({ ...p, enrollment: (e.target.value || null) as typeof p.enrollment }))}
          >
            <option value="">학적</option>
            <option>재학</option>
            <option>휴학</option>
            <option>졸업유예</option>
          </select>
          <AutoChip auto={auto("enrollment")} edited={edited("enrollment")} />
        </Row>
      </Section>

      <Section
        title="성적·학점"
        action={
          <button
            type="button"
            className="btn btn-sm"
            onClick={() => {
              setProfile((p) => ({ ...p, ...demoImported, auto: ["grade", "enrollment", "gpa", "credits", "semesters"], edited: [] }));
              toast("학사정보시스템에서 가져왔습니다 (예시)", { tone: "success" });
            }}
          >
            <Download aria-hidden />
            학사시스템에서 가져오기
          </button>
        }
      >
        <div className="grid gap-3 sm:grid-cols-3">
          {(
            [
              ["gpa", "평점", "/4.5"],
              ["credits", "취득학점", "학점"],
              ["semesters", "이수학기", "학기"],
            ] as const
          ).map(([k, l, u]) => (
            <label key={k} className="rounded-xl bg-surface-2 p-3">
              <span className="flex items-center gap-2 text-[13px] font-semibold text-muted">
                {l}
                <AutoChip auto={auto(k)} edited={edited(k)} />
              </span>
              <span className="mt-1 flex items-baseline gap-1">
                <input
                  type="number"
                  step={k === "gpa" ? 0.01 : 1}
                  className="field field-sm num w-24"
                  value={profile[k] ?? ""}
                  onChange={(e) => setAutoField(k, e.target.value ? Number(e.target.value) : null)}
                />
                <span className="text-[13px] text-faint">{u}</span>
              </span>
            </label>
          ))}
        </div>
      </Section>

      <section className="card">
        <button type="button" className="flex w-full items-center gap-2 p-4 text-left md:p-5" aria-expanded={sensOpen} onClick={() => setSensOpen((v) => !v)}>
          <span className="flex-1 text-[15px] font-bold">장학 매칭용 정보 (선택)</span>
          <span className="text-[12px] text-faint">{sensOpen ? "" : "접혀 있음"}</span>
          <ChevronDown className={`size-4 text-faint transition-transform ${sensOpen ? "rotate-180" : ""}`} aria-hidden />
        </button>
        <AnimatePresence initial={false}>
          {sensOpen && (
            <motion.div initial={{ height: 0 }} animate={{ height: "auto" }} exit={{ height: 0 }} style={{ overflow: "hidden" }}>
              <div className="border-t border-border px-4 pb-4 md:px-5">
                <p className="py-3 text-[13px] text-muted">F11 장학 매칭에만 쓰이고 PC 밖으로 나가지 않습니다.</p>
                {(
                  [
                    ["income", "소득구간"],
                    ["region", "거주지역"],
                    ["school", "출신고교 지역"],
                  ] as const
                ).map(([k, l]) => (
                  <Row key={k} label={l}>
                    <input
                      className="field field-sm w-48"
                      value={profile.sensitive[k]}
                      aria-label={l}
                      onChange={(e) => setProfile((p) => ({ ...p, sensitive: { ...p.sensitive, [k]: e.target.value } }))}
                    />
                  </Row>
                ))}
                <div className="flex justify-end pt-3">
                  <button type="button" className="btn btn-danger btn-sm" onClick={() => setProfile((p) => ({ ...p, sensitive: { income: "", region: "", school: "" } }))}>
                    전부 지우기
                  </button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </section>

      <div className="flex justify-end">
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => {
            toast("저장했습니다", { tone: "success" });
            router.back();
          }}
        >
          저장
        </button>
      </div>

      <Modal open={picker} onClose={() => closeQuery(["picker"])} title="학과 바꾸기">
        <DeptPicker
          value={profile.deptCode}
          onChange={(d) => {
            setProfile((p) => ({ ...p, deptCode: d.code }));
            closeQuery(["picker"]);
          }}
        />
      </Modal>
    </SettingsShell>
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

export function SourcesSettings() {
  const toast = useToast();
  const { status, syncing, startSync } = useAppData();
  const [rows, setRows] = useState(demoSources);
  const [boards, setBoards] = useState(demoBoards);
  const [adding, setAdding] = useState(false);
  const exit = status?.sync.exit_code;
  const eState: SourceRow["state"] = exit === 2 ? "login" : exit !== null && exit !== undefined && exit !== 0 && exit !== 3 ? "failed" : "ok";

  return (
    <SettingsShell title="수집 원천" subtitle="어디서 무엇을 가져오는지, 마지막으로 언제 성공했는지">
      <Section
        title="e클래스 (과제·마감·강의자료)"
        action={
          <button type="button" className="btn btn-primary btn-sm" onClick={startSync} disabled={syncing}>
            <RefreshCw className={syncing ? "animate-spin" : ""} aria-hidden />
            {syncing ? (status?.sync.source === "external" ? "예약 동기화 진행 중…" : "진행 중…") : "지금 수집"}
          </button>
        }
      >
        {eState !== "ok" && (
          <Banner tone={eState === "login" ? "warn" : "danger"} className="mb-3">
            {eState === "login" ? "e클래스 로그인이 필요합니다 — eclass_agent 의 login.cmd 를 실행하세요" : `마지막 실행이 실패했습니다 (코드 ${exit})`}
          </Banner>
        )}
        <Row label="주기" hint="바꾸면 작업 스케줄러를 다시 등록합니다">
          <select className="field field-sm w-auto" aria-label="주기" defaultValue="4">
            <option value="2">2시간</option>
            <option value="4">4시간 (00·04·08·12·16·20시)</option>
            <option value="6">6시간</option>
            <option value="12">12시간</option>
          </select>
        </Row>
        <Row label="마지막 성공">
          <span className="num text-[14px]">
            {status ? `${fmtShortStamp(status.updated_at)} (${fmtRelative(status.updated_at)}) · 과목 ${status.counts.courses} · 과제 ${status.counts.deadlines}` : "확인 중"}
          </span>
        </Row>
        <div className="pt-3">
          <p className="label">최근 실행 (예시)</p>
          <ul className="space-y-1 text-[13px]">
            {demoRunHistory.map((h) => (
              <li key={h.at} className="flex items-center gap-3">
                <span className="num w-12 text-muted">{h.at}</span>
                <StatusBadge tone={h.tone}>{h.result}</StatusBadge>
                <span className="text-muted">{h.detail}</span>
              </li>
            ))}
          </ul>
          {status && status.log.length > 0 && (
            <details className="mt-3">
              <summary className="cursor-pointer text-[13px] font-semibold text-muted">sync.log 끝부분</summary>
              <pre className="thin-scroll mt-2 max-h-48 overflow-auto rounded-lg bg-surface-2 p-3 text-[12px] leading-relaxed whitespace-pre-wrap">{status.log.join("\n")}</pre>
            </details>
          )}
        </div>
      </Section>

      <Section title="학사일정 · 학사시스템">
        <DemoNotice what="학사·학과 원천" />
        <SourceList list={rows} set={setRows} onSync={(r) => toast(`${r.name} 수집 API 가 아직 없습니다`)} />
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
  const toast = useToast();
  const [rows, setRows] = useState(demoRuleset.rows);
  const [edited, setEdited] = useState(false);
  return (
    <SettingsShell title="졸업요건 기준" subtitle="룰셋 보기·수정 — 값마다 근거(요람 쪽수·학칙 조항)를 옆에 둡니다">
      <DemoNotice what="졸업요건 룰셋" />
      <Section
        title={`${demoRuleset.year}학년도 · ${demoRuleset.dept} · ${TRACK_LABEL[demoRuleset.track]}`}
        action={edited && <Chip tone="accent" square>사용자 수정</Chip>}
      >
        <ul>
          {rows.map((r) => (
            <li key={r.key} className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-border py-3 last:border-b-0">
              <span className="w-24 text-[14px] font-semibold">{r.label}</span>
              <span className="flex items-baseline gap-1">
                <input
                  type="number"
                  step={r.key === "gpa" ? 0.01 : 1}
                  aria-label={r.label}
                  className="field field-sm num w-24"
                  value={r.value}
                  onChange={(e) => {
                    setEdited(true);
                    setRows((xs) => xs.map((x) => (x.key === r.key ? { ...x, value: Number(e.target.value) } : x)));
                  }}
                />
                <span className="text-[13px] text-faint">{r.unit}</span>
              </span>
              <span className="ml-auto text-[12px] text-muted">근거: {r.basis}</span>
            </li>
          ))}
        </ul>
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            className="btn btn-sm"
            disabled={!edited}
            onClick={() => {
              setRows(demoRuleset.rows);
              setEdited(false);
            }}
          >
            <RotateCcw aria-hidden />
            기본값으로 되돌리기
          </button>
          <button type="button" className="btn btn-primary btn-sm" onClick={() => toast("저장했습니다 — 졸업요건을 다시 계산합니다 (예시)", { tone: "success" })}>
            저장
          </button>
        </div>
      </Section>
      <Section title="교과구분 매핑" action={<span className="text-[12px] text-faint">학사시스템 구분 문자열 → 영역</span>}>
        <ul className="grid gap-2 sm:grid-cols-2">
          {demoRuleset.mapping.map((m) => (
            <li key={m.from} className="flex items-center gap-2 rounded-lg bg-surface-2 px-3 py-2 text-[14px]">
              <code className="rounded bg-surface px-1.5 font-semibold">{m.from}</code>→
              <select className="field field-sm ml-auto w-auto" defaultValue={m.to} aria-label={`${m.from} 매핑`}>
                {Object.entries(AREA_LABEL).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </li>
          ))}
        </ul>
      </Section>
    </SettingsShell>
  );
}

/* ------------------------------------------------------------------ /settings/availability */

const AVAIL_DEFAULT = { eveningFrom: "19:00", eveningTo: "23:00", useGaps: true, lunch: true, buffer: 10, blockMin: 30, blockMax: 120, dailyCap: 4, weekend: true };

export function AvailabilitySettings() {
  const toast = useToast();
  const [v, setV] = useStored("availability", AVAIL_DEFAULT);
  const set = <K extends keyof typeof AVAIL_DEFAULT>(k: K, val: (typeof AVAIL_DEFAULT)[K]) => setV((p) => ({ ...p, [k]: val }));
  return (
    <SettingsShell title="가용 시간" subtitle="공강 배치(F8)와 시험 공부 계획(F5)이 쓰는 시간 — 하루 상한은 두 기능이 같은 값을 씁니다">
      <Section title="언제 공부할 수 있나요">
        <Row label="저녁 시간대">
          <input type="time" className="field field-sm w-auto" aria-label="저녁 시작" value={v.eveningFrom} onChange={(e) => set("eveningFrom", e.target.value)} />
          <span className="text-muted">~</span>
          <input type="time" className="field field-sm w-auto" aria-label="저녁 끝" value={v.eveningTo} onChange={(e) => set("eveningTo", e.target.value)} />
        </Row>
        <Row label="수업 사이 공강 사용">
          <Toggle checked={v.useGaps} onChange={(x) => set("useGaps", x)} label="수업 사이 공강 사용" />
        </Row>
        <Row label="점심 제외" hint="12:00 ~ 13:00">
          <Toggle checked={v.lunch} onChange={(x) => set("lunch", x)} label="점심 제외" />
        </Row>
        <Row label="주말 사용">
          <Toggle checked={v.weekend} onChange={(x) => set("weekend", x)} label="주말 사용" />
        </Row>
      </Section>
      <Section title="블록과 상한">
        <Row label="수업 앞뒤 여유">
          <select className="field field-sm w-auto" aria-label="여유" value={v.buffer} onChange={(e) => set("buffer", Number(e.target.value))}>
            {[0, 10, 15, 30].map((m) => (
              <option key={m} value={m}>
                {m}분
              </option>
            ))}
          </select>
        </Row>
        <Row label="블록 길이">
          <select className="field field-sm w-auto" aria-label="최소" value={v.blockMin} onChange={(e) => set("blockMin", Number(e.target.value))}>
            {[30, 60].map((m) => (
              <option key={m} value={m}>
                최소 {m}분
              </option>
            ))}
          </select>
          <select className="field field-sm w-auto" aria-label="최대" value={v.blockMax} onChange={(e) => set("blockMax", Number(e.target.value))}>
            {[60, 90, 120].map((m) => (
              <option key={m} value={m}>
                최대 {m / 60}시간
              </option>
            ))}
          </select>
        </Row>
        <Row label="하루 상한" hint="F5 시험 계획과 같은 값">
          <select className="field field-sm w-auto" aria-label="하루 상한" value={v.dailyCap} onChange={(e) => set("dailyCap", Number(e.target.value))}>
            {[2, 3, 4, 5, 6].map((h) => (
              <option key={h} value={h}>
                {h}시간
              </option>
            ))}
          </select>
        </Row>
      </Section>
      <Section title="자동 배치 블록 지우기">
        <p className="mb-3 text-[13px] text-muted">기간을 골라 자동으로 배치한 블록만 지웁니다. 내가 옮긴(고정) 블록과 완료한 블록은 남깁니다.</p>
        <button type="button" className="btn btn-danger btn-sm" onClick={() => toast("배치 API 연결 전입니다")}>
          자동 배치 블록 지우기
        </button>
      </Section>
    </SettingsShell>
  );
}

/* ------------------------------------------------------------------ /settings/notifications */

const NOTI_DEFAULT = { briefingOn: true, briefingAt: "08:00", keepDays: 30, notifyAt: "09:00", academic: [7, 3, 1], deadline: ["D-3", "D-1", "당일 아침"] };

export function NotificationSettings() {
  const [v, setV] = useStored("notification-settings", NOTI_DEFAULT);
  const toggle = <T,>(list: T[], x: T) => (list.includes(x) ? list.filter((y) => y !== x) : [...list, x]);
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
        <Row label="알림 기본 시각">
          <input type="time" className="field field-sm w-auto" aria-label="알림 기본 시각" value={v.notifyAt} onChange={(e) => setV((p) => ({ ...p, notifyAt: e.target.value }))} />
        </Row>
        <Row label="학사일정 (F1)">
          {[7, 3, 1].map((d) => (
            <button key={d} type="button" aria-pressed={v.academic.includes(d)} onClick={() => setV((p) => ({ ...p, academic: toggle(p.academic, d) }))} className={`btn btn-sm ${v.academic.includes(d) ? "border-primary bg-primary-soft text-primary" : ""}`}>
              D-{d}
            </button>
          ))}
        </Row>
        <Row label="과제 마감 (F6)" hint="마감이 09시 이전이면 3시간 전">
          {["D-3", "D-1", "당일 아침"].map((d) => (
            <button key={d} type="button" aria-pressed={v.deadline.includes(d)} onClick={() => setV((p) => ({ ...p, deadline: toggle(p.deadline, d) }))} className={`btn btn-sm ${v.deadline.includes(d) ? "border-primary bg-primary-soft text-primary" : ""}`}>
              {d}
            </button>
          ))}
        </Row>
      </Section>
      <p className="text-[12px] text-faint">모바일 알림(Web Push·메신저)은 추후 검토입니다(전역 결정 G2). 설정은 이 브라우저에 저장됩니다.</p>
    </SettingsShell>
  );
}
