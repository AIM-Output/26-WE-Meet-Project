"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  BookOpen,
  ChevronDown,
  ChevronRight,
  Download,
  ExternalLink,
  FileText,
  Lock,
  Play,
  Plus,
  RefreshCw,
  Search,
  Send,
  ShieldCheck,
  Trash2,
  Upload,
} from "lucide-react";
import { Page, PageHeader, Section } from "@/components/ui/Layout";
import { Tabs } from "@/components/ui/Tabs";
import { Banner, DemoNotice, EmptyState, ErrorPanel, SkeletonList } from "@/components/ui/Feedback";
import { Chip, EvidenceChip, StatusBadge } from "@/components/ui/Chip";
import { Modal } from "@/components/ui/Modal";
import { useAppData } from "@/components/app/AppData";
import { useStored } from "@/lib/storage";
import { api } from "@/lib/api";
import { useMaterials } from "@/lib/useMaterials";
import {
  fileSrc,
  KIND_FILTERS,
  KIND_TONE,
  pagesText,
  sizeText,
  STATE_TONE,
  type MaterialItem,
  type MaterialKind,
} from "@/lib/materials";
import { closeQuery, navigateQuery, useQueryParam, useQueryValue } from "@/lib/useQueryState";
import { demoAskThread, demoQuestions, demoSummaries, type Citation } from "@/lib/demo";

// /courses — 과목 목록, /courses?course=<id> — 자료 / 요약 / 문제 / 질문 (Frontend-Route 9절).
//
// 1차로 붙인 것: **자료 탭과 원문 뷰어가 진짜다** — e클래스에서 F6 가 받아 둔 강의자료·게시판 첨부·과제 첨부를
// 과목별로 보여 주고, 앱 안에서 열거나 내려받는다(F4-R01·R02·R04·R06~R08 · S01·S02·S05).
// 요약·문제·질문(RAG)은 모델이 정해진 뒤 — 그동안 예시 데이터로 화면만 서 있다.
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

/* ---------------------------------------------------------------- 과목 목록 (F4-S01) */

function CourseList() {
  const { syncing, startSync } = useAppData();
  const { data, loading, error, busy, reload, rescan } = useMaterials();
  const courses = data?.courses ?? [];
  const withFiles = courses.filter((c) => c.files > 0);

  return (
    <>
      <PageHeader
        icon={<BookOpen />}
        title="강의자료"
        subtitle={
          data
            ? `${data.totals.files}개 자료 · ${data.totals.pages}쪽 · ${data.totals.courses}과목`
            : "과목을 고르면 자료를 보고 열어 볼 수 있습니다"
        }
        actions={
          <>
            <button type="button" className="btn btn-sm" onClick={() => rescan()} disabled={busy}>
              <RefreshCw aria-hidden />
              다시 훑기
            </button>
            <button type="button" className="btn btn-primary btn-sm" onClick={() => void startSync()} disabled={syncing}>
              <Download aria-hidden />
              {syncing ? "가져오는 중…" : "e클래스에서 가져오기"}
            </button>
          </>
        }
      />
      {error ? (
        <ErrorPanel message={`자료 목록을 불러오지 못했습니다 — ${error}`} onRetry={() => void reload()} />
      ) : loading ? (
        <SkeletonList rows={4} />
      ) : (
        <>
          {data && !data.source.eclass.available && (
            <Banner tone="warn" className="mb-4">
              아직 e클래스에서 자료를 받은 적이 없습니다 — <b>e클래스에서 가져오기</b>를 한 번 눌러 주세요.
            </Banner>
          )}
          {withFiles.length === 0 ? (
            <EmptyState
              icon={<BookOpen />}
              title="강의자료가 없습니다"
              action={
                <>
                  <button type="button" className="btn btn-primary btn-sm" onClick={() => void startSync()} disabled={syncing}>
                    e클래스 동기화
                  </button>
                  <Link href="/settings/sources" className="btn btn-sm">
                    수집 원천 설정
                  </Link>
                </>
              }
            >
              e클래스 동기화를 하면 과목별 강의자료·첨부파일이 여기 모입니다
            </EmptyState>
          ) : (
            <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {courses.map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    onClick={() => navigateQuery({ course: c.id }, "push")}
                    className="card card-hover flex h-full w-full flex-col gap-3 p-4 text-left hover:bg-surface-2"
                  >
                    <span className="flex items-center gap-2">
                      <span className="size-2.5 flex-none rounded-full" style={{ background: c.color ?? "var(--faint)" }} aria-hidden />
                      <span className="truncate text-[15px] font-bold">{c.short}</span>
                      <span className="ml-auto text-[12px] text-faint">{c.code}</span>
                    </span>
                    <span className="flex flex-wrap items-center gap-2 text-[13px] text-muted">
                      <FileText className="size-4" aria-hidden />
                      자료 <b className="num text-text">{c.files}</b>
                      {c.pages > 0 && <span className="num text-faint">· {c.pages}쪽</span>}
                      {c.attention > 0 && (
                        <Chip tone="warn" square>
                          확인 {c.attention}
                        </Chip>
                      )}
                      {c.uploads > 0 && (
                        <Chip tone="study" square>
                          직접 {c.uploads}
                        </Chip>
                      )}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <p className="hint mt-4">
            요약·예상 문제·질문(RAG)은 아직 붙이지 않았습니다 — 과목을 열면 자료 목록과 원문 보기가 동작합니다.
          </p>
        </>
      )}
    </>
  );
}

/* ---------------------------------------------------------------- 과목 상세 */

function CourseDetail({ id }: { id: string }) {
  const { courses } = useAppData();
  const [consent] = useStored("f4-consent", false);
  const [rawTab, setTab] = useQueryParam("tab", "materials", TABS);
  const tab = consent ? rawTab : "materials"; // 동의 전에는 분석 탭이 잠긴다
  const m = useMaterials(id);
  const mine = m.data?.courses.find((c) => c.id === id);
  const course = courses.find((c) => c.id === id);
  const files = m.data?.materials ?? [];
  const title = mine?.short || course?.short || "과목";

  return (
    <>
      <PageHeader
        icon={<BookOpen />}
        title={title}
        subtitle={mine ? `${mine.files}개 자료 · ${mine.pages}쪽${mine.code ? ` · ${mine.code}` : ""}` : course?.code}
        actions={
          <button type="button" className="btn btn-sm" onClick={() => navigateQuery({ course: null, tab: null }, "replace")}>
            과목 목록
          </button>
        }
      />
      {!consent && (
        <Banner tone="warn" icon={<Lock aria-hidden />} className="mb-5">
          요약·문제·질문은 자료 텍스트 일부를 외부 분석 API 로 보냅니다. 동의 전에는 잠깁니다 — 자료 목록과 원문 보기는 그대로 됩니다.
        </Banner>
      )}
      <Tabs
        className="mb-5"
        label="강의자료 보기"
        value={tab}
        onChange={(t) => setTab(t)}
        items={[
          { key: "materials", label: "자료", count: files.length },
          { key: "summary", label: "요약", disabled: !consent },
          { key: "questions", label: "문제", disabled: !consent },
          { key: "ask", label: "질문", disabled: !consent },
        ]}
      />
      {tab === "materials" ? (
        <MaterialsTab courseId={id} m={m} />
      ) : (
        <>
          <div className="mb-4">
            <DemoNotice what="요약·예상 문제·질문(RAG)" />
          </div>
          {tab === "summary" ? <SummaryTab /> : tab === "questions" ? <QuestionsTab /> : <AskTab />}
        </>
      )}
    </>
  );
}

/* ---------------------------------------------------------------- 자료 탭 (F4-S02) */

function MaterialsTab({ courseId, m }: { courseId: string; m: ReturnType<typeof useMaterials> }) {
  const { syncing, startSync } = useAppData();
  const [kind, setKind] = useState<MaterialKind | "all">("all");
  const [q, setQ] = useState("");
  const [over, setOver] = useState(false);
  const course = m.data?.courses.find((c) => c.id === courseId);
  const files = useMemo(() => m.data?.materials ?? [], [m.data]);

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return files.filter(
      (f) =>
        (kind === "all" || f.kind === kind) &&
        (!needle || f.title.toLowerCase().includes(needle) || f.activity.toLowerCase().includes(needle) || f.post.toLowerCase().includes(needle)),
    );
  }, [files, kind, q]);

  if (m.error) return <ErrorPanel message={`자료를 불러오지 못했습니다 — ${m.error}`} onRetry={() => void m.reload()} />;
  if (m.loading) return <SkeletonList rows={5} />;

  const drop = (fs: FileList | null) => {
    setOver(false);
    if (fs && fs.length) void m.upload(fs);
  };

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        drop(e.dataTransfer.files);
      }}
      className={`rounded-xl transition-colors ${over ? "bg-primary-soft ring-2 ring-primary" : ""}`}
    >
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Tabs
          variant="pill"
          size="sm"
          label="자료 종류"
          value={kind}
          onChange={setKind}
          items={KIND_FILTERS.map((f) => ({
            key: f.key,
            label: f.label,
            count: f.key === "all" ? files.length : (course?.byKind[f.key as MaterialKind] ?? 0),
          }))}
        />
        <label className="relative ml-auto">
          <span className="sr-only">자료 검색</span>
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-faint" aria-hidden />
          <input className="field field-sm w-44 pl-8" placeholder="파일 이름" value={q} onChange={(e) => setQ(e.target.value)} />
        </label>
        <button type="button" className="btn btn-sm" onClick={() => void m.rescan()} disabled={m.busy} title="수집 폴더를 다시 훑습니다">
          <RefreshCw aria-hidden />
          다시 훑기
        </button>
        <label className="btn btn-primary btn-sm cursor-pointer">
          <Upload aria-hidden />
          파일 추가
          <input
            type="file"
            multiple
            className="sr-only"
            disabled={m.busy}
            onChange={(e) => {
              drop(e.target.files);
              e.target.value = "";
            }}
          />
        </label>
      </div>

      {files.length === 0 ? (
        <EmptyState
          icon={<FileText />}
          title="이 과목의 강의자료가 없습니다"
          action={
            <button type="button" className="btn btn-primary btn-sm" onClick={() => void startSync()} disabled={syncing}>
              e클래스 동기화
            </button>
          }
        >
          e클래스 동기화로 자료를 받아오거나, 파일을 이 영역에 끌어다 놓아 직접 추가하세요
        </EmptyState>
      ) : shown.length === 0 ? (
        <EmptyState compact icon={<Search />} title="조건에 맞는 자료가 없습니다" />
      ) : (
        <ul className="overflow-hidden rounded-xl border border-border bg-surface">
          {shown.map((f) => (
            <MaterialRow key={f.id} m={f} onDelete={() => void m.remove(f)} busy={m.busy} />
          ))}
        </ul>
      )}

      <p className="hint mt-3 text-center">
        파일을 이 영역에 끌어다 놓아도 추가됩니다 (최대 {m.data?.limits.maxFileMB ?? 100}MB · 문서 파일만)
      </p>
      {m.data && (
        <p className="hint mt-1 text-center">
          보관함: <code className="text-faint">{m.data.source.libraryDir}</code> — e클래스에서 받은 자료를 여기로 들여옵니다
          {m.data.source.eclass.manifestAt && ` · 마지막 수집 ${m.data.source.eclass.manifestAt.replace("T", " ").slice(0, 16)}`}
        </p>
      )}
    </div>
  );
}

const ALERT_NOTE = new Set<MaterialItem["state"]>(["missing", "failed", "locked"]);

function MaterialRow({ m, onDelete, busy }: { m: MaterialItem; onDelete: () => void; busy: boolean }) {
  const [confirm, setConfirm] = useState(false);
  const origin = m.post || m.activity;
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-border px-4 py-3 last:border-b-0">
      <FileText className="size-5 flex-none text-faint" aria-hidden />
      <button
        type="button"
        className="min-w-0 flex-1 text-left"
        onClick={() => navigateQuery({ file: m.id, page: "1" }, "push")}
        title={m.viewable ? "앱 안에서 열기" : "이 형식은 내려받아서 봅니다"}
      >
        <span className="block truncate text-[14px] font-semibold hover:text-primary">{m.title}</span>
        <span className="block truncate text-[12px] text-faint">
          {m.week ? `${m.week}주차(추정) · ` : ""}
          {pagesText(m)} · {sizeText(m)} · {m.kindLabel}
          {origin ? ` · ${origin}` : ""}
        </span>
      </button>
      <Chip tone={KIND_TONE[m.kind]} square className="hidden sm:inline-flex">
        {m.kindLabel}
      </Chip>
      <StatusBadge tone={STATE_TONE[m.state]}>{m.stateLabel}</StatusBadge>
      <span className="flex flex-none items-center gap-1">
        <a
          className="btn btn-ghost btn-icon btn-sm"
          href={m.downloadUrl}
          download={m.title}
          aria-label={`${m.title} 내려받기`}
          title="내려받기"
        >
          <Download aria-hidden />
        </a>
        {m.eclassUrl && (
          <a
            className="btn btn-ghost btn-icon btn-sm"
            href={m.eclassUrl}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={`${m.title} e클래스에서 보기`}
            title="e클래스에서 보기"
          >
            <ExternalLink aria-hidden />
          </a>
        )}
        {m.canDelete ? (
          <button
            type="button"
            className={`btn btn-icon btn-sm ${confirm ? "btn-danger" : "btn-ghost"}`}
            disabled={busy}
            aria-label={confirm ? `${m.title} 정말 삭제` : `${m.title} 삭제`}
            title={confirm ? "한 번 더 누르면 지웁니다" : "삭제"}
            onClick={() => (confirm ? onDelete() : setConfirm(true))}
            onBlur={() => setConfirm(false)}
          >
            <Trash2 aria-hidden />
          </button>
        ) : (
          <span className="grid size-8 place-items-center" title="e클래스 수집분은 원본이 그쪽이라 지울 수 없습니다">
            <Lock className="size-3.5 text-faint" aria-label="삭제 잠김" />
          </span>
        )}
      </span>
      {m.note && (
        // 손쓸 것이 있는 상태(파일 없음·실패·암호)만 경고색, 나머지(텍스트 없는 PDF·중복·분석 제외)는 안내로만
        <p className={`w-full pl-8 text-[12px] ${ALERT_NOTE.has(m.state) ? "text-warn-text" : "text-faint"}`}>{m.note}</p>
      )}
    </li>
  );
}

/* ---------------------------------------------------------------- 원문 뷰어 (F4-S05) */

/** `?file=&page=` (push) — 요약·문제·질문 어디서든 같은 뷰어. PDF·텍스트는 앱 안에서, 나머지는 내려받기. */
function SourceViewer() {
  const fileId = useQueryValue("file");
  const page = Number(useQueryValue("page") ?? 1) || 1;
  const [m, setM] = useState<MaterialItem | null>(null);
  const [error, setError] = useState<string | null>(null);
  const asked = useRef<string | null>(null);

  useEffect(() => {
    if (!fileId || asked.current === fileId) return;
    asked.current = fileId;
    setM(null);
    setError(null);
    api
      .material(fileId)
      .then(setM)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [fileId]);

  useEffect(() => {
    if (!fileId) asked.current = null;
  }, [fileId]);

  return (
    <Modal
      open={!!fileId}
      onClose={() => closeQuery(["file", "page"])}
      size="xl"
      title={m ? `${m.title}${m.pages ? ` · ${page}/${m.pages}쪽` : ""}` : "원문"}
      footer={
        m && (
          <>
            {m.eclassUrl && (
              <a className="btn" href={m.eclassUrl} target="_blank" rel="noopener noreferrer">
                <ExternalLink aria-hidden />
                e클래스에서 보기
              </a>
            )}
            <a className="btn btn-primary" href={m.downloadUrl} download={m.title}>
              <Download aria-hidden />
              내려받기
            </a>
          </>
        )
      }
    >
      {error ? (
        <div className="grid place-items-center rounded-lg border border-border bg-surface-2 p-8 text-center text-[14px] text-muted">
          <div>
            <FileText className="mx-auto mb-2 size-8 text-faint" aria-hidden />
            {/* 예시 요약·문제의 근거 칩은 아직 진짜 파일을 가리키지 않는다 */}
            {fileId?.startsWith("mt:se") ? "예시 요약의 근거입니다 — 실제 파일이 아닙니다" : `원문을 열지 못했습니다 — ${error}`}
          </div>
        </div>
      ) : !m ? (
        <div className="skeleton h-[60vh] w-full rounded-lg" aria-busy="true" />
      ) : m.viewable ? (
        <iframe
          src={fileSrc(m, page)}
          title={m.title}
          className="h-[70vh] max-h-[70vh] w-full rounded-lg border border-border bg-surface-2"
        />
      ) : (
        <div className="grid place-items-center rounded-lg border border-border bg-surface-2 p-10 text-center text-[14px] text-muted">
          <div>
            <FileText className="mx-auto mb-2 size-8 text-faint" aria-hidden />
            <b className="text-text">{m.ext}</b> 는 브라우저에서 바로 열 수 없습니다 — 내려받아서 보세요.
            <p className="mt-1 text-[13px]">{pagesText(m)} · {sizeText(m)}</p>
          </div>
        </div>
      )}
    </Modal>
  );
}

/* ---------------------------------------------------------------- 아래는 아직 예시 (모델이 정해지면 붙인다) */

function SummaryTab() {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <select className="field field-sm w-auto" aria-label="범위" defaultValue="all">
          <option value="all">전체</option>
          <option value="3-7">3~7주차</option>
          <option value="mid">중간고사 범위</option>
        </select>
        <button type="button" className="btn btn-primary btn-sm ml-auto" disabled>
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
              <button type="button" className="btn btn-ghost btn-sm" disabled>
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
      <p className="border-b border-border px-4 py-2 text-[12px] text-faint">검색 범위: 이 과목 자료만</p>
      <div className="space-y-4 p-4">
        {demoAskThread.map((m, i) =>
          m.role === "user" ? (
            <p key={i} className="ml-auto max-w-[80%] rounded-2xl rounded-br-md bg-primary px-4 py-2 text-[14px] text-on-primary">
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

/** 첫 사용 동의 — 요약·문제·질문을 만들 때 텍스트 일부가 외부로 나간다(F4-R40). 자료 목록·원문 보기에는 필요 없다. */
function ConsentGate() {
  const [consent, setConsent] = useStored("f4-consent", false);
  const [dismissed, setDismissed] = useState(false);
  const tab = useQueryValue("tab");
  const wantsAnalysis = !!tab && tab !== "materials";
  return (
    <Modal
      open={wantsAnalysis && !consent && !dismissed}
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
