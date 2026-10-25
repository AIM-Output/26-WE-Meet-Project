"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Bookmark,
  BookmarkCheck,
  CalendarCheck,
  CalendarPlus,
  ChevronDown,
  Copy,
  ExternalLink,
  FileText,
  HandCoins,
  ListTodo,
  NotebookPen,
  RefreshCw,
  Settings2,
  ShieldAlert,
  Sparkles,
  Trophy,
  Undo2,
  X,
} from "lucide-react";
import { Page, PageHeader, Section, Group, Toggle } from "@/components/ui/Layout";
import { Tabs } from "@/components/ui/Tabs";
import { Banner, EmptyState, ErrorPanel, SkeletonList, SyncBanner } from "@/components/ui/Feedback";
import { Chip, DdayChip, StatusBadge } from "@/components/ui/Chip";
import { Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { useAppData } from "@/components/app/AppData";
import { closeQuery, navigateQuery, useQueryParam, useQueryValue } from "@/lib/useQueryState";
import { useIsXl } from "@/lib/useMediaQuery";
import { useActivities } from "@/lib/useActivities";
import { api } from "@/lib/api";
import { fmtRelative, parseLocal } from "@/lib/dates";
import { GROUP_LABEL, RELEVANCE, type SchSource } from "@/lib/scholarships";
import type { Interests } from "@/lib/profile";
import {
  GRADE_TONE,
  PROGRESS_TONE,
  actSyncText,
  type ActDetail,
  type ActHistory,
  type ActItem,
  type ActMaterials,
  type ActOverview,
  type ActSources,
} from "@/lib/activities";

// /opportunities — 대외활동 (F12·F13, Frontend-Route 17절). 2026-10-10 실데이터.
// 원천은 장학(F11)과 같다 — 학교 전체 · 부서 · 사업단 · 내 단과대학·학과. 장학 글은 장학 화면 몫이고 여기는 나머지 전부
// (교내 프로그램 · 공모전 · 대외활동 · 취업·인턴 · 해외 · 창업 · 봉사 · 기자재 대여 …). 장학은 '내 해당'을, 여기는 '내 관심사'를 가른다.

const TABS = ["activity", "program", "history", "sources"] as const;
const VIEWS = ["info", "draft", "apply"] as const;

const deadlineDate = (s: string) => parseLocal(s.length > 10 ? s : `${s}T23:59`);
const fmtDl = (s: string | null) => (s ? s.replace("T", " ").slice(5, 16).replace("-", "/") : "기간 미정");
const isOpen = (o: ActItem) => o.status === "open";

export default function OpportunitiesPage() {
  const [tab] = useQueryParam("tab", "activity", TABS);
  const [show, setShow] = useQueryParam("show", "", ["", "all"] as const);
  const [saved, setSaved] = useQueryParam("saved", "", ["", "1"] as const);
  const cat = useQueryValue("cat");
  const itemId = useQueryValue("item");
  const askInterests = useQueryValue("interests") === "1"; // 내 프로필의 '관심사 설정' 링크
  const isXl = useIsXl();
  const a = useActivities(itemId);
  const [interestsOpen, setInterestsOpen] = useState(false);
  const [materialsOpen, setMaterialsOpen] = useState(false);
  const [materialsFor, setMaterialsFor] = useState<string | null>(null); // 초안을 만들려다 재료부터 묻는 중이면 그 공지 id
  const openMaterials = (forId: string | null = null) => {
    setMaterialsFor(forId);
    setMaterialsOpen(true);
  };
  const data = a.data;
  const graded = !!data?.interests.set;

  const inTab = useMemo(
    () => (data?.items ?? []).filter((o) => (tab !== "program" || o.isProgram) && (!saved || o.saved) && (!cat || o.category === cat)),
    [data, tab, saved, cat],
  );
  const groups = useMemo(() => {
    const closed = { key: "마감·결과·대상 아님", items: inTab.filter((o) => !isOpen(o)), dot: "var(--border-strong)", fold: true, hideEmpty: true };
    if (!graded) return [{ key: "모집 중", items: inTab.filter(isOpen), dot: "var(--primary)", fold: false, hideEmpty: false }, closed];
    return [
      { key: "내 관심사", items: inTab.filter((o) => isOpen(o) && o.grade === "match"), dot: "var(--ok)", fold: false, hideEmpty: false },
      { key: "관련 있음", items: inTab.filter((o) => isOpen(o) && o.grade === "related"), dot: "var(--info)", fold: false, hideEmpty: true },
      { key: "관심 밖", items: inTab.filter((o) => isOpen(o) && o.grade === "other"), dot: "var(--border-strong)", fold: true, hideEmpty: true },
      closed,
    ];
  }, [inTab, graded]);
  const catCounts = useMemo(() => {
    const m = new Map<string, number>();
    for (const o of data?.items ?? []) if (isOpen(o) && (tab !== "program" || o.isProgram) && o.category) m.set(o.category, (m.get(o.category) ?? 0) + 1);
    return [...m.entries()].sort((x, y) => y[1] - x[1]);
  }, [data, tab]);

  const sync = data?.sync;
  const meta = data && <span className="num">{data.lastOkAt ? `수집 ${fmtRelative(data.lastOkAt)}` : "아직 수집 전"}</span>;

  return (
    <Page wide>
      <PageHeader
        icon={<Trophy />}
        title="대외활동"
        subtitle="교내 프로그램 · 공모전 · 대외활동 · 취업 · 기자재 대여 — 장학 외 공지를 내 관심사로 골라 드립니다"
        meta={meta}
        actions={
          <>
            <button type="button" className="btn btn-sm" onClick={() => setInterestsOpen(true)}>
              <Settings2 aria-hidden />
              관심사 설정
            </button>
            <button type="button" className="btn btn-sm" onClick={() => openMaterials()}>
              <NotebookPen aria-hidden />
              초안 재료
            </button>
            <button type="button" className="btn btn-primary btn-sm" disabled={!!sync?.running} onClick={() => void a.sync()}>
              <RefreshCw className={sync?.running ? "animate-spin" : ""} aria-hidden />
              {sync?.running ? "모으는 중" : "지금 수집"}
            </button>
          </>
        }
      />

      <div className="mb-5 space-y-3">
        {sync?.running && <SyncBanner state="running">{actSyncText(sync)} 게시판마다 1.5초 간격으로 읽어 처음에는 몇 분 걸립니다.</SyncBanner>}
        {data && !graded && (
          <Banner
            tone="info"
            action={
              <button type="button" className="btn btn-primary btn-sm" onClick={() => setInterestsOpen(true)}>
                관심사 고르기
              </button>
            }
          >
            관심사를 고르면 맞는 기회만 골라 드립니다. 고르기 전에는 모든 공지를 최신순으로 보여 드리고, 알림은 보내지 않습니다.
          </Banner>
        )}
        {data?.wide.map((w) => (
          <Banner key={w.keyword} tone="warn" action={<button type="button" className="btn btn-sm" onClick={() => setInterestsOpen(true)}>키워드 고치기</button>}>
            키워드 &ldquo;{w.keyword}&rdquo;에 모집 중인 공지 {w.count}건이 걸렸습니다 — 너무 넓으면 알림이 시끄러워집니다.
          </Banner>
        ))}
        {data && !data.profile.exists && (
          <Banner tone="warn" action={<a className="btn btn-sm" href="/settings/profile">프로필 넣기</a>}>
            학과를 넣으면 내 학과 관련 사업단·학과 공지 게시판도 같이 모읍니다.
          </Banner>
        )}
        <Banner
          tone="neutral"
          icon={<HandCoins aria-hidden />}
          action={
            <Link href="/scholarships" className="btn btn-sm">
              장학 보기
            </Link>
          }
        >
          같은 게시판의 장학 공지는 &lsquo;장학&rsquo; 화면에서 내 조건과 대조합니다. 여기는 장학이 아닌 나머지 공지입니다.
        </Banner>
      </div>

      <Tabs
        className="mb-5"
        label="대외활동 화면"
        value={tab}
        onChange={(t) => navigateQuery({ tab: t === "activity" ? null : t, item: null, view: null, show: null, cat: null }, "replace")}
        items={[
          { key: "activity", label: "대외활동", count: data ? (graded ? data.counts.match : data.counts.open) : undefined },
          { key: "program", label: "사업단", count: data ? (graded ? data.counts.programMatch : data.counts.program) : undefined },
          { key: "history", label: "이력" },
          { key: "sources", label: "원천" },
        ]}
      />

      {tab === "history" ? (
        <HistoryTab onChanged={() => void a.reload()} />
      ) : tab === "sources" ? (
        <SourcesTab onSync={() => void a.sync()} />
      ) : a.error ? (
        <ErrorPanel message={`대외활동 목록을 불러오지 못했습니다: ${a.error}`} onRetry={() => void a.reload()} />
      ) : a.loading || !data ? (
        <SkeletonList />
      ) : data.items.length === 0 ? (
        <EmptyState
          icon={<Trophy />}
          title="아직 수집한 공지가 없습니다"
          action={
            <button type="button" className="btn btn-primary btn-sm" disabled={!!sync?.running} onClick={() => void a.sync()}>
              <RefreshCw aria-hidden />
              지금 수집
            </button>
          }
        >
          앱이 켜져 있으면 매일 06:00 · 18:00 에 (장학 수집이 끝난 뒤) 자동으로 모읍니다. 처음 수집은 몇 분 걸립니다.
        </EmptyState>
      ) : (
        <>
          {/* 분류 필터 — 휴대폰 폭에서는 한 줄 가로 스크롤, 넓으면 줄바꿈 */}
          <div className="mb-4 flex items-start gap-2">
            <div className="no-scrollbar flex min-w-0 flex-1 gap-2 overflow-x-auto md:flex-wrap" role="group" aria-label="분류">
              <button type="button" aria-pressed={!cat} className={`btn btn-sm flex-none ${!cat ? "border-primary bg-primary-soft text-primary" : ""}`} onClick={() => navigateQuery({ cat: null }, "replace")}>
                전체
              </button>
              {catCounts.map(([k, n]) => (
                <button key={k} type="button" aria-pressed={cat === k} className={`btn btn-sm flex-none whitespace-nowrap ${cat === k ? "border-primary bg-primary-soft text-primary" : ""}`} onClick={() => navigateQuery({ cat: cat === k ? null : k }, "replace")}>
                  {data.categories[k] ?? k} <span className="num text-faint">{n}</span>
                </button>
              ))}
            </div>
            <button type="button" aria-pressed={!!saved} className={`btn btn-sm flex-none ${saved ? "border-primary bg-primary-soft text-primary" : ""}`} onClick={() => setSaved(saved ? null : "1")}>
              <Bookmark aria-hidden />
              담은 것만 {data.counts.saved ? <span className="num">{data.counts.saved}</span> : null}
            </button>
          </div>
          {tab === "program" && <p className="mb-4 text-[13px] text-muted">사업단 게시판과, 사업단이 학교 공지에 올린 글만 모았습니다 (켜진 사업단은 &lsquo;원천&rsquo; 탭).</p>}
          {graded && !data.llm && <p className="mb-4 text-[12px] text-faint">키워드로만 고르고 있습니다 — 키워드가 없는 공지는 내 학과 관련 게시판의 모집 글만 &lsquo;관련 있음&rsquo;으로 둡니다.</p>}
          <div className={`grid gap-5 ${itemId && isXl ? "grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]" : "grid-cols-[minmax(0,1fr)]"}`}>
            <div className="min-w-0">
              {groups.map((g) =>
                g.fold && show !== "all" ? (
                  g.items.length > 0 && (
                    <button key={g.key} type="button" className="btn btn-ghost btn-sm mb-4" onClick={() => setShow("all")}>
                      + {g.key} {g.items.length}건 더보기
                      <ChevronDown aria-hidden />
                    </button>
                  )
                ) : g.items.length === 0 && g.hideEmpty ? null : (
                  <Group key={g.key} title={g.key} count={g.items.length} dot={g.dot}>
                    {g.items.length === 0 ? (
                      <p className="rounded-xl border border-dashed border-border-strong px-4 py-3 text-[14px] text-muted">
                        {g.key === "내 관심사" ? `지금 관심사에 맞는 기회가 없습니다${data.counts.related ? ` — 관련 있음 ${data.counts.related}건` : ""}` : saved ? "담아 둔 것이 없습니다" : "없습니다"}
                      </p>
                    ) : (
                      <ul className="overflow-hidden rounded-xl border border-border bg-surface">
                        {g.items.map((o) => (
                          <ItemRow key={o.id} o={o} active={o.id === itemId} />
                        ))}
                      </ul>
                    )}
                  </Group>
                ),
              )}
            </div>
            {itemId && isXl && (
              <aside
                key={itemId}
                className="sticky top-[calc(var(--header-h)+16px)] max-h-[calc(100dvh-var(--header-h)-32px)] self-start overflow-y-auto overscroll-contain rounded-2xl"
                aria-label="상세 — 목록과 따로 스크롤됩니다"
              >
                {a.detail ? <Detail d={a.detail} a={a} onMaterials={openMaterials} /> : <SkeletonList rows={4} />}
              </aside>
            )}
          </div>
        </>
      )}

      <Modal open={!!itemId && !isXl && (tab === "activity" || tab === "program")} onClose={() => closeQuery(["item", "view"])} title={a.detail?.title} size="lg">
        {a.detail && <Detail d={a.detail} a={a} onMaterials={openMaterials} bare />}
      </Modal>
      <InterestsModal
        open={interestsOpen || askInterests}
        onClose={() => {
          setInterestsOpen(false);
          if (askInterests) closeQuery(["interests"]);
        }}
        data={data}
      />
      <MaterialsModal
        open={materialsOpen}
        onClose={() => setMaterialsOpen(false)}
        onSaved={() => {
          if (materialsFor) void a.run(() => api.makeOpportunityDraft(materialsFor), "초안을 만들었습니다");
          setMaterialsFor(null);
        }}
      />
    </Page>
  );
}

function ItemRow({ o, active }: { o: ActItem; active: boolean }) {
  const dim = !isOpen(o) || o.grade === "other";
  return (
    <li className="border-b border-border last:border-b-0">
      <button
        type="button"
        onClick={() => navigateQuery({ item: o.id, view: null }, "push")}
        className={`flex w-full flex-wrap items-center gap-x-3 gap-y-1.5 px-4 py-3 text-left transition-colors hover:bg-surface-2 ${active ? "bg-primary-soft" : ""} ${dim ? "opacity-75" : ""}`}
      >
        <span className="min-w-0 flex-1 basis-[55%]">
          <span className={`block truncate text-[15px] font-semibold ${o.status === "expired" ? "line-through" : ""}`}>{o.title}</span>
          <span className="block truncate text-[13px] text-muted">
            {o.categoryLabel}
            {o.org ? ` · ${o.org}` : ""}
            {o.target ? ` · ${o.target.slice(0, 30)}` : ""}
          </span>
        </span>
        <span className="flex flex-wrap items-center gap-1.5">
          {!isOpen(o) && <StatusBadge tone="neutral">{o.statusLabel}</StatusBadge>}
          {o.chips.slice(0, 3).map((r) => (
            <Chip key={r} tone={r === "LLM 판단" || r === "내 학과 관련 원천" ? "neutral" : r.startsWith("제외") ? "danger" : "primary"} square>
              {r}
            </Chip>
          ))}
          {o.flipped && <Chip tone="accent">내가 바꿈</Chip>}
          {o.progress && o.progress !== "saved" && <Chip tone={PROGRESS_TONE[o.progress]}>{o.progressLabel}</Chip>}
          {o.saved && <BookmarkCheck className="size-4 text-primary" aria-label="담음" />}
          {o.isNew && <Chip tone="primary" square>새 글</Chip>}
          {o.deadline && isOpen(o) && <DdayChip date={deadlineDate(o.deadline)} />}
        </span>
      </button>
    </li>
  );
}

type Act = ReturnType<typeof useActivities>;

function Detail({ d, a, onMaterials, bare }: { d: ActDetail; a: Act; onMaterials: (forId?: string) => void; bare?: boolean }) {
  const [view, setView] = useQueryParam("view", "info", VIEWS);
  const body = (
    <div className="space-y-4">
      <p className="flex flex-wrap items-center gap-2 text-[14px] text-muted">
        <span>{d.org || d.sourceName}</span>
        {d.categoryLabel && <Chip square>{d.categoryLabel}</Chip>}
        <span>· 신청 ~{fmtDl(d.deadline)}</span>
        {d.deadline && isOpen(d) && <DdayChip date={deadlineDate(d.deadline)} />}
        {d.grade ? <StatusBadge tone={GRADE_TONE[d.grade]}>{d.gradeLabel}</StatusBadge> : null}
        {!isOpen(d) && <StatusBadge tone="neutral">{d.statusLabel}</StatusBadge>}
        {d.flipped && <Chip tone="accent">내가 바꿈</Chip>}
        <a href={d.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 font-semibold text-primary hover:underline">
          원문
          <ExternalLink className="size-3.5" aria-hidden />
        </a>
      </p>
      <Tabs
        variant="pill"
        size="sm"
        label="상세 단계"
        value={view}
        onChange={(v) => setView(v === "info" ? null : v)}
        items={[
          { key: "info", label: "공지·관심사" },
          { key: "draft", label: d.hasDraft ? "초안" : "초안 만들기" },
          { key: "apply", label: "제출 준비" },
        ]}
      />
      {view === "info" && <InfoView d={d} a={a} onDraft={() => setView("draft")} />}
      {view === "draft" && <DraftView d={d} a={a} onMaterials={onMaterials} />}
      {view === "apply" && <ApplyView d={d} a={a} />}
    </div>
  );
  if (bare) return body;
  return (
    <Section
      title={d.title}
      action={
        <button type="button" className="btn btn-ghost btn-icon btn-sm" aria-label="상세 닫기" onClick={() => closeQuery(["item", "view"])}>
          <X aria-hidden />
        </button>
      }
    >
      {body}
    </Section>
  );
}

function InfoView({ d, a, onDraft }: { d: ActDetail; a: Act; onDraft: () => void }) {
  const toast = useToast();
  const flip = (grade: "match" | "other" | null) =>
    void a.run(() => api.patchOpportunity(d.id, { grade }), grade ? `${grade === "match" ? "내 관심사" : "관심 밖"}로 표시했습니다` : "시스템 판단으로 되돌렸습니다");
  const rows: [string, string | null][] = [
    ["대상", d.target ?? (d.grades ? `${d.grades.join("·")}학년` : null)],
    ["신청 기간", d.period?.raw ?? null],
    ["활동·교육", d.eventPeriod],
    ["장소", d.place],
    ["혜택", d.benefit],
    ["참가비", d.fee],
    ["인원", d.capacity],
    ["출처", d.alsoPostedAt.length ? `${d.sourceName} 외 ${d.alsoPostedAt.map((x) => x.source_name).join(" · ")}` : d.sourceName],
  ];
  return (
    <>
      {d.notes.map((n) => (
        <Banner key={n} tone="warn">
          {n}
        </Banner>
      ))}
      {d.draftStale && <Banner tone="warn">초안을 만든 뒤 원문이 바뀌었습니다 — 초안 탭에서 다시 만들어 주세요</Banner>}
      {d.askApplied && (
        <Banner
          tone="info"
          action={
            <>
              <button type="button" className="btn btn-sm" onClick={() => void a.run(() => api.patchOpportunity(d.id, { askedApplied: true }))}>
                아니요
              </button>
              <button type="button" className="btn btn-primary btn-sm" onClick={() => void a.run(() => api.patchOpportunity(d.id, { progress: "applied" }), "지원함으로 기록했습니다")}>
                지원했어요
              </button>
            </>
          }
        >
          마감이 지났습니다 — 지원하셨나요?
        </Banner>
      )}
      <div className="rounded-xl border border-border bg-surface-2 px-3 py-2.5">
        <p className="mb-1.5 flex flex-wrap items-center gap-1.5 text-[12px] font-semibold text-muted">
          왜 이 목록에 있나
          {d.chips.map((c) => (
            <Chip key={c} tone={c.startsWith("제외") ? "danger" : c === "LLM 판단" || c === "내 학과 관련 원천" ? "neutral" : "primary"} square>
              {c}
            </Chip>
          ))}
        </p>
        <ul className="space-y-0.5 text-[13px]">
          {d.reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      </div>
      {d.audienceNote && <Banner tone="warn">{d.audienceNote} — 모집 대상 학년이 아닐 수 있습니다. 원문을 확인하세요.</Banner>}
      <dl className="grid grid-cols-[76px_minmax(0,1fr)] gap-x-3 gap-y-2 text-[14px]">
        {rows
          .filter(([, v]) => v)
          .map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-muted">{k}</dt>
              <dd className="min-w-0 break-words">{v}</dd>
            </div>
          ))}
      </dl>
      {d.body && (
        <details className="rounded-xl border border-border px-3 py-2 text-[13px]">
          <summary className="cursor-pointer font-semibold text-muted">본문 보기{d.attachments.length ? ` · 첨부 ${d.attachments.length}` : ""}</summary>
          <p className="mt-2 whitespace-pre-wrap text-muted">{d.body}{d.bodyTruncated ? "…" : ""}</p>
          {d.attachments.length > 0 && (
            <ul className="mt-2 space-y-1">
              {d.attachments.map((f) => (
                <li key={f.url}>
                  <a href={f.url} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
                    {f.name}
                  </a>
                  {f.read && <span className="text-faint"> · 글자 읽음</span>}
                </li>
              ))}
            </ul>
          )}
        </details>
      )}
      <div className="flex flex-wrap justify-end gap-2 border-t border-border pt-3">
        <button
          type="button"
          className="btn btn-sm"
          onClick={() => {
            void a.run(() => api.patchOpportunity(d.id, { progress: "skipped" }));
            toast("숨겼습니다 — 이력 탭에서 되돌릴 수 있습니다");
            closeQuery(["item", "view"]);
          }}
        >
          관심 없음
        </button>
        {d.flipped ? (
          <button type="button" className="btn btn-sm" onClick={() => flip(null)}>
            <Undo2 aria-hidden />
            등급 되돌리기
          </button>
        ) : d.grade === "match" ? (
          <button type="button" className="btn btn-sm" onClick={() => flip("other")}>
            관심 밖으로
          </button>
        ) : (
          <button type="button" className="btn btn-sm" onClick={() => flip("match")}>
            내 관심사로 표시
          </button>
        )}
        <SaveButton d={d} a={a} />
        <button type="button" className="btn btn-primary btn-sm" onClick={onDraft}>
          <Sparkles aria-hidden />
          {d.hasDraft ? "초안 보기" : "신청서 초안"}
        </button>
      </div>
    </>
  );
}

function SaveButton({ d, a }: { d: ActDetail; a: Act }) {
  if (d.progress && d.progress !== "saved")
    return (
      <Chip tone={PROGRESS_TONE[d.progress]} icon={<BookmarkCheck aria-hidden />}>
        {d.progressLabel}
      </Chip>
    );
  return (
    <button
      type="button"
      className={`btn btn-sm ${d.saved ? "border-primary bg-primary-soft text-primary" : ""}`}
      disabled={a.busy}
      onClick={() =>
        void a.run(
          () => api.patchOpportunity(d.id, { saved: !d.saved }),
          d.saved ? "담기를 풀었습니다" : d.deadline ? "담았습니다 — 신청 마감을 캘린더에 넣고 D-3 에 알려 드립니다" : "담았습니다 (마감을 못 읽어 캘린더에는 넣지 않았습니다)",
        )
      }
    >
      {d.saved ? <BookmarkCheck aria-hidden /> : <Bookmark aria-hidden />}
      {d.saved ? "담음" : "담기"}
    </button>
  );
}

function DraftView({ d, a, onMaterials }: { d: ActDetail; a: Act; onMaterials: (forId?: string) => void }) {
  const toast = useToast();
  const [text, setText] = useState(d.draft?.body ?? "");
  const [borrow, setBorrow] = useState("");
  const [making, setMaking] = useState(false);
  useEffect(() => {
    void Promise.resolve().then(() => setText(d.draft?.body ?? ""));
  }, [d.draft?.body]);

  const make = async (borrowFrom?: string) => {
    setMaking(true);
    try {
      const nd = await api.makeOpportunityDraft(d.id, borrowFrom);
      a.setDetail(nd);
      await a.reload();
      toast(borrowFrom ? "이전 초안의 문단을 가져왔습니다 — 이 공지에 맞게 고치세요" : "초안을 만들었습니다", { tone: "success" });
    } catch (e) {
      if (e instanceof Error && e.message === "needsMaterials") onMaterials(d.id);
      else toast(`초안을 만들지 못했습니다: ${e instanceof Error ? e.message : e}`, { tone: "error" });
    } finally {
      setMaking(false);
    }
  };
  const borrowSelect = d.otherDrafts.length > 0 && (
    <select
      className="field field-sm w-auto"
      aria-label="이전 초안 가져오기"
      value={borrow}
      onChange={(e) => {
        setBorrow(e.target.value);
        if (e.target.value) void make(e.target.value);
      }}
    >
      <option value="">이전 초안 가져오기…</option>
      {d.otherDrafts.map((o) => (
        <option key={o.id} value={o.id}>
          {o.title.slice(0, 40)}
        </option>
      ))}
    </select>
  );

  if (!d.draft)
    return (
      <div className="space-y-3">
        <EmptyState
          compact
          icon={<FileText />}
          title="아직 초안이 없습니다"
          action={
            <>
              <button type="button" className="btn btn-primary btn-sm" disabled={making} onClick={() => void make()}>
                <Sparkles aria-hidden />
                초안 만들기
              </button>
              {borrowSelect}
            </>
          }
        >
          모집 정보 정리 · {d.category === "rental" ? "사용 목적 · 사용 계획" : d.category === "contest" ? "참가 동기 · 아이디어·준비 계획" : "지원 동기 · 참여 계획"} · 제출 서류 · 신청 방법을 한 문서로 만듭니다. 처음 한 번은 진로·활동 같은 재료를 묻고(장학 초안 재료가 있으면 불러옵니다), 이후 초안에 다시 씁니다.
        </EmptyState>
        <p className="text-[12px] text-faint">이름·학번·연락처는 채우지 않습니다 — {"{{이름}}"} 자리로 남습니다. 재료에 없는 경험은 지어내지 않고 빈칸으로 둡니다. 초안을 만들면 담은 것으로 기록합니다.</p>
      </div>
    );

  const blanks = (text.match(/\{\{[^}]*\}\}/g) ?? []).length;
  const parts = text.split(/(\{\{[^}]*\}\})/g);
  const by = d.draft.generatedBy;
  return (
    <div className="space-y-3">
      {d.draft.stale && (
        <Banner tone="warn" action={<button type="button" className="btn btn-sm" onClick={() => void make()}>다시 만들기</button>}>
          원문이 바뀌었습니다 — 초안을 다시 만들어 확인하세요
        </Banner>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Chip tone={blanks ? "warn" : "ok"}>채워야 할 곳 {blanks}</Chip>
        <Chip square>{by === "llm" ? "LLM 작성" : by === "borrowed" ? "가져옴" : "템플릿"}</Chip>
        {d.draft.borrowed.map((b) => (
          <Chip key={b.from} tone="info">
            {b.title.slice(0, 24)}에서 가져옴
          </Chip>
        ))}
        <span className="ml-auto flex flex-wrap gap-2">
          {borrowSelect}
          <button type="button" className="btn btn-ghost btn-sm" disabled={making} onClick={() => void make()}>
            다시 만들기
          </button>
        </span>
      </div>
      <div className="max-h-[320px] overflow-y-auto rounded-xl border border-border bg-surface-2 p-3 text-[14px] leading-relaxed whitespace-pre-wrap" aria-label="빈칸 미리보기">
        {parts.map((p, i) =>
          p.startsWith("{{") ? (
            <mark key={i} className="rounded bg-blank px-1 text-text">
              {p}
            </mark>
          ) : (
            <span key={i}>{p}</span>
          ),
        )}
      </div>
      <label htmlFor="act-draft" className="label">
        편집
      </label>
      <textarea id="act-draft" className="field min-h-[240px] font-mono text-[13px]" value={text} onChange={(e) => setText(e.target.value)} />
      <div className="flex flex-wrap items-center justify-end gap-2">
        <span className="mr-auto text-[12px] text-faint">{d.draft.updatedAt ? `저장 ${fmtRelative(d.draft.updatedAt)}` : ""}</span>
        <button type="button" className="btn btn-primary btn-sm" disabled={a.busy || text === d.draft.body} onClick={() => void a.run(() => api.saveOpportunityDraft(d.id, text), "초안을 저장했습니다")}>
          저장
        </button>
      </div>
    </div>
  );
}

function ApplyView({ d, a }: { d: ActDetail; a: Act }) {
  const toast = useToast();
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(d.draft?.body ?? "");
      toast("초안을 복사했습니다", { tone: "success" });
    } catch {
      toast("복사하지 못했습니다 — 초안 탭에서 직접 선택해 주세요", { tone: "error" });
    }
  };
  const progress = (p: ActDetail["progress"], ok: string) => void a.run(() => api.patchOpportunity(d.id, { progress: p }), ok);
  return (
    <div className="space-y-3 text-[14px]">
      <Banner tone="danger" icon={<ShieldAlert aria-hidden />}>
        제출은 시스템이 하지 않습니다. 확인 후 본인이 직접 신청하세요.
      </Banner>
      <dl className="grid grid-cols-[72px_minmax(0,1fr)] items-center gap-3">
        <dt className="text-muted">신청 방법</dt>
        <dd className="flex flex-wrap items-center gap-2">
          <span className="min-w-0">{d.applyMethod ?? "원문 확인"}</span>
          <a href={d.applyUrl ?? d.url} target="_blank" rel="noopener noreferrer" className="btn btn-sm">
            {d.applyUrl ? "신청 링크" : "원문"}
            <ExternalLink aria-hidden />
          </a>
        </dd>
        <dt className="text-muted">마감</dt>
        <dd className="flex flex-wrap items-center gap-2">
          <span className="num">{d.deadline ? d.deadline.replace("T", " ") : "기간 미정 — 원문 확인"}</span>
          {d.deadline &&
            (d.onCalendar ? (
              <Chip tone="ok" icon={<CalendarCheck aria-hidden />}>
                캘린더에 있음
              </Chip>
            ) : (
              <button type="button" className="btn btn-sm" disabled={a.busy} onClick={() => void a.run(() => api.opportunityToCalendar(d.id), "캘린더에 넣었습니다")}>
                <CalendarPlus aria-hidden />
                캘린더에 넣기
              </button>
            ))}
        </dd>
        {d.contact && (
          <>
            <dt className="text-muted">문의</dt>
            <dd className="min-w-0 text-[13px]">{d.contact}</dd>
          </>
        )}
      </dl>
      <div>
        <p className="label">제출 서류·준비물</p>
        {d.documents.length === 0 ? (
          <p className="rounded-xl border border-dashed border-border-strong px-3 py-2 text-[13px] text-muted">공지에서 서류 목록을 읽지 못했습니다 — 원문·신청 양식을 확인하세요.</p>
        ) : (
          <ul className="divide-y divide-border rounded-xl border border-border">
            {d.documents.map((doc, i) => {
              const sent = !!d.state.todos[String(i)];
              return (
                <li key={doc} className="flex items-center gap-3 px-3 py-2">
                  <span className="min-w-0 flex-1">{doc}</span>
                  {sent ? (
                    <Chip tone="ok">할 일에 있음</Chip>
                  ) : (
                    <button type="button" className="btn btn-ghost btn-sm" disabled={a.busy} onClick={() => void a.run(() => api.opportunityToTodo(d.id, i), `'${doc.slice(0, 20)}' 할 일을 마감 하루 전으로 만들었습니다`)}>
                      <ListTodo aria-hidden />
                      할 일로 보내기
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
      <div className="flex flex-wrap items-center justify-end gap-2 border-t border-border pt-3">
        <span className="mr-auto">{d.progress && <Chip tone={PROGRESS_TONE[d.progress]}>{d.progressLabel}</Chip>}</span>
        <button type="button" className="btn btn-sm" disabled={!d.draft} onClick={() => void copy()} title={d.draft ? undefined : "초안이 아직 없습니다"}>
          <Copy aria-hidden />
          초안 전체 복사
        </button>
        {(!d.progress || d.progress === "saved" || d.progress === "draft") && (
          <>
            <button type="button" className="btn btn-sm" onClick={() => progress("skipped", "반려했습니다 — 이력 탭에서 되돌릴 수 있습니다")}>
              반려
            </button>
            <button type="button" className="btn btn-primary btn-sm" onClick={() => progress("approved", "제출 예정으로 표시했습니다 — 마감 D-3·D-1 에 알려 드립니다")}>
              승인 (제출 예정)
            </button>
          </>
        )}
        {d.progress === "approved" && (
          <button type="button" className="btn btn-primary btn-sm" onClick={() => progress("applied", "지원함으로 기록했습니다")}>
            지원했어요
          </button>
        )}
        {d.progress === "applied" && (
          <>
            <button type="button" className="btn btn-sm" onClick={() => progress("not_selected", "탈락으로 기록했습니다")}>
              탈락
            </button>
            <button type="button" className="btn btn-primary btn-sm" onClick={() => progress("selected", "선정을 축하합니다 — 이력에 남겼습니다")}>
              선정
            </button>
          </>
        )}
      </div>
    </div>
  );
}

/** 관심사 — C2 프로필의 interests 칸에 저장한다(F12-R13). 저장하면 프로필이 바뀌어 목록 전체가 다시 매겨진다(F12-R15). */
function InterestsModal({ open, onClose, data }: { open: boolean; onClose: () => void; data: ActOverview | null }) {
  const toast = useToast();
  const { updateProfile } = useAppData();
  const [tags, setTags] = useState<string[]>([]);
  const [keywords, setKeywords] = useState<string[]>([]);
  const [excludes, setExcludes] = useState<string[]>([]);
  const [kw, setKw] = useState("");
  const [ex, setEx] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    if (!open || !data) return;
    void Promise.resolve().then(() => {
      setTags(data.interests.tags);
      setKeywords(data.interests.keywords);
      setExcludes(data.interests.exclude);
    });
  }, [open, data]);
  const add = (v: string, list: string[], set: (x: string[]) => void, clear: () => void) => {
    const t = v.replace(/\s+/g, " ").trim();
    if (t.length < 2) {
      toast("두 글자 이상 입력하세요", { tone: "error" });
      return;
    }
    if (list.length >= 20) {
      toast("20개까지 넣을 수 있습니다", { tone: "error" });
      return;
    }
    if (!list.includes(t)) set([...list, t]);
    clear();
  };
  const save = async () => {
    setSaving(true);
    const interests: Interests = { tags, keywords, exclude: excludes };
    const doc = await updateProfile({ interests });
    setSaving(false);
    if (!doc) return;
    onClose();
    toast(tags.length || keywords.length ? `관심사를 저장했습니다 — 공지 ${data?.counts.total ?? 0}건을 다시 분류합니다` : "관심사를 비웠습니다 — 알림을 보내지 않습니다", { tone: "success" });
  };
  const chipList = (list: string[], set: (x: string[]) => void) =>
    list.map((k) => (
      <span key={k} className="chip bg-surface-3 text-text">
        {k}
        <button type="button" aria-label={`${k} 삭제`} onClick={() => set(list.filter((x) => x !== k))}>
          <X aria-hidden />
        </button>
      </span>
    ));
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="관심사 설정"
      footer={
        <button type="button" className="btn btn-primary" disabled={saving || !data} onClick={() => void save()}>
          저장
        </button>
      }
    >
      <div className="space-y-5 pt-1">
        <fieldset>
          <legend className="label">태그 — 제목에 걸리면 &lsquo;내 관심사&rsquo;, 본문에만 걸리면 &lsquo;관련 있음&rsquo;</legend>
          <div className="flex flex-wrap gap-2">
            {(data?.tags ?? []).map((t) => {
              const on = tags.includes(t.key);
              return (
                <button key={t.key} type="button" title={`${t.words.join(", ")} …`} aria-pressed={on} onClick={() => setTags(on ? tags.filter((x) => x !== t.key) : [...tags, t.key])} className={`btn btn-sm ${on ? "border-primary bg-primary-soft text-primary" : ""}`}>
                  {t.key}
                </button>
              );
            })}
          </div>
        </fieldset>
        {[
          { label: "키워드 — 제목·본문 어디든 걸리면 '내 관심사' (최대 20)", list: keywords, set: setKeywords, v: kw, setV: setKw, ph: "예: 반도체" },
          { label: "제외 — 걸리면 무조건 '관심 밖'", list: excludes, set: setExcludes, v: ex, setV: setEx, ph: "예: 대학원생" },
        ].map((f) => (
          <div key={f.label}>
            <p className="label">{f.label}</p>
            <div className="flex flex-wrap items-center gap-2">
              {chipList(f.list, f.set)}
              <form
                className="flex gap-1"
                onSubmit={(e) => {
                  e.preventDefault();
                  add(f.v, f.list, f.set, () => f.setV(""));
                }}
              >
                <input className="field field-sm w-32" value={f.v} onChange={(e) => f.setV(e.target.value)} placeholder={f.ph} aria-label={f.label} />
              </form>
            </div>
          </div>
        ))}
        <p className="hint">공백·대소문자는 무시하고, 영문 세 글자 이하(AI·SW)는 앞에 영문이 붙으면 걸리지 않습니다(RAIN 의 AI). 관심사는 내 프로필에 저장되고 이 PC 밖으로 나가지 않습니다.</p>
      </div>
    </Modal>
  );
}

function MaterialsModal({ open, onClose, onSaved }: { open: boolean; onClose: () => void; onSaved: () => void }) {
  const toast = useToast();
  const [m, setM] = useState<ActMaterials | null>(null);
  useEffect(() => {
    if (!open) return;
    void api.opportunityMaterials().then(setM, () => setM(null));
  }, [open]);
  const set = (k: keyof ActMaterials, v: string) => m && setM({ ...m, [k]: v });
  const fields: { k: "careerGoal" | "activities" | "skills" | "highlights"; label: string; ph: string }[] = [
    { k: "careerGoal", label: "진로 목표", ph: "예: 임베디드 AI 엔지니어" },
    { k: "activities", label: "활동 경험", ph: "예: 교내 AI 경진대회 참가, 학과 튜터링 2학기" },
    { k: "skills", label: "보유 역량·도구 (선택)", ph: "예: 파이썬, PyTorch, 피그마 — 공모전·인턴 초안에 쓰입니다" },
    { k: "highlights", label: "강조하고 싶은 점 (선택)", ph: "예: 꾸준함, 팀 프로젝트 리더 경험" },
  ];
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="초안 재료 (대외활동)"
      footer={
        <>
          {m?.exists && (
            <button
              type="button"
              className="btn btn-ghost mr-auto"
              onClick={async () => {
                setM(await api.deleteOpportunityMaterials());
                toast("초안 재료를 지웠습니다");
              }}
            >
              재료 지우기
            </button>
          )}
          <button
            type="button"
            className="btn btn-primary"
            disabled={!m}
            onClick={async () => {
              if (!m) return;
              await api.putOpportunityMaterials({ careerGoal: m.careerGoal, activities: m.activities, skills: m.skills, highlights: m.highlights });
              toast("저장했습니다 — 다음 초안부터 쓰입니다", { tone: "success" });
              onClose();
              onSaved();
            }}
          >
            저장
          </button>
        </>
      }
    >
      <div className="space-y-4 pt-1">
        <p className="hint">한 번 적어 두면 이후 초안에 다시 쓰입니다(이미 만든 초안은 그대로). 적은 것만 근거로 쓰고, 없는 경험은 지어내지 않고 빈칸으로 남깁니다. 장학 초안 재료와 따로 저장되고 따로 지울 수 있습니다.</p>
        {m?.from === "scholarship" && <p className="text-[12px] text-faint">장학 초안 재료를 불러왔습니다 — 저장하면 대외활동 초안에 쓰입니다.</p>}
        {m?.from === "profile" && <p className="text-[12px] text-faint">프로필에 적어 둔 초안 재료를 불러왔습니다.</p>}
        {fields.map((f) => (
          <div key={f.k}>
            <label htmlFor={`act-mat-${f.k}`} className="label">
              {f.label}
            </label>
            <textarea id={`act-mat-${f.k}`} className="field min-h-[72px] text-[14px]" placeholder={f.ph} value={m?.[f.k] ?? ""} onChange={(e) => set(f.k, e.target.value)} />
          </div>
        ))}
      </div>
    </Modal>
  );
}

function HistoryTab({ onChanged }: { onChanged: () => void }) {
  const [h, setH] = useState<ActHistory | null>(null);
  const toast = useToast();
  const load = () => void api.opportunityHistory().then(setH, () => setH({ semesters: [] }));
  useEffect(load, []);
  if (!h) return <SkeletonList rows={4} />;
  if (h.semesters.length === 0)
    return (
      <EmptyState icon={<Trophy />} title="아직 기록이 없습니다">
        담거나 초안을 만들고 지원·선정을 표시하면 학기별로 여기 남습니다. 관심 없음으로 숨긴 공지도 여기서 되돌립니다.
      </EmptyState>
    );
  return (
    <div className="space-y-4">
      {h.semesters.map((g) => (
        <Section key={g.semester} title={`${g.semester.replace("-", "년 ")}학기`} action={<span className="num text-[13px] text-muted">담음 {g.saved} · 지원 {g.applied} · 선정 {g.selected}</span>}>
          <ul className="divide-y divide-border">
            {g.items.map((it) => (
              <li key={it.id} className="flex flex-wrap items-center gap-3 py-3 text-[14px]">
                <button type="button" className="min-w-0 flex-1 text-left font-medium hover:text-primary" onClick={() => navigateQuery({ tab: null, item: it.id }, "push")}>
                  {it.title}
                </button>
                {it.categoryLabel && <Chip square>{it.categoryLabel}</Chip>}
                <StatusBadge tone={PROGRESS_TONE[it.progress]}>{it.progressLabel}</StatusBadge>
                {it.progress === "skipped" && (
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={async () => {
                      await api.patchOpportunity(it.id, { progress: null });
                      toast("되돌렸습니다 — 목록에 다시 보입니다");
                      load();
                      onChanged();
                    }}
                  >
                    되돌리기
                  </button>
                )}
              </li>
            ))}
          </ul>
        </Section>
      ))}
    </div>
  );
}

function SourcesTab({ onSync }: { onSync: () => void }) {
  const toast = useToast();
  const { profile } = useAppData();
  const [d, setD] = useState<ActSources | null>(null);
  const load = () => void api.opportunitySources().then(setD, () => setD(null));
  useEffect(load, []);
  if (!d) return <SkeletonList rows={6} />;
  const toggle = async (src: SchSource, on: boolean) => {
    const r = await api.patchOpportunitySource(src.key, on === src.relevance.default ? null : on);
    setD({ ...d, sources: d.sources.map((x) => (x.key === r.key ? r : x)) });
    toast(on ? `${src.name} — 다음 수집부터 읽습니다` : `${src.name} — 끄면 그 원천의 공지가 목록에서 빠집니다`);
  };
  const p = profile?.profile;
  return (
    <div className="space-y-4">
      <Banner
        tone="neutral"
        action={
          <button type="button" className="btn btn-sm" disabled={d.sync.running} onClick={onSync}>
            <RefreshCw className={d.sync.running ? "animate-spin" : ""} aria-hidden />
            지금 수집
          </button>
        }
      >
        장학과 같은 원천을 읽고 장학이 아닌 공지를 모읍니다 (장학만 올라오는 &lsquo;장학안내&rsquo; 분류·상시 장학 안내는 빼고).{" "}
        {p?.department ? (
          <>
            <b>{p.deptPath ?? p.department}</b> 기준으로 관련 사업단·내 학과 공지 게시판을 켰습니다.
          </>
        ) : (
          "프로필에 소속을 넣으면 학과에 맞는 사업단·학과 게시판을 자동으로 켭니다."
        )}{" "}
        켜고 끈 것은 장학과 따로 저장됩니다. {d.autosync ? `앱이 켜져 있으면 매일 ${d.slots.join(" · ")} (장학 수집 뒤)에 모읍니다.` : "이 실행에서는 자동 수집이 꺼져 있습니다 — '지금 수집'으로 모읍니다."}
      </Banner>
      {(["school", "office", "project", "mine"] as const).map((g) => (
        <Section key={g} title={GROUP_LABEL[g]} padded={false}>
          <ul className="divide-y divide-border">
            {d.sources
              .filter((x) => x.group === g)
              .map((src) => (
                <li key={src.key} className="flex flex-wrap items-start gap-3 px-4 py-3 md:px-5">
                  <div className="min-w-0 flex-1 basis-[60%]">
                    <p className="flex flex-wrap items-center gap-2 text-[14px] font-semibold">
                      {src.url ? (
                        <a href={src.url} target="_blank" rel="noopener noreferrer" className="hover:text-primary hover:underline">
                          {src.name}
                        </a>
                      ) : (
                        src.name
                      )}
                      <Chip tone={RELEVANCE[src.relevance.level].tone} square>
                        {RELEVANCE[src.relevance.level].label}
                      </Chip>
                      {src.relay && <Chip square>학교 공지로 받음</Chip>}
                    </p>
                    <p className="text-[13px] text-muted">
                      {src.org} · {src.relevance.why}
                    </p>
                    {src.why && <p className="mt-0.5 text-[12px] text-faint">{src.why}</p>}
                    {src.target && (
                      <p className="mt-0.5 text-[12px] text-faint">
                        {src.target.homepage
                          ? `${src.target.listedAs} 홈페이지 ${src.target.board ? `› ${src.target.boardLabel ?? "공지"} (장학 글은 장학 화면으로)` : "— 다음 수집 때 공지 게시판을 찾습니다"}`
                          : "프로필 소속의 홈페이지를 학교 목록에서 찾지 못했습니다"}
                      </p>
                    )}
                    {!src.relay && (
                      <p className={`mt-0.5 text-[12px] ${src.error ? "text-danger-text" : "text-faint"}`}>
                        {src.error ? `실패: ${src.error}` : src.lastOkAt ? `마지막 수집 ${fmtRelative(src.lastOkAt)} · 대외활동 글 ${src.lastCount ?? 0}건 · 모은 공지 ${src.stored}건` : "아직 수집 전"}
                      </p>
                    )}
                  </div>
                  <Toggle checked={src.enabled} onChange={(v) => void toggle(src, v)} label={`${src.name} ${src.enabled ? "끄기" : "켜기"}`} />
                </li>
              ))}
          </ul>
        </Section>
      ))}
      {d.log.length > 0 && (
        <details className="rounded-xl border border-border px-4 py-3 text-[12px] text-muted">
          <summary className="cursor-pointer font-semibold">수집 기록</summary>
          <pre className="mt-2 whitespace-pre-wrap">{d.log.join("\n")}</pre>
        </details>
      )}
    </div>
  );
}
