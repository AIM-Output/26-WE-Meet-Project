"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { ChevronRight, CircleCheck, CircleHelp, Download, GraduationCap, Plus, Square, Trash2 } from "lucide-react";
import { Page, PageHeader, Section } from "@/components/ui/Layout";
import { Tabs } from "@/components/ui/Tabs";
import { Banner, DemoNotice } from "@/components/ui/Feedback";
import { Chip, StatusBadge } from "@/components/ui/Chip";
import { Donut, ProgressBar } from "@/components/ui/Progress";
import { Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { closeQuery, navigateQuery, useQueryParam, useQueryValue } from "@/lib/useQueryState";
import {
  AREA_LABEL,
  demoAreaCourses,
  demoCertifications,
  demoGradCourses,
  demoGradStatus,
  TRACK_LABEL,
  type AreaKey,
  type Certification,
  type GradCourse,
  type Track,
} from "@/lib/demo";

// /graduation — 요약 / 이수 과목 / 가정 계산 (Frontend-Route 7절). 계산은 백엔드 규칙 코드만 한다 — 화면에 규칙을 복제하지 않는다.

const TABS = ["summary", "courses", "whatif"] as const;
const TRACKS = ["single", "double", "minor"] as const;
const FILTERS = ["all", "unmapped", "manual"] as const;
const AREAS = Object.keys(AREA_LABEL) as AreaKey[];

export default function GraduationPage() {
  const [tab, setTab] = useQueryParam("tab", "summary", TABS);
  const [track, setTrack] = useQueryParam<Track>("track", "single", TRACKS);
  const area = useQueryValue("area") as AreaKey | null;
  const newCourse = useQueryValue("new") === "course";
  const [courses, setCourses] = useState<GradCourse[]>(demoGradCourses);
  const unmapped = courses.filter((c) => c.area === null && !c.excluded).length;
  const s = demoGradStatus;
  const verdict = unmapped ? "확인 필요" : s.verdict;

  return (
    <Page>
      <PageHeader
        icon={<GraduationCap />}
        title="졸업요건"
        actions={
          <>
            <label className="sr-only" htmlFor="track">
              이수유형
            </label>
            <select id="track" className="field field-sm w-auto" value={track} onChange={(e) => setTrack(e.target.value as Track)}>
              {TRACKS.map((t) => (
                <option key={t} value={t}>
                  {s.ruleset.year} 입학 · {s.ruleset.dept} · {TRACK_LABEL[t]}
                </option>
              ))}
            </select>
            <Link href="/settings/requirements" className="btn btn-sm">
              기준 보기
            </Link>
          </>
        }
      />

      <div className="mb-5 space-y-3">
        <DemoNotice what="졸업요건" />
        <Banner tone="neutral">참고용입니다. 최종 확인은 학과 사무실·학사정보시스템에서 하세요.</Banner>
        {unmapped > 0 && (
          <Banner
            tone="warn"
            action={
              <button type="button" className="btn btn-sm" onClick={() => navigateQuery({ tab: "courses", filter: "unmapped" }, "replace")}>
                지정하기
              </button>
            }
          >
            분류하지 못한 과목 {unmapped}건 — 지정해야 정확해집니다
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
          { key: "courses", label: "이수 과목", count: courses.length },
          { key: "whatif", label: "가정 계산" },
        ]}
      />

      {tab === "summary" && (
        <div className="space-y-4">
          <Section>
            <div className="flex flex-col items-center gap-6 md:flex-row">
              <Donut value={s.total.earned} max={s.total.required} size={148}>
                <span className="num text-[28px] font-bold">{Math.round((s.total.earned / s.total.required) * 100)}%</span>
                <span className="num text-[13px] text-muted">
                  {s.total.earned}/{s.total.required}
                </span>
              </Donut>
              <div className="flex-1 text-center md:text-left">
                <p className="text-[14px] text-muted">졸업까지</p>
                <p className="num text-[36px] leading-tight font-bold">{s.total.required - s.total.earned} 학점</p>
                <p className="mt-1 text-[14px] text-muted">전공필수 2과목 · 핵심교양 3학점</p>
                <p className="mt-1 text-[14px]">
                  평점 <b className="num">{s.gpa.value}</b> / 최저 {s.gpa.min} <CircleCheck className="inline size-4 text-ok" aria-label="충족" />
                </p>
              </div>
              <div className="text-center">
                <p className="mb-1 text-[13px] text-muted">판정</p>
                <StatusBadge tone={verdict === "충족" ? "ok" : verdict === "확인 필요" ? "warn" : "accent"}>{verdict}</StatusBadge>
              </div>
            </div>
          </Section>

          <Section title="영역별">
            <ul className="divide-y divide-border">
              {s.areas.map((a) => {
                const ok = a.earned >= a.required;
                return (
                  <li key={a.key}>
                    <button
                      type="button"
                      className="grid w-full grid-cols-[88px_1fr_auto] items-center gap-3 py-3 text-left hover:bg-surface-2 md:grid-cols-[100px_1fr_120px_120px_20px] md:px-2"
                      onClick={() => navigateQuery({ area: a.key }, "push")}
                    >
                      <span className="text-[14px] font-semibold">{a.label}</span>
                      <ProgressBar value={a.earned} max={a.required || a.earned} tone={ok ? "ok" : "primary"} label={`${a.label} ${a.earned}/${a.required}`} />
                      <span className="num text-right text-[14px]">
                        {a.earned}/{a.required}
                      </span>
                      <span className="hidden text-[13px] md:block">
                        {ok ? <StatusBadge tone="ok">충족</StatusBadge> : <span className="text-accent-text">부족 {a.required - a.earned}{a.remainingCourses ? ` (남은 과목 ${a.remainingCourses})` : ""}</span>}
                      </span>
                      <ChevronRight className="hidden size-4 text-faint md:block" aria-hidden />
                    </button>
                  </li>
                );
              })}
            </ul>
          </Section>

          <Section title="졸업인증">
            <CertList />
          </Section>
        </div>
      )}

      {tab === "courses" && <CourseTable courses={courses} setCourses={setCourses} />}
      {tab === "whatif" && <WhatIf />}

      <Modal open={!!area} onClose={() => closeQuery(["area"])} title={area ? `${AREA_LABEL[area]}에 들어간 과목` : ""} size="sm">
        {area && (
          <ul className="space-y-1 pt-1">
            {demoAreaCourses[area].map((c) => (
              <li key={c} className="rounded-lg bg-surface-2 px-3 py-2 text-[14px]">
                {c}
              </li>
            ))}
          </ul>
        )}
      </Modal>
      <AddCourseModal open={newCourse} onAdd={(c) => setCourses((xs) => [...xs, c])} />
    </Page>
  );
}

function CertList() {
  const [items, setItems] = useState<Certification[]>(demoCertifications);
  const icon = (st: Certification["state"]) =>
    st === "done" ? <CircleCheck className="size-5 text-ok" aria-label="충족" /> : st === "unknown" ? <CircleHelp className="size-5 text-warn" aria-label="모름" /> : <Square className="size-5 text-faint" aria-label="미충족" />;
  return (
    <ul className="divide-y divide-border">
      {items.map((c) => (
        <li key={c.id} className="flex flex-wrap items-center gap-3 py-3">
          <button
            type="button"
            onClick={() => setItems((xs) => xs.map((x) => (x.id === c.id ? { ...x, state: x.state === "done" ? "todo" : "done" } : x)))}
            aria-label={`${c.label} 충족 여부 바꾸기`}
          >
            {icon(c.state)}
          </button>
          <span className="text-[14px] font-semibold">{c.label}</span>
          <span className="text-[13px] text-muted">{c.note}</span>
          <span className="ml-auto">
            {c.state === "todo" && <button type="button" className="btn btn-sm">기록하기</button>}
            {c.state === "unknown" && <Chip tone="warn" square>확인 필요</Chip>}
          </span>
        </li>
      ))}
    </ul>
  );
}

function CourseTable({ courses, setCourses }: { courses: GradCourse[]; setCourses: React.Dispatch<React.SetStateAction<GradCourse[]>> }) {
  const toast = useToast();
  const [filter, setFilter] = useQueryParam("filter", "all", FILTERS);
  const [busy, setBusy] = useState(false);
  const shown = courses.filter((c) => (filter === "unmapped" ? c.area === null : filter === "manual" ? c.source === "manual" : true));
  const terms = useMemo(() => {
    const m = new Map<string, GradCourse[]>();
    for (const c of shown) m.set(`${c.year}-${c.term}`, [...(m.get(`${c.year}-${c.term}`) ?? []), c]);
    return [...m.entries()];
  }, [shown]);

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
            { key: "unmapped", label: "미분류", count: courses.filter((c) => c.area === null).length },
            { key: "manual", label: "직접 입력" },
          ]}
        />
        <div className="ml-auto flex gap-2">
          <button
            type="button"
            className="btn btn-sm"
            disabled={busy}
            onClick={() => {
              setBusy(true);
              window.setTimeout(() => {
                setBusy(false);
                toast("이수 내역 수집 API 가 아직 없습니다 — 예시 데이터를 보여 줍니다");
              }, 900);
            }}
          >
            {busy ? <span className="spin spin-dark" aria-hidden /> : <Download aria-hidden />}
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
            <h3 className="num mb-2 text-[13px] font-bold text-muted">{k.replace("-", "년 ")}학기</h3>
            <div className="overflow-hidden rounded-xl border border-border bg-surface">
              <table className="w-full text-[14px]">
                <thead className="bg-surface-2 text-left text-[12px] text-muted max-md:hidden">
                  <tr>
                    <th className="px-4 py-2 font-semibold">과목</th>
                    <th className="w-16 px-2 py-2 font-semibold">학점</th>
                    <th className="w-16 px-2 py-2 font-semibold">성적</th>
                    <th className="w-40 px-2 py-2 font-semibold">구분</th>
                    <th className="w-12" />
                  </tr>
                </thead>
                <tbody>
                  {list.map((c) => (
                    <tr key={c.id} className={`border-t border-border first:border-t-0 max-md:flex max-md:flex-wrap max-md:items-center max-md:gap-2 max-md:px-4 max-md:py-2 ${c.area === null ? "bg-warn-soft/50" : ""}`}>
                      <td className="px-4 py-2 font-medium max-md:w-full max-md:p-0">
                        {c.name}
                        {c.source === "manual" && (
                          <Chip tone="primary" square className="ml-2">
                            직접 입력
                          </Chip>
                        )}
                      </td>
                      <td className="num px-2 py-2 max-md:p-0">{c.credits}학점</td>
                      <td className="num px-2 py-2 max-md:p-0">{c.grade}</td>
                      <td className="px-2 py-2 max-md:p-0">
                        <label className="sr-only" htmlFor={`area-${c.id}`}>
                          {c.name} 구분
                        </label>
                        <select
                          id={`area-${c.id}`}
                          className="field field-sm"
                          value={c.area ?? ""}
                          aria-invalid={c.area === null}
                          onChange={(e) => {
                            setCourses((xs) => xs.map((x) => (x.id === c.id ? { ...x, area: (e.target.value || null) as AreaKey | null } : x)));
                            toast("구분을 바꿨습니다 — 요약 숫자가 다시 계산됩니다");
                          }}
                        >
                          <option value="">미분류</option>
                          {AREAS.map((a) => (
                            <option key={a} value={a}>
                              {AREA_LABEL[a]}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="px-2 py-2 max-md:ml-auto max-md:p-0">
                        {c.source === "manual" && (
                          <button type="button" className="btn btn-ghost btn-icon btn-sm" aria-label={`${c.name} 삭제`} onClick={() => setCourses((xs) => xs.filter((x) => x.id !== c.id))}>
                            <Trash2 aria-hidden />
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ))}
        {terms.length === 0 && <p className="rounded-xl border border-dashed border-border-strong px-4 py-8 text-center text-[14px] text-muted">해당하는 과목이 없습니다</p>}
      </div>
    </div>
  );
}

function AddCourseModal({ open, onAdd }: { open: boolean; onAdd: (c: GradCourse) => void }) {
  const [name, setName] = useState("");
  const [credits, setCredits] = useState(3);
  const [area, setArea] = useState<AreaKey>("major_elective");
  const close = () => closeQuery(["new"]);
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
          <button
            type="button"
            className="btn btn-primary"
            disabled={!name.trim()}
            onClick={() => {
              onAdd({ id: `m${Date.now()}`, year: 2026, term: "2", name: name.trim(), credits, grade: "-", area, source: "manual" });
              setName("");
              close();
            }}
          >
            추가
          </button>
        </>
      }
    >
      <div className="space-y-4 pt-1">
        <div>
          <label className="label" htmlFor="cn">
            과목명
          </label>
          <input id="cn" data-autofocus className="field" value={name} onChange={(e) => setName(e.target.value)} placeholder="예) 교내 AI 캠프(학점인정)" />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label" htmlFor="cc">
              학점
            </label>
            <input id="cc" type="number" min={1} max={6} className="field" value={credits} onChange={(e) => setCredits(Number(e.target.value))} />
          </div>
          <div>
            <label className="label" htmlFor="ca">
              구분
            </label>
            <select id="ca" className="field" value={area} onChange={(e) => setArea(e.target.value as AreaKey)}>
              {AREAS.map((a) => (
                <option key={a} value={a}>
                  {AREA_LABEL[a]}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>
    </Modal>
  );
}

function WhatIf() {
  const [add, setAdd] = useState<Record<string, number>>({ major_required: 6, major_elective: 6, core_liberal: 3 });
  const total = Object.values(add).reduce((a, b) => a + b, 0);
  const s = demoGradStatus;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Section title="가정을 넣어 보세요" action={<span className="text-[12px] text-faint">과목을 추천하지는 않습니다</span>}>
        <ul className="space-y-3">
          {s.areas.slice(0, 3).map((a) => (
            <li key={a.key} className="flex items-center gap-3">
              <span className="w-20 text-[14px] font-semibold">{a.label}</span>
              <span className="text-[14px] text-muted">+</span>
              <input
                type="number"
                min={0}
                max={30}
                aria-label={`${a.label} 추가 학점`}
                className="field field-sm w-20"
                value={add[a.key] ?? 0}
                onChange={(e) => setAdd((m) => ({ ...m, [a.key]: Number(e.target.value) }))}
              />
              <span className="text-[14px] text-muted">학점</span>
            </li>
          ))}
        </ul>
      </Section>
      <Section title="현재 → 가정 후" action={<Chip square>예시 계산</Chip>}>
        <table className="w-full text-[14px]">
          <tbody className="divide-y divide-border">
            <tr>
              <th className="py-2 text-left font-medium text-muted">총 학점</th>
              <td className="num py-2">
                {s.total.earned}/{s.total.required}
              </td>
              <td className="num py-2 font-bold text-primary">
                {s.total.earned + total}/{s.total.required}
              </td>
            </tr>
            <tr>
              <th className="py-2 text-left font-medium text-muted">남은 학점</th>
              <td className="num py-2">{s.total.required - s.total.earned}</td>
              <td className="num py-2 font-bold text-primary">{Math.max(0, s.total.required - s.total.earned - total)}</td>
            </tr>
            <tr>
              <th className="py-2 text-left font-medium text-muted">전공필수</th>
              <td className="py-2">2과목 남음</td>
              <td className="py-2 font-bold text-primary">{(add.major_required ?? 0) >= 6 ? "모두 충족" : "부족"}</td>
            </tr>
          </tbody>
        </table>
        <p className="hint">실제 계산은 백엔드 POST /api/graduation/simulate 한 곳에서만 합니다.</p>
        <div className="mt-4 flex justify-end gap-2">
          <button type="button" className="btn btn-sm" onClick={() => setAdd({})}>
            초기화
          </button>
          <button type="button" className="btn btn-primary btn-sm">
            내 계획으로 저장
          </button>
        </div>
      </Section>
    </div>
  );
}
