"use client";

import Link from "next/link";
import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { BookOpen, ChevronDown, ChevronRight, FileText, Lock, Play, Plus, Send, ShieldCheck, Trash2, Upload } from "lucide-react";
import { Page, PageHeader, Section } from "@/components/ui/Layout";
import { Tabs } from "@/components/ui/Tabs";
import { Banner, DemoNotice, EmptyState } from "@/components/ui/Feedback";
import { Chip, EvidenceChip, StatusBadge } from "@/components/ui/Chip";
import { Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { useAppData } from "@/components/app/AppData";
import { useStored } from "@/lib/storage";
import { closeQuery, navigateQuery, useQueryParam, useQueryValue } from "@/lib/useQueryState";
import { demoAskThread, demoMaterialCounts, demoMaterials, demoQuestions, demoSummaries, type Citation, type Material } from "@/lib/demo";

// /courses — 과목 목록, /courses?course=<id> — 자료 / 요약 / 문제 / 질문 (Frontend-Route 9절).
// 근거 없는 요약·문제는 내보내지 않는다 — 모든 생성물에 `[p.12]` 근거 칩(CitationChip)이 붙는다.

const TABS = ["materials", "summary", "questions", "ask"] as const;

const openCite = (c: Citation) => navigateQuery({ file: c.file, page: String(c.page) }, "push");
export function CitationChip({ c }: { c: Citation }) {
  return <EvidenceChip label={`p.${c.page}`} title={`${c.fileName} ${c.page}쪽`} onClick={() => openCite(c)} />;
}

export default function CoursesPage() {
  const courseId = useQueryValue("course");
  return (
    <Page>
      {courseId ? <CourseDetail id={courseId} /> : <CourseList />}
      <ConsentGate />
      <SourceViewer />
      <QuizRunner />
    </Page>
  );
}

function CourseList() {
  const { courses, loading } = useAppData();
  return (
    <>
      <PageHeader icon={<BookOpen />} title="강의자료" subtitle="과목을 고르면 자료·요약·예상 문제·질문을 볼 수 있습니다" />
      <div className="mb-5">
        <DemoNotice what="강의자료 분석(자료 수·요약·문제)" />
      </div>
      {!loading && courses.length === 0 ? (
        <EmptyState icon={<BookOpen />} title="강의자료가 없습니다" action={<Link href="/settings/sources" className="btn btn-sm">e클래스 동기화</Link>}>
          e클래스 동기화 또는 파일 추가로 자료를 모으세요
        </EmptyState>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {courses.map((c) => {
            const n = demoMaterialCounts[c.id] ?? { files: 0, ready: 0 };
            return (
              <li key={c.id}>
                <button
                  type="button"
                  onClick={() => navigateQuery({ course: c.id }, "push")}
                  className="card card-hover flex h-full w-full flex-col gap-3 p-4 text-left hover:bg-surface-2"
                >
                  <span className="flex items-center gap-2">
                    <span className="size-2.5 flex-none rounded-full" style={{ background: c.color }} aria-hidden />
                    <span className="truncate text-[15px] font-bold">{c.short}</span>
                    <span className="ml-auto text-[12px] text-faint">{c.code}</span>
                  </span>
                  <span className="flex items-center gap-2 text-[13px] text-muted">
                    <FileText className="size-4" aria-hidden />
                    자료 <b className="num text-text">{n.files}</b>
                    {n.files > 0 && (
                      <Chip tone={n.ready === n.files ? "ok" : "warn"} square>
                        {n.ready === n.files ? "준비됨" : `분석 중 ${n.ready}/${n.files}`}
                      </Chip>
                    )}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}

const STATE_BADGE: Record<Material["state"], { tone: "ok" | "info" | "neutral" | "danger" | "warn"; label: (m: Material) => string }> = {
  ready: { tone: "ok", label: () => "준비됨" },
  indexing: { tone: "info", label: (m) => `분석 중 (${m.progress?.[0]}/${m.progress?.[1]})` },
  queued: { tone: "neutral", label: () => "대기" },
  failed: { tone: "danger", label: () => "실패" },
  notext: { tone: "warn", label: () => "텍스트 없는 PDF" },
};

function CourseDetail({ id }: { id: string }) {
  const { courses } = useAppData();
  const [consent] = useStored("f4-consent", false);
  const [rawTab, setTab] = useQueryParam("tab", "materials", TABS);
  const tab = consent ? rawTab : "materials"; // 동의 전에는 분석 탭이 잠긴다
  const course = courses.find((c) => c.id === id);
  const materials = demoMaterials.filter((m) => m.courseId === id);
  const hasDemo = materials.length > 0;
  const indexing = materials.some((m) => m.state === "indexing" || m.state === "queued");

  return (
    <>
      <PageHeader
        icon={<BookOpen />}
        title={course ? course.short : "과목"}
        subtitle={course?.code}
        actions={
          <button type="button" className="btn btn-sm" onClick={() => navigateQuery({ course: null, tab: null }, "replace")}>
            과목 목록
          </button>
        }
      />
      <div className="mb-5 space-y-3">
        <DemoNotice what="강의자료 분석" />
        {!consent && (
          <Banner tone="warn" icon={<Lock aria-hidden />}>
            동의 전에는 분석·생성 기능이 잠깁니다. 자료 목록과 원문은 계속 볼 수 있습니다.
          </Banner>
        )}
      </div>
      <Tabs
        className="mb-5"
        label="강의자료 보기"
        value={tab}
        onChange={(t) => setTab(t)}
        items={[
          { key: "materials", label: "자료", count: materials.length },
          { key: "summary", label: "요약", disabled: !consent },
          { key: "questions", label: "문제", disabled: !consent },
          { key: "ask", label: "질문", disabled: !consent },
        ]}
      />
      {!hasDemo ? (
        <EmptyState icon={<FileText />} title="예시 자료가 있는 과목은 소프트웨어공학론입니다">
          <button type="button" className="font-semibold text-primary underline" onClick={() => navigateQuery({ course: "74261" }, "replace")}>
            소프트웨어공학론[1] 열기
          </button>
        </EmptyState>
      ) : tab === "materials" ? (
        <MaterialList materials={materials} />
      ) : (
        <>
          {indexing && (
            <Banner tone="info" className="mb-4">
              자료를 준비하는 중입니다 ({materials.filter((m) => m.state === "ready").length}/{materials.length}) — 준비된 자료만 반영됩니다
            </Banner>
          )}
          {tab === "summary" ? <SummaryTab /> : tab === "questions" ? <QuestionsTab /> : <AskTab />}
        </>
      )}
    </>
  );
}

function MaterialList({ materials }: { materials: Material[] }) {
  const toast = useToast();
  const [over, setOver] = useState(false);
  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        toast(`${e.dataTransfer.files.length}개 파일 — 업로드 API 연결 전이라 대기열에 넣지 않았습니다`);
      }}
      className={`rounded-xl transition-colors ${over ? "bg-primary-soft ring-2 ring-primary" : ""}`}
    >
      <div className="mb-3 flex justify-end">
        <label className="btn btn-primary btn-sm cursor-pointer">
          <Upload aria-hidden />
          파일 추가
          <input type="file" accept="application/pdf" multiple className="sr-only" onChange={(e) => toast(`${e.target.files?.length ?? 0}개 파일 — 업로드 API 연결 전`)} />
        </label>
      </div>
      <ul className="overflow-hidden rounded-xl border border-border bg-surface">
        {materials.map((m) => {
          const b = STATE_BADGE[m.state];
          return (
            <li key={m.id} className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3 last:border-b-0">
              <FileText className="size-5 flex-none text-faint" aria-hidden />
              <button type="button" className="min-w-0 flex-1 text-left" onClick={() => navigateQuery({ file: m.id, page: "1" }, "push")}>
                <span className="block truncate text-[14px] font-semibold hover:text-primary">{m.name}</span>
                <span className="text-[12px] text-faint">
                  {m.pages ? `${m.pages}쪽` : "—"} · {m.origin === "eclass" ? "e클래스" : "직접 추가"} · {m.week}주차
                </span>
              </button>
              <StatusBadge tone={b.tone}>{b.label(m)}</StatusBadge>
              {m.origin === "upload" ? (
                <button type="button" className="btn btn-ghost btn-icon btn-sm" aria-label={`${m.name} 삭제`}>
                  <Trash2 aria-hidden />
                </button>
              ) : (
                <span className="size-8" title="e클래스 수집분은 원본이 그쪽이라 삭제할 수 없습니다">
                  <Lock className="m-auto mt-2 size-3.5 text-faint" aria-label="삭제 잠김" />
                </span>
              )}
            </li>
          );
        })}
      </ul>
      <p className="hint text-center">파일을 이 영역에 끌어다 놓아도 추가됩니다</p>
    </div>
  );
}

function SummaryTab() {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <select className="field field-sm w-auto" aria-label="범위" defaultValue="all">
          <option value="all">전체</option>
          <option value="3-7">3~7주차</option>
          <option value="mid">중간고사 범위</option>
        </select>
        <button type="button" className="btn btn-primary btn-sm ml-auto">
          요약 만들기
        </button>
      </div>
      {demoSummaries.map((s) => (
        <Section key={s.fileId} title={s.fileName} icon={<FileText />}>
          <div className="space-y-4">
            {s.sections.map((sec) => (
              <div key={sec.heading}>
                <h4 className="mb-2 text-[14px] font-bold">{sec.heading}</h4>
                <ul className="space-y-2">
                  {sec.points.map((p) => (
                    <li key={p.text} className="flex flex-wrap items-start gap-2 text-[14px]">
                      <span className="mt-2 size-1 flex-none rounded-full bg-faint" aria-hidden />
                      <span className="min-w-0 flex-1">{p.text}</span>
                      <span className="flex gap-1">
                        {p.cites.map((c) => (
                          <CitationChip key={`${c.file}-${c.page}`} c={c} />
                        ))}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          <div className="mt-4 flex items-center justify-between border-t border-border pt-3 text-[12px] text-faint">
            <span>근거를 찾은 항목만 표시했습니다 (1건 제외)</span>
            <span className="flex items-center gap-2">
              {s.meta}
              <button type="button" className="btn btn-ghost btn-sm">
                다시 생성
              </button>
            </span>
          </div>
        </Section>
      ))}
    </div>
  );
}

function QuestionsTab() {
  const [open, setOpen] = useState<string[]>([]);
  return (
    <div className="space-y-3">
      <div className="flex justify-end gap-2">
        <button type="button" className="btn btn-sm" onClick={() => navigateQuery({ quiz: "qs:12", n: "1" }, "push")}>
          <Play aria-hidden />
          풀기
        </button>
        <button type="button" className="btn btn-primary btn-sm" onClick={() => navigateQuery({ new: "quiz" }, "push")}>
          <Plus aria-hidden />
          문제 만들기
        </button>
      </div>
      {demoQuestions.map((q) => {
        const shown = open.includes(q.id);
        return (
          <article key={q.id} className="card p-4">
            <div className="flex items-start gap-2">
              <h4 className="min-w-0 flex-1 text-[15px] font-semibold">
                Q{q.n}. {q.text}
              </h4>
              <Chip square>{q.type}</Chip>
            </div>
            {q.choices && (
              <ol className="mt-2 grid gap-1 text-[14px] text-muted sm:grid-cols-2">
                {q.choices.map((c, i) => (
                  <li key={c}>
                    {"①②③④"[i]} {c}
                  </li>
                ))}
              </ol>
            )}
            <div className="mt-3 flex items-center gap-2">
              <button type="button" className="btn btn-ghost btn-sm" aria-expanded={shown} onClick={() => setOpen((xs) => (shown ? xs.filter((x) => x !== q.id) : [...xs, q.id]))}>
                답 보기
                <ChevronDown className={`transition-transform ${shown ? "rotate-180" : ""}`} aria-hidden />
              </button>
              <span className="ml-auto flex gap-1">
                {q.cites.map((c) => (
                  <CitationChip key={c.page} c={c} />
                ))}
              </span>
            </div>
            <AnimatePresence initial={false}>
              {shown && (
                <motion.div initial={{ height: 0 }} animate={{ height: "auto" }} exit={{ height: 0 }} style={{ overflow: "hidden" }}>
                  <div className="mt-2 rounded-lg bg-surface-2 p-3 text-[14px]">
                    <p className="font-semibold">{q.answer}</p>
                    <p className="mt-1 text-muted">{q.explain}</p>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </article>
        );
      })}
      <NewQuizModal />
    </div>
  );
}

function NewQuizModal() {
  const open = useQueryValue("new") === "quiz";
  const close = () => closeQuery(["new"]);
  return (
    <Modal
      open={open}
      onClose={close}
      title="문제 만들기"
      footer={
        <>
          <button type="button" className="btn" onClick={close}>
            취소
          </button>
          <button type="button" className="btn btn-primary" onClick={close}>
            만들기
          </button>
        </>
      }
    >
      <div className="grid grid-cols-2 gap-4 pt-1">
        {[
          ["유형", ["객관식", "단답", "서술"]],
          ["개수", ["5", "10", "20"]],
          ["난이도", ["쉬움", "보통", "어려움"]],
          ["범위", ["전체", "3~7주차", "중간고사 범위"]],
        ].map(([l, opts]) => (
          <div key={l as string}>
            <label className="label">{l as string}</label>
            <select className="field">
              {(opts as string[]).map((o) => (
                <option key={o}>{o}</option>
              ))}
            </select>
          </div>
        ))}
      </div>
    </Modal>
  );
}

function AskTab() {
  const [text, setText] = useState("");
  return (
    <div className="card flex flex-col">
      <p className="border-b border-border px-4 py-2 text-[12px] text-faint">검색 범위: 이 과목 자료만 (7개 파일)</p>
      <div className="space-y-4 p-4">
        {demoAskThread.map((m, i) =>
          m.role === "user" ? (
            <p key={i} className="ml-auto max-w-[80%] rounded-2xl rounded-br-md bg-primary px-4 py-2 text-[14px] text-white">
              {m.text}
            </p>
          ) : (
            <div key={i} className="max-w-[85%]">
              <p className="rounded-2xl rounded-bl-md bg-surface-3 px-4 py-2 text-[14px]">{m.text}</p>
              {"cites" in m && m.cites && m.cites.length > 0 && (
                <ul className="mt-2 space-y-1">
                  {m.cites.map((c) => (
                    <li key={c.page}>
                      <button type="button" onClick={() => openCite(c)} className="flex w-full items-start gap-2 rounded-lg border border-border px-3 py-2 text-left text-[13px] hover:border-primary">
                        <FileText className="mt-0.5 size-4 flex-none text-primary" aria-hidden />
                        <span>
                          <b>
                            {c.fileName} · p.{c.page}
                          </b>
                          {c.quote && <span className="block text-muted">&ldquo;{c.quote}&rdquo;</span>}
                        </span>
                        <ChevronRight className="ml-auto size-4 flex-none text-faint" aria-hidden />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ),
        )}
      </div>
      <form className="flex gap-2 border-t border-border p-3" onSubmit={(e) => e.preventDefault()}>
        <label htmlFor="ask" className="sr-only">
          질문
        </label>
        <input id="ask" className="field flex-1" placeholder="이 과목 자료에 대해 물어보세요" value={text} onChange={(e) => setText(e.target.value)} />
        <button type="submit" className="btn btn-primary btn-icon" aria-label="보내기" disabled={!text.trim()}>
          <Send aria-hidden />
        </button>
      </form>
    </div>
  );
}

/** 첫 사용 동의 — 텍스트 일부가 외부 API 로 나가므로 필수(F4). 과목 상세에 처음 들어오면 뜬다. */
function ConsentGate() {
  const [consent, setConsent] = useStored("f4-consent", false);
  const [dismissed, setDismissed] = useState(false);
  const course = useQueryValue("course");
  return (
    <Modal
      open={!!course && !consent && !dismissed}
      onClose={() => setDismissed(true)}
      title="강의자료 분석을 시작할까요?"
      footer={
        <>
          <button type="button" className="btn" onClick={() => setDismissed(true)}>
            나중에
          </button>
          <button type="button" className="btn btn-primary" onClick={() => setConsent(true)}>
            <ShieldCheck aria-hidden />
            동의하고 시작
          </button>
        </>
      }
    >
      <ul className="space-y-2 pt-1 text-[14px] text-muted">
        <li>• 파일 원본은 이 PC 에만 있습니다.</li>
        <li>
          • 요약·문제·질문을 만들 때 <b className="text-text">자료 텍스트 일부가 외부 분석 API 로 전송</b>됩니다.
        </li>
        <li>• 동의하지 않아도 자료 목록과 원문 보기는 쓸 수 있습니다.</li>
      </ul>
    </Modal>
  );
}

/** 원문 뷰어 — `?file=&page=` (push). 요약·문제·질문 어디서든 같은 뷰어. */
function SourceViewer() {
  const file = useQueryValue("file");
  const page = Number(useQueryValue("page") ?? 1);
  const m = demoMaterials.find((x) => x.id === file);
  return (
    <Modal open={!!file} onClose={() => closeQuery(["file", "page"])} size="lg" title={m ? `${m.name} · ${page}쪽` : "원문"}>
      <div className="grid aspect-[3/4] max-h-[70vh] w-full place-items-center rounded-lg border border-border bg-surface-2 text-center text-[14px] text-muted">
        <div>
          <FileText className="mx-auto mb-2 size-8 text-faint" aria-hidden />
          PDF {page}쪽 — 로컬 파일 스트림(GET /api/materials/{"{id}"}/file) 연결 후 렌더링됩니다
          <p className="mt-3 inline-block rounded bg-blank px-2 py-1 text-text">인용 문장 하이라이트 자리</p>
        </div>
      </div>
    </Modal>
  );
}

/** 풀기 모드 — 전체 화면 모달. 문항 이동(n)은 replace, 뒤로가기는 목록으로. 숫자키 선택·Enter 제출. */
function QuizRunner() {
  const quiz = useQueryValue("quiz");
  const n = Math.max(1, Number(useQueryValue("n") ?? 1));
  const [picked, setPicked] = useState<number | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const q = demoQuestions[Math.min(n, demoQuestions.length) - 1];
  const next = () => {
    setPicked(null);
    setSubmitted(false);
    if (n < demoQuestions.length) navigateQuery({ n: String(n + 1) }, "replace");
    else closeQuery(["quiz", "n"]);
  };
  return (
    <Modal open={!!quiz} onClose={() => closeQuery(["quiz", "n"])} size="full" title="문제 풀기">
      {q && (
        <div
          className="mx-auto max-w-[680px] py-6"
          onKeyDown={(e) => {
            const k = Number(e.key);
            if (q.choices && k >= 1 && k <= q.choices.length && !submitted) setPicked(k - 1);
            if (e.key === "Enter") {
              if (submitted) next();
              else setSubmitted(true);
            }
            if (e.key === "ArrowRight" && submitted) next();
          }}
        >
          <div className="mb-6 flex items-center gap-3">
            <span className="num text-[14px] font-bold">
              {n} / {demoQuestions.length}
            </span>
            <span className="flex gap-1" aria-hidden>
              {demoQuestions.map((_, i) => (
                <span key={i} className={`size-2 rounded-full ${i < n ? "bg-primary" : "bg-border"}`} />
              ))}
            </span>
          </div>
          <h3 className="mb-5 text-[20px] font-bold">{q.text}</h3>
          {q.choices ? (
            <div className="space-y-2" role="radiogroup">
              {q.choices.map((c, i) => (
                <button
                  key={c}
                  type="button"
                  role="radio"
                  aria-checked={picked === i}
                  disabled={submitted}
                  onClick={() => setPicked(i)}
                  className={`flex w-full items-center gap-3 rounded-xl border px-4 py-3 text-left text-[15px] transition-colors ${picked === i ? "border-primary bg-primary-soft" : "border-border hover:bg-surface-2"}`}
                >
                  <span className="num grid size-6 place-items-center rounded-full bg-surface-3 text-[12px] font-bold">{i + 1}</span>
                  {c}
                </button>
              ))}
            </div>
          ) : (
            <textarea className="field" placeholder="답을 적어 보세요" aria-label="답" />
          )}
          {submitted && (
            <div className="mt-5 rounded-xl bg-surface-2 p-4 text-[14px]">
              <p className="font-bold">{q.type === "서술" ? "모범답안과 비교" : "정답"}: {q.answer}</p>
              <p className="mt-1 text-muted">{q.explain}</p>
              <div className="mt-2 flex gap-1">
                {q.cites.map((c) => (
                  <CitationChip key={c.page} c={c} />
                ))}
              </div>
            </div>
          )}
          <div className="mt-6 flex justify-end">
            {submitted ? (
              <button type="button" className="btn btn-primary" onClick={next}>
                {n < demoQuestions.length ? "다음 문제 →" : "결과 보기"}
              </button>
            ) : (
              <button type="button" className="btn btn-primary" onClick={() => setSubmitted(true)}>
                제출
              </button>
            )}
          </div>
        </div>
      )}
    </Modal>
  );
}
