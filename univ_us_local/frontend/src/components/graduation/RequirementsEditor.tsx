"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Copy, Download, ExternalLink, Plus, RotateCcw, Save, Trash2, X } from "lucide-react";
import { Section, Toggle } from "@/components/ui/Layout";
import { Banner, ErrorPanel, SkeletonCards } from "@/components/ui/Feedback";
import { Chip } from "@/components/ui/Chip";
import { Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { useAppData } from "@/components/app/AppData";
import { useProfile } from "@/lib/useProfile";
import { closeQuery, navigateQuery, useQueryParam, useQueryValue } from "@/lib/useQueryState";
import { api } from "@/lib/api";
import { TRACK_LABEL, type Track } from "@/lib/profile";
import { LEVEL_TONE, num, type CategoryView, type CurriculumState, type RequiredCourse, type RulesetArea, type RulesetDoc, type RulesetView } from "@/lib/graduation";

// /settings/requirements — 졸업요건 기준(룰셋) 보기·수정 (F2-S10·S11, Frontend-Route 7-6).
// 값마다 근거를 옆에 둔다(F2-R12). 저장하면 '내 수정본'이 되고 기본 룰셋 파일은 건드리지 않는다(F2-R13).

const TRACKS = ["single", "double", "minor"] as const;
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x)) as T;
const msg = (e: unknown) => (e instanceof Error ? e.message : String(e));

export function RequirementsEditor() {
  const toast = useToast();
  const router = useRouter();
  const { refresh } = useAppData();
  const { profile } = useProfile();
  const yearQ = useQueryValue("year");
  const [track, setTrack] = useQueryParam<Track>("track", (profile?.track as Track) ?? "single", TRACKS);
  const copyOpen = useQueryValue("copy") === "1";
  const year = yearQ && /^\d{4}$/.test(yearQ) ? Number(yearQ) : (profile?.admissionYear ?? null);

  const [view, setView] = useState<RulesetView | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [draft, setDraft] = useState<RulesetDoc | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);

  const accept = useCallback((v: RulesetView) => {
    setView(v);
    setDraft(clone(v.editable));
    setDirty(false);
    setErr(null);
  }, []);

  const load = useCallback(async () => {
    try {
      accept(await api.ruleset({ year, track }));
    } catch (e) {
      setErr(msg(e));
    }
  }, [year, track, accept]);

  useEffect(() => {
    void Promise.resolve().then(load);
  }, [load]);

  const edit = (f: (d: RulesetDoc) => void) => {
    setDraft((d) => {
      if (!d) return d;
      const n = clone(d);
      f(n);
      return n;
    });
    setDirty(true);
  };

  const save = async () => {
    if (!draft || !view) return;
    setSaving(true);
    try {
      accept(await api.putRuleset(draft, { admissionYear: view.target.admissionYear, track }));
      void refresh();
      toast("저장했습니다 — 내 수정본으로 졸업요건을 다시 계산합니다", { tone: "success", action: { label: "졸업요건 보기", onClick: () => router.push("/graduation") } });
    } catch (e) {
      toast(`저장하지 못했습니다: ${msg(e)}`, { tone: "error" });
    } finally {
      setSaving(false);
    }
  };

  const reset = async () => {
    setConfirmReset(false);
    try {
      accept(await api.resetRuleset({ year: view?.target.admissionYear, track }));
      void refresh();
      toast("기본값으로 되돌렸습니다");
    } catch (e) {
      toast(`되돌리지 못했습니다: ${msg(e)}`, { tone: "error" });
    }
  };

  if (!view || !draft) return err ? <ErrorPanel message={`기준을 불러오지 못했습니다 — ${err}`} onRetry={() => void load()} /> : <SkeletonCards count={3} />;

  const resolvedArea = (key: string) => view.ruleset?.areas.find((a) => a.key === key);
  const areaCourses = (a: RulesetArea): RequiredCourse[] | null => a.courses ?? (a.coursesFrom ? (resolvedArea(a.key)?.courses ?? []) : null);
  const setCourses = (i: number, list: RequiredCourse[]) =>
    edit((d) => {
      const a = d.areas[i];
      a.courses = list.map(({ code, name, credits }) => ({ code, name, credits }));
      a.coursesSource = "ruleset";
      delete a.coursesFrom;
    });
  const years = Array.from({ length: new Date().getFullYear() + 2 - 2015 }, (_, i) => 2015 + i);
  const noProfile = !view.target.deptCode;

  return (
    <div className="space-y-5">
      <Section
        title={view.target.label}
        action={
          <span className="flex flex-wrap items-center gap-1.5">
            <Chip tone={LEVEL_TONE[view.level]} square>
              {view.levelLabel}
            </Chip>
            {view.edited && (
              <Chip tone="accent" square>
                사용자 수정
              </Chip>
            )}
            {view.ruleset?.verified && (view.level === "exact" || view.level === "dept") && (
              <Chip tone="ok" square>
                검수한 기본값
              </Chip>
            )}
          </span>
        }
      >
        <div className="flex flex-wrap items-center gap-2">
          <label className="text-[13px] text-muted" htmlFor="rq-year">
            입학년도
          </label>
          <select id="rq-year" className="field field-sm w-auto" value={year ?? ""} onChange={(e) => navigateQuery({ year: e.target.value || null }, "replace")}>
            {!year && <option value="">선택</option>}
            {years.map((y) => (
              <option key={y} value={y}>
                {y}
                {y === profile?.admissionYear ? " (내 입학년도)" : ""}
              </option>
            ))}
          </select>
          <label className="ml-2 text-[13px] text-muted" htmlFor="rq-track">
            이수유형
          </label>
          <select id="rq-track" className="field field-sm w-auto" value={track} onChange={(e) => setTrack(e.target.value as Track)}>
            {TRACKS.map((t) => (
              <option key={t} value={t}>
                {TRACK_LABEL[t]}
              </option>
            ))}
          </select>
          <Link href="/settings/profile" className="ml-auto text-[13px] font-semibold text-primary hover:underline">
            학과 바꾸기 →
          </Link>
        </div>
        <p className="mt-2 text-[13px] text-muted">
          지금 계산에 쓰는 기준: <b className="text-text">{view.label}</b>
          {view.base && view.edited && <span> · 원본 {view.base.label}</span>}
        </p>
        <div className="mt-3 space-y-2">
          {noProfile && (
            <Banner tone="primary" action={<Link href="/onboarding?step=1" className="btn btn-sm">입력하기</Link>}>
              프로필에 학과·입학년도가 없어 기준을 고를 수 없습니다
            </Banner>
          )}
          {view.warnings.map((w) => (
            <Banner key={w} tone="warn">
              {w}
            </Banner>
          ))}
          {view.baseChanged && <Banner tone="info">기본 기준이 새 판으로 바뀌었습니다 — &lsquo;기본값으로 되돌리기&rsquo;를 누르면 새 기준을 씁니다</Banner>}
          {view.isTemplate && !noProfile && (
            <Banner
              tone="warn"
              action={
                <button type="button" className="btn btn-sm" onClick={() => navigateQuery({ copy: "1" }, "push")}>
                  <Copy aria-hidden />
                  비슷한 학과에서 복사
                </button>
              }
            >
              이 학과·입학년도 기준이 아직 없습니다 — 학과 홈페이지의 &lsquo;졸업소요학점&rsquo; 표를 보고 아래를 채워 저장하면 바로 계산됩니다
            </Banner>
          )}
        </div>
      </Section>

      <Section title="졸업 학점 · 평점">
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="label" htmlFor="rq-total">
              졸업 학점
            </label>
            <input
              id="rq-total"
              type="number"
              min={1}
              max={300}
              className="field num w-32"
              value={draft.totalCredits ?? ""}
              onChange={(e) => edit((d) => (d.totalCredits = e.target.value === "" ? null : Number(e.target.value)))}
            />
            <input className="field field-sm mt-2" aria-label="졸업 학점 근거" placeholder="근거 (요람 쪽수·학칙 조항·URL)" value={draft.totalEvidence} onChange={(e) => edit((d) => (d.totalEvidence = e.target.value))} maxLength={300} />
          </div>
          <div>
            <label className="label" htmlFor="rq-gpa">
              최저 평점 <span className="font-normal text-faint">(없으면 비워 둠)</span>
            </label>
            <span className="flex items-center gap-2">
              <input
                id="rq-gpa"
                type="number"
                min={0}
                max={4.5}
                step={0.01}
                className="field num w-24"
                value={draft.minGpa?.value ?? ""}
                onChange={(e) => edit((d) => (d.minGpa = e.target.value === "" ? null : { value: Number(e.target.value), scale: d.minGpa?.scale ?? 4.5 }))}
              />
              <select
                className="field w-auto"
                aria-label="평점 만점"
                value={draft.minGpa?.scale ?? 4.5}
                disabled={!draft.minGpa}
                onChange={(e) => edit((d) => d.minGpa && (d.minGpa.scale = Number(e.target.value)))}
              >
                {[4.5, 4.3, 4.0].map((s) => (
                  <option key={s} value={s}>
                    / {s}
                  </option>
                ))}
              </select>
            </span>
            <input className="field field-sm mt-2" aria-label="최저 평점 근거" placeholder="근거" value={draft.minGpaEvidence} onChange={(e) => edit((d) => (d.minGpaEvidence = e.target.value))} maxLength={300} />
          </div>
        </div>
      </Section>

      <Section title="영역별 최소 학점" action={<span className="text-[12px] text-faint">초과분은 &lsquo;넘길 영역&rsquo;으로 한 번만 인정</span>}>
        <ul className="divide-y divide-border">
          {draft.areas.map((a, i) => {
            const list = areaCourses(a);
            return (
              <li key={a.key} className="space-y-2 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <input className="field field-sm w-28 font-semibold" aria-label={`${a.key} 이름`} value={a.label} onChange={(e) => edit((d) => (d.areas[i].label = e.target.value))} maxLength={20} />
                  <span className="flex items-baseline gap-1">
                    <input
                      type="number"
                      min={0}
                      max={200}
                      aria-label={`${a.label} 최소 학점`}
                      className="field field-sm num w-20"
                      value={a.minCredits}
                      onChange={(e) => edit((d) => (d.areas[i].minCredits = Number(e.target.value) || 0))}
                    />
                    <span className="text-[13px] text-faint">학점</span>
                  </span>
                  <label className="ml-2 text-[12px] text-muted" htmlFor={`of-${a.key}`}>
                    넘길 영역
                  </label>
                  <select
                    id={`of-${a.key}`}
                    className="field field-sm w-auto"
                    value={a.overflowTo ?? ""}
                    onChange={(e) =>
                      edit((d) => {
                        if (e.target.value) d.areas[i].overflowTo = e.target.value;
                        else delete d.areas[i].overflowTo;
                      })
                    }
                  >
                    <option value="">없음</option>
                    {draft.areas
                      .filter((x) => x.key !== a.key)
                      .map((x) => (
                        <option key={x.key} value={x.key}>
                          {x.label}
                        </option>
                      ))}
                  </select>
                  <code className="ml-auto text-[11px] text-faint">{a.key}</code>
                </div>
                <input className="field field-sm" aria-label={`${a.label} 근거`} placeholder="근거" value={a.evidence} onChange={(e) => edit((d) => (d.areas[i].evidence = e.target.value))} maxLength={300} />
                {list !== null && <CourseListEditor area={a} list={list} onChange={(l) => setCourses(i, l)} year={view.ruleset?.curriculum?.year ?? null} />}
              </li>
            );
          })}
        </ul>
      </Section>

      <Section
        title="졸업인증"
        action={
          <button
            type="button"
            className="btn btn-sm"
            onClick={() =>
              edit((d) => {
                let n = d.certifications.length + 1;
                while (d.certifications.some((c) => c.key === `cert${n}`)) n++;
                d.certifications.push({ key: `cert${n}`, label: "새 인증", detail: "", required: true, evidence: "" });
              })
            }
          >
            <Plus aria-hidden />
            인증 추가
          </button>
        }
      >
        {draft.certifications.length === 0 && <p className="text-[14px] text-muted">항목이 없습니다 (영어·봉사·캡스톤·졸업논문 등)</p>}
        <ul className="divide-y divide-border">
          {draft.certifications.map((c, i) => (
            <li key={c.key} className="space-y-2 py-3">
              <div className="flex flex-wrap items-center gap-2">
                <input className="field field-sm w-40 font-semibold" aria-label="인증 이름" value={c.label} onChange={(e) => edit((d) => (d.certifications[i].label = e.target.value))} maxLength={30} />
                <span className="flex items-center gap-2 text-[13px] text-muted">
                  필수
                  <Toggle checked={c.required} label={`${c.label} 필수`} onChange={(v) => edit((d) => (d.certifications[i].required = v))} />
                </span>
                <button type="button" className="btn btn-ghost btn-icon btn-sm ml-auto" aria-label={`${c.label} 삭제`} onClick={() => edit((d) => d.certifications.splice(i, 1))}>
                  <Trash2 aria-hidden />
                </button>
              </div>
              <textarea className="field min-h-[60px] text-[13px]" aria-label={`${c.label} 설명`} placeholder="기준 (예: TOEIC 600 이상)" value={c.detail} onChange={(e) => edit((d) => (d.certifications[i].detail = e.target.value))} maxLength={300} />
              <input className="field field-sm" aria-label={`${c.label} 근거`} placeholder="근거" value={c.evidence} onChange={(e) => edit((d) => (d.certifications[i].evidence = e.target.value))} maxLength={300} />
            </li>
          ))}
        </ul>
      </Section>

      {!!view.ruleset?.checks.length && (
        <Section title="대학 공통 조건" action={<span className="text-[12px] text-faint">입학년도에 따라 자동으로 붙습니다 · 여기서 고치지 않습니다</span>}>
          <ul className="grid gap-1 sm:grid-cols-2">
            {view.ruleset.checks.map((c) => (
              <li key={c.key} className="rounded-lg bg-surface-2 px-3 py-2 text-[13px]" title={c.evidence}>
                <b>{c.label}</b> {num(c.minCredits)}학점 이상
              </li>
            ))}
          </ul>
          {view.ruleset.commonSources?.map((s) => (
            <a key={s.id} href={s.url} target="_blank" rel="noopener noreferrer" className="mt-2 inline-flex items-center gap-1 text-[12px] text-primary hover:underline">
              {s.docName}
              <ExternalLink className="size-3" aria-hidden />
            </a>
          ))}
        </Section>
      )}

      {(draft.source?.url || draft.notes.length > 0) && (
        <Section title="근거·메모">
          {draft.source?.url && (
            <p className="text-[13px]">
              <a href={draft.source.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 font-semibold text-primary hover:underline">
                {draft.source.docName}
                <ExternalLink className="size-3" aria-hidden />
              </a>
              {draft.source.checkedAt && <span className="text-faint"> · {draft.source.checkedAt} 확인</span>}
            </p>
          )}
          <ul className="mt-2 space-y-1 text-[13px] text-muted">
            {draft.notes.map((n) => (
              <li key={n}>· {n}</li>
            ))}
          </ul>
        </Section>
      )}

      <div className="sticky bottom-4 z-10 flex flex-wrap items-center justify-end gap-2 rounded-xl border border-border bg-surface/95 px-4 py-3 shadow-sm backdrop-blur">
        {dirty && <span className="mr-auto text-[13px] font-semibold text-accent-text">저장하지 않은 변경이 있습니다</span>}
        {dirty && (
          <button type="button" className="btn btn-sm" onClick={() => accept(view)}>
            변경 취소
          </button>
        )}
        <button type="button" className="btn btn-sm" disabled={!view.edited} onClick={() => setConfirmReset(true)}>
          <RotateCcw aria-hidden />
          기본값으로 되돌리기
        </button>
        <button type="button" className="btn btn-primary btn-sm" disabled={!dirty || saving || noProfile} onClick={() => void save()}>
          <Save aria-hidden />
          {view.edited ? "저장" : "내 수정본으로 저장"}
        </button>
      </div>

      <CategoryMap key={`${view.editedAt}-${view.target.admissionYear}-${track}`} />
      <CurriculumPanel onDone={load} />

      <Modal
        open={confirmReset}
        onClose={() => setConfirmReset(false)}
        title="기본값으로 되돌릴까요?"
        size="sm"
        footer={
          <>
            <button type="button" className="btn" onClick={() => setConfirmReset(false)}>
              취소
            </button>
            <button type="button" className="btn btn-primary" onClick={() => void reset()}>
              되돌리기
            </button>
          </>
        }
      >
        <p className="text-[14px] text-muted">이 학과·입학년도·이수유형에 저장한 내 수정본을 지우고 기본 기준으로 계산합니다.</p>
      </Modal>
      <CopyModal
        open={copyOpen}
        view={view}
        onPick={async (id) => {
          try {
            const doc = await api.rulesetById(id);
            setDraft({ ...doc, id: doc.id });
            setDirty(true);
            closeQuery(["copy"]);
            toast("복사했습니다 — 값을 확인하고 저장하세요");
          } catch (e) {
            toast(`불러오지 못했습니다: ${msg(e)}`, { tone: "error" });
          }
        }}
      />
    </div>
  );
}

function CourseListEditor({ area, list, onChange, year }: { area: RulesetArea; list: RequiredCourse[]; onChange: (l: RequiredCourse[]) => void; year: number | null }) {
  const [adding, setAdding] = useState(false);
  const [f, setF] = useState({ code: "", name: "", credits: 3 });
  const fromCurriculum = !area.courses && !!area.coursesFrom;
  const total = list.reduce((s, c) => s + (c.credits || 0), 0);
  return (
    <div className="rounded-lg bg-surface-2 px-3 py-2">
      <p className="mb-1.5 flex flex-wrap items-center gap-2 text-[12px] text-muted">
        반드시 들을 과목 {list.length}개 · {num(total)}학점
        {fromCurriculum ? <Chip square>교육과정검색 {year ?? ""} &lsquo;{area.coursesFrom}&rsquo;</Chip> : <Chip tone="accent" square>직접 고친 목록</Chip>}
      </p>
      <ul className="flex flex-wrap gap-1.5">
        {list.map((c, i) => (
          <li key={c.code ?? c.name} className="inline-flex items-center gap-1 rounded-md border border-border bg-surface px-2 py-0.5 text-[12px]">
            {c.name}
            <span className="text-faint">{num(c.credits)}</span>
            <button type="button" className="text-faint hover:text-danger" aria-label={`${c.name} 빼기`} onClick={() => onChange(list.filter((_, j) => j !== i))}>
              <X className="size-3" aria-hidden />
            </button>
          </li>
        ))}
        {list.length === 0 && <li className="text-[12px] text-faint">{fromCurriculum ? "교육과정을 아직 받지 않았습니다 — 아래 '교육과정'에서 받으세요" : "없음"}</li>}
        <li>
          <button type="button" className="inline-flex h-6 items-center gap-1 rounded-md px-1.5 text-[12px] font-semibold text-primary hover:bg-primary-soft" onClick={() => setAdding((x) => !x)}>
            <Plus className="size-3" aria-hidden />
            과목
          </button>
        </li>
      </ul>
      {adding && (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <input className="field field-sm num w-28" placeholder="학수번호" aria-label="학수번호" value={f.code} onChange={(e) => setF((x) => ({ ...x, code: e.target.value }))} maxLength={20} />
          <input className="field field-sm w-44" placeholder="과목명" aria-label="과목명" value={f.name} onChange={(e) => setF((x) => ({ ...x, name: e.target.value }))} maxLength={80} />
          <input className="field field-sm num w-16" type="number" min={0} max={30} aria-label="학점" value={f.credits} onChange={(e) => setF((x) => ({ ...x, credits: Number(e.target.value) }))} />
          <button
            type="button"
            className="btn btn-sm"
            disabled={!f.name.trim()}
            onClick={() => {
              onChange([...list, { code: f.code.trim().toUpperCase() || null, name: f.name.trim(), credits: f.credits }]);
              setF({ code: "", name: "", credits: 3 });
              setAdding(false);
            }}
          >
            더하기
          </button>
        </div>
      )}
    </div>
  );
}

function CopyModal({ open, view, onPick }: { open: boolean; view: RulesetView; onPick: (id: string) => void }) {
  return (
    <Modal open={open} onClose={() => closeQuery(["copy"])} title="비슷한 학과에서 복사" size="sm">
      <p className="mb-3 text-[13px] text-muted">복사한 뒤 내 학과에 맞게 숫자를 고쳐 저장하세요. 과목 목록은 내 학과의 교육과정에서 다시 채웁니다.</p>
      {view.similar.length === 0 ? (
        <p className="text-[14px] text-muted">아직 복사할 기준이 없습니다</p>
      ) : (
        <ul className="space-y-1">
          {view.similar.map((s) => (
            <li key={s.id}>
              <button type="button" className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-[14px] hover:bg-surface-2" onClick={() => onPick(s.id)}>
                <span className="font-semibold">{[s.department, s.major].filter(Boolean).join(" ")}</span>
                <span className="text-muted">
                  {s.label} 입학 · {TRACK_LABEL[s.track]}
                </span>
                <span className="num ml-auto text-[12px] text-faint">{s.totalCredits}학점</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Modal>
  );
}

/** 교과구분 → 영역 매핑 (F2-R22). 학사시스템 구분 문자열마다 영역을 고른다 — 내 지정이 기본값보다 우선한다. */
function CategoryMap() {
  const toast = useToast();
  const [cv, setCv] = useState<CategoryView | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    void api
      .categories()
      .then(setCv)
      .catch((e) => setErr(msg(e)));
  }, []);
  const label = (k: string | null) => cv?.areas.find((a) => a.key === k)?.label ?? k ?? "미분류";
  return (
    <Section title="교과구분 매핑" action={<span className="text-[12px] text-faint">학사시스템 구분 → 영역 · 바꾸면 바로 다시 계산</span>}>
      {err && <Banner tone="danger">{err}</Banner>}
      {!cv ? (
        <p className="text-[14px] text-muted">불러오는 중…</p>
      ) : (
        <ul className="grid gap-2 sm:grid-cols-2">
          {cv.rows.map((r) => (
            <li key={r.raw} className={`flex items-center gap-2 rounded-lg px-3 py-2 text-[14px] ${r.area ? "bg-surface-2" : "bg-warn-soft/60"}`}>
              <code className="rounded bg-surface px-1.5 font-semibold">{r.raw}</code>
              {r.courses > 0 && <span className="text-[11px] text-faint">내 과목 {r.courses}</span>}
              {r.mine && (
                <Chip tone="accent" square>
                  내 지정
                </Chip>
              )}
              <select
                className="field field-sm ml-auto w-auto"
                aria-label={`${r.raw} 영역`}
                value={r.mine ?? ""}
                onChange={async (e) => {
                  try {
                    setCv(await api.putCategory(r.raw, e.target.value || null));
                    toast(`'${r.raw}' → ${label(e.target.value || r.base)}`);
                  } catch (x) {
                    toast(`바꾸지 못했습니다: ${msg(x)}`, { tone: "error" });
                  }
                }}
              >
                <option value="">{r.base ? `기본 · ${label(r.base)}` : "미분류"}</option>
                {cv.areas.map((a) => (
                  <option key={a.key} value={a.key}>
                    {a.label}
                  </option>
                ))}
              </select>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

/** 교육과정(과목 목록) 스냅숏 — 없으면 받기 (F2-R16) */
function CurriculumPanel({ onDone }: { onDone: () => Promise<void> }) {
  const toast = useToast();
  const [st, setSt] = useState<CurriculumState | null>(null);
  const [running, setRunning] = useState(false);
  useEffect(() => {
    void api
      .curriculum()
      .then(setSt)
      .catch(() => {});
  }, []);
  if (!st || !st.codes.length) return null;
  const start = async () => {
    setRunning(true);
    try {
      let s = await api.syncCurriculum();
      for (let i = 0; i < 60 && s.running; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        s = (await api.curriculum()).sync;
      }
      const cur = await api.curriculum();
      setSt(cur);
      if (s.ok) {
        await onDone();
        toast(`교육과정을 받았습니다 — ${s.result?.codes.map((c) => `${c.code} ${c.count}과목`).join(", ")}`, { tone: "success" });
      } else toast(`받지 못했습니다: ${s.error ?? "알 수 없는 오류"}`, { tone: "error" });
    } catch (e) {
      toast(`받지 못했습니다: ${msg(e)}`, { tone: "error" });
    } finally {
      setRunning(false);
    }
  };
  return (
    <Section
      title="교육과정 (과목 목록)"
      action={
        <button type="button" className="btn btn-sm" disabled={running} onClick={() => void start()}>
          {running ? <span className="spin spin-dark" aria-hidden /> : <Download aria-hidden />}
          {st.missing.length ? "교육과정 받기" : "다시 받기"}
        </button>
      }
    >
      <p className="text-[13px] text-muted">
        {st.year}학년도 교육과정검색에서 학부·전공 과목 목록을 받아 전공필수·교양필수 &lsquo;남은 과목&rsquo;을 셉니다. 공개 페이지라 로그인이 필요 없습니다.
      </p>
      <ul className="mt-2 flex flex-wrap gap-2 text-[13px]">
        {st.codes.map((c) => (
          <li key={c}>
            <Chip tone={st.have.includes(c) ? "ok" : "warn"} square>
              {c} · {st.have.includes(c) ? "있음" : "없음"}
            </Chip>
          </li>
        ))}
      </ul>
    </Section>
  );
}
