"use client";

import { useEffect, useMemo, useState } from "react";
import {
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
  ShieldAlert,
  Sparkles,
  Undo2,
  X,
} from "lucide-react";
import { Page, PageHeader, Section, Group, Toggle } from "@/components/ui/Layout";
import { Tabs } from "@/components/ui/Tabs";
import { Banner, EmptyState, ErrorPanel, SkeletonList, SyncBanner } from "@/components/ui/Feedback";
import { Chip, DdayChip, StatusBadge, type Tone } from "@/components/ui/Chip";
import { Modal } from "@/components/ui/Modal";
import { OcrText } from "@/components/ui/OcrText";
import { DraftBasicFields } from "@/components/ui/DraftBasicFields";
import { useToast } from "@/components/ui/Toast";
import { useAppData } from "@/components/app/AppData";
import { closeQuery, navigateQuery, useQueryParam, useQueryValue } from "@/lib/useQueryState";
import { useIsXl } from "@/lib/useMediaQuery";
import { useScholarships } from "@/lib/useScholarships";
import { api } from "@/lib/api";
import { fmtRelative, parseLocal } from "@/lib/dates";
import { FLAG_LABEL, INCOME_BRACKETS, REGIONS, type ProfilePatch } from "@/lib/profile";
import {
  GROUP_LABEL,
  PROGRESS_TONE,
  RELEVANCE,
  VERDICT_TONE,
  syncText,
  type Reason,
  type SchDetail,
  type SchHistory,
  type SchItem,
  type SchMaterials,
  type SchSource,
  type SchSources,
  type SensitiveKey,
} from "@/lib/scholarships";

// /scholarships — 장학 (F11). 2026-10-09 '기회'(/opportunities)에서 분리 — 대외활동(F12·F13)은 /opportunities 에 남았다.
// 돈이 걸린 화면: 판정 근거와 "제출은 본인이 한다"는 사실이 한순간도 흐려지면 안 된다 (Frontend-Route 16절).

const TABS = ["list", "history", "sources"] as const;
const KINDS = ["notice", "catalog"] as const;
const VIEWS = ["match", "draft", "apply"] as const;

const deadlineDate = (s: string) => parseLocal(s.length > 10 ? s : `${s}T23:59`);
const fmtDl = (s: string | null) => (s ? s.replace("T", " ").slice(5, 16).replace("-", "/") : "기간 미정");

export default function ScholarshipsPage() {
  const [tab] = useQueryParam("tab", "list", TABS);
  const [kind, setKind] = useQueryParam("kind", "notice", KINDS);
  const [show, setShow] = useQueryParam("show", "", ["", "all"] as const);
  const itemId = useQueryValue("item");
  const isXl = useIsXl();
  const s = useScholarships(itemId);
  const [materialsOpen, setMaterialsOpen] = useState(false);
  const [materialsFor, setMaterialsFor] = useState<string | null>(null); // 초안을 만들려다 재료부터 묻는 중이면 그 장학 id
  const openMaterials = (forId: string | null = null) => {
    setMaterialsFor(forId);
    setMaterialsOpen(true);
  };
  const data = s.data;

  const inKind = useMemo(() => (data?.items ?? []).filter((i) => i.kind === kind), [data, kind]);
  const groups = useMemo(
    () => [
      { key: "해당", items: inKind.filter((o) => o.verdict === "eligible"), dot: "var(--ok)", fold: false, hideEmpty: true },
      { key: "확인 필요", items: inKind.filter((o) => o.verdict === "needs_review"), dot: "var(--warn)", fold: false, hideEmpty: false },
      { key: "비해당·마감·대상 아님", items: inKind.filter((o) => ["ineligible", "expired", "not_applicable"].includes(o.verdict)), dot: "var(--border-strong)", fold: true, hideEmpty: true },
    ],
    [inKind],
  );

  const sync = data?.sync;
  const meta = data && (
    <span className="num">
      {data.lastOkAt ? `수집 ${fmtRelative(data.lastOkAt)}` : "아직 수집 전"}
      {data.catalogAt ? ` · 상시 안내 ${data.catalogAt.slice(5, 10).replace("-", "/")}` : ""}
    </span>
  );

  return (
    <Page wide>
      <PageHeader
        icon={<HandCoins />}
        title="장학"
        subtitle="학교 장학안내 · 부서 · 사업단 · 내 학과 게시판을 모아 내 조건과 대조합니다"
        meta={meta}
        actions={
          <>
            <button type="button" className="btn btn-sm" onClick={() => openMaterials()}>
              <NotebookPen aria-hidden />
              초안 재료
            </button>
            <button type="button" className="btn btn-primary btn-sm" disabled={!!sync?.running} onClick={() => void s.sync()}>
              <RefreshCw className={sync?.running ? "animate-spin" : ""} aria-hidden />
              {sync?.running ? "모으는 중" : "지금 수집"}
            </button>
          </>
        }
      />

      <div className="mb-5 space-y-3">
        {sync?.running && <SyncBanner state="running">{syncText(sync)} 게시판마다 1.5초 간격으로 읽어 처음에는 몇 분 걸립니다.</SyncBanner>}
        {data && !data.profile.exists && (
          <Banner tone="warn" action={<a className="btn btn-sm" href="/settings/profile">프로필 넣기</a>}>
            학년·학과를 넣으면 나에게 맞는 장학을 골라 드립니다. 학과에 맞는 사업단·학과 게시판도 그때 켜집니다.
          </Banner>
        )}
        {data && data.profile.exists && data.profile.missing.length > 0 && (
          <Banner tone="neutral">
            프로필에 {data.profile.missing.map((m) => ({ grade: "학년", college: "단과대학", department: "학과" })[m] ?? m).join("·")}이 없어 일부 조건은 &lsquo;모름&rsquo;으로 둡니다.
          </Banner>
        )}
      </div>

      <Tabs
        className="mb-5"
        label="장학 화면"
        value={tab}
        onChange={(t) => navigateQuery({ tab: t === "list" ? null : t, item: null, view: null, show: null }, "replace")}
        items={[
          { key: "list", label: "장학", count: data ? data.counts.eligible + data.counts.review : undefined },
          { key: "history", label: "이력" },
          { key: "sources", label: "원천" },
        ]}
      />

      {tab === "history" ? (
        <HistoryTab onChanged={() => void s.reload()} />
      ) : tab === "sources" ? (
        <SourcesTab onSync={() => void s.sync()} />
      ) : s.error ? (
        <ErrorPanel message={`장학 목록을 불러오지 못했습니다: ${s.error}`} onRetry={() => void s.reload()} />
      ) : s.loading || !data ? (
        <SkeletonList />
      ) : data.items.length === 0 ? (
        <EmptyState
          icon={<HandCoins />}
          title="아직 수집한 장학 공지가 없습니다"
          action={
            <button type="button" className="btn btn-primary btn-sm" disabled={!!sync?.running} onClick={() => void s.sync()}>
              <RefreshCw aria-hidden />
              지금 수집
            </button>
          }
        >
          앱이 켜져 있으면 매일 06:00 · 18:00 에 자동으로 모읍니다. 처음 수집은 몇 분 걸립니다.
        </EmptyState>
      ) : (
        <>
          <Tabs
            variant="pill"
            size="sm"
            className="mb-4"
            label="장학 종류"
            value={kind}
            onChange={(k) => setKind(k === "notice" ? null : k)}
            items={[
              { key: "notice", label: "공지", count: data.counts.eligible + data.counts.review },
              { key: "catalog", label: "상시 장학", count: data.counts.catalogEligible + data.counts.catalogReview },
            ]}
          />
          {kind === "catalog" && (
            <p className="mb-4 text-[13px] text-muted">
              공지 없이 학교가 매 학기 뽑는 장학입니다(대표 홈페이지 &lsquo;교내·교외 장학금&rsquo; 안내, 주 1회 확인). 신청 시기는 학생과 공지·학사정보시스템에서 확인하세요.
            </p>
          )}
          {kind === "notice" && data.counts.eligible === 0 && (
            <p className="mb-4 rounded-xl border border-dashed border-border-strong px-4 py-3 text-[14px] text-muted">
              지금 확실히 해당하는 장학은 없습니다 — 확인 필요 {data.counts.review}건은 조건을 하나씩 확인해 주세요.
            </p>
          )}
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
                      <p className="rounded-xl border border-dashed border-border-strong px-4 py-3 text-[14px] text-muted">없습니다</p>
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
                {s.detail ? (
                  <Detail d={s.detail} s={s} onMaterials={openMaterials} />
                ) : (
                  <SkeletonList rows={4} />
                )}
              </aside>
            )}
          </div>
        </>
      )}

      <Modal open={!!itemId && !isXl && tab === "list"} onClose={() => closeQuery(["item", "view"])} title={s.detail?.title} size="lg">
        {s.detail && <Detail d={s.detail} s={s} onMaterials={openMaterials} bare />}
      </Modal>
      <MaterialsModal
        open={materialsOpen}
        onClose={() => setMaterialsOpen(false)}
        onSaved={() => {
          if (materialsFor) void s.run(() => api.makeScholarshipDraft(materialsFor), "초안을 만들었습니다");
          setMaterialsFor(null);
        }}
      />
    </Page>
  );
}

function ItemRow({ o, active }: { o: SchItem; active: boolean }) {
  const dim = ["expired", "not_applicable", "ineligible"].includes(o.verdict);
  return (
    <li className="border-b border-border last:border-b-0">
      <button
        type="button"
        onClick={() => navigateQuery({ item: o.id, view: null }, "push")}
        className={`flex w-full flex-wrap items-center gap-x-3 gap-y-1.5 px-4 py-3 text-left transition-colors hover:bg-surface-2 ${active ? "bg-primary-soft" : ""} ${dim ? "opacity-70" : ""}`}
      >
        <span className="min-w-0 flex-1 basis-[55%]">
          <span className={`block truncate text-[15px] font-semibold ${o.verdict === "expired" ? "line-through" : ""}`}>{o.title}</span>
          <span className="block truncate text-[13px] text-muted">
            {o.org || o.sourceName}
            {o.amount && o.kind === "catalog" ? ` · ${o.amount.replace(/^지급액:\s*/, "").slice(0, 40)}` : ""}
            {o.unit ? ` · ${o.unit.org}` : ""}
          </span>
        </span>
        <span className="flex flex-wrap items-center gap-1.5">
          <StatusBadge tone={VERDICT_TONE[o.verdict]} unknown={o.verdict === "needs_review"}>
            {o.label}
          </StatusBadge>
          {o.hint && <Chip tone={o.hint === "정보 입력 필요" ? "warn" : "neutral"} square>{o.hint}</Chip>}
          {o.flipped && <Chip tone="accent">내가 바꿈</Chip>}
          {o.progress && <Chip tone={PROGRESS_TONE[o.progress]}>{o.progressLabel}</Chip>}
          {o.isNew && o.kind === "notice" && <Chip tone="primary" square>새 글</Chip>}
          {o.deadline && o.verdict !== "expired" && <DdayChip date={deadlineDate(o.deadline)} />}
        </span>
      </button>
    </li>
  );
}

type Sch = ReturnType<typeof useScholarships>;

function Detail({ d, s, onMaterials, bare }: { d: SchDetail; s: Sch; onMaterials: (forId?: string) => void; bare?: boolean }) {
  const [view, setView] = useQueryParam("view", "match", VIEWS);
  const body = (
    <div className="space-y-4">
      <p className="flex flex-wrap items-center gap-2 text-[14px] text-muted">
        <span>{d.org || d.sourceName}</span>
        {d.scholarshipKind && <Chip square>{d.scholarshipKind}</Chip>}
        <span>· 신청 ~{fmtDl(d.deadline)}</span>
        {d.deadline && d.verdict !== "expired" && <DdayChip date={deadlineDate(d.deadline)} />}
        <StatusBadge tone={VERDICT_TONE[d.verdict]} unknown={d.verdict === "needs_review"}>
          {d.label}
        </StatusBadge>
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
        onChange={(v) => setView(v === "match" ? null : v)}
        items={[
          { key: "match", label: "판정" },
          { key: "draft", label: d.hasDraft ? "초안" : "초안 만들기" },
          { key: "apply", label: "제출 준비" },
        ]}
      />
      {view === "match" && <MatchView d={d} s={s} onDraft={() => setView("draft")} />}
      {view === "draft" && <DraftView d={d} s={s} onMaterials={onMaterials} />}
      {view === "apply" && <ApplyView d={d} s={s} />}
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

const STATUS_TEXT: Record<Reason["status"], { label: string; tone: Tone }> = {
  pass: { label: "충족", tone: "ok" },
  fail: { label: "미달", tone: "danger" },
  unknown: { label: "모름", tone: "warn" },
};

function MatchView({ d, s, onDraft }: { d: SchDetail; s: Sch; onDraft: () => void }) {
  const toast = useToast();
  const rows = d.reasons.filter((r) => !["other", "exclusion"].includes(r.field));
  const others = d.reasons.filter((r) => r.field === "other" || r.field === "exclusion");
  const flip = (verdict: "eligible" | "ineligible" | null) =>
    void s.run(() => api.patchScholarship(d.id, { verdict }), verdict ? `${verdict === "eligible" ? "해당" : "비해당"}으로 표시했습니다` : "시스템 판정으로 되돌렸습니다");
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
              <button type="button" className="btn btn-sm" onClick={() => void s.run(() => api.patchScholarship(d.id, { askedApplied: true }))}>
                아니요
              </button>
              <button type="button" className="btn btn-primary btn-sm" onClick={() => void s.run(() => api.patchScholarship(d.id, { progress: "applied" }), "신청함으로 기록했습니다")}>
                신청했어요
              </button>
            </>
          }
        >
          마감이 지났습니다 — 신청하셨나요?
        </Banner>
      )}
      {rows.length === 0 ? (
        <Banner tone="neutral">자동으로 읽은 조건이 없습니다 — 원문에서 자격 요건을 확인하세요.</Banner>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-border">
          <table className="w-full min-w-[560px] text-[14px]">
            <thead className="bg-surface-2 text-left text-[12px] text-muted">
              <tr>
                <th className="px-3 py-2 font-semibold">조건</th>
                <th className="px-3 py-2 font-semibold">공지</th>
                <th className="px-3 py-2 font-semibold">내 값</th>
                <th className="px-3 py-2 font-semibold">판정</th>
                <th className="px-3 py-2 font-semibold">근거</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <ReasonRow key={`${r.field}-${i}`} r={r} />
              ))}
            </tbody>
          </table>
        </div>
      )}
      {others.length > 0 && (
        <div className="rounded-xl border border-border px-3 py-2.5">
          <p className="mb-1.5 text-[12px] font-semibold text-muted">자동 판정하지 않는 조건 — 원문으로 확인하세요</p>
          <ul className="space-y-1 text-[13px]">
            {others.map((r, i) => (
              <li key={i} className="flex gap-2">
                <Chip tone={r.field === "exclusion" ? "danger" : "neutral"} square>
                  {r.field === "exclusion" ? "제외" : "기타"}
                </Chip>
                <span className="min-w-0">{r.need}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {d.ocrText && <OcrText text={d.ocrText} />}
      {d.alsoPostedAt.length > 0 && (
        <p className="text-[12px] text-faint">같은 글: {d.alsoPostedAt.map((a) => a.source_name).join(" · ")}</p>
      )}
      <div className="flex flex-wrap justify-end gap-2 border-t border-border pt-3">
        <button
          type="button"
          className="btn btn-sm"
          onClick={() => {
            void s.run(() => api.patchScholarship(d.id, { progress: "skipped" }));
            toast("숨겼습니다 — 이력 탭에서 되돌릴 수 있습니다");
            closeQuery(["item", "view"]);
          }}
        >
          관심 없음
        </button>
        {d.flipped ? (
          <button type="button" className="btn btn-sm" onClick={() => flip(null)}>
            <Undo2 aria-hidden />
            판정 되돌리기
          </button>
        ) : d.verdict === "eligible" ? (
          <button type="button" className="btn btn-sm" onClick={() => flip("ineligible")}>
            비해당으로 표시
          </button>
        ) : (
          <button type="button" className="btn btn-sm" onClick={() => flip("eligible")}>
            해당으로 표시
          </button>
        )}
        <button type="button" className="btn btn-primary btn-sm" onClick={onDraft}>
          <Sparkles aria-hidden />
          {d.hasDraft ? "초안 보기" : "초안 만들기"}
        </button>
      </div>
    </>
  );
}

function ReasonRow({ r }: { r: Reason }) {
  const [skip, setSkip] = useState(false);
  const st = STATUS_TEXT[r.status];
  return (
    <>
      <tr className="border-t border-border first:border-t-0 align-top">
        <td className="px-3 py-2.5 font-medium whitespace-nowrap">{r.label}</td>
        <td className="min-w-[96px] px-3 py-2.5 text-[13px]">{r.need ?? "—"}</td>
        <td className="num min-w-[72px] px-3 py-2.5">{r.mine ?? <span className="text-faint">—</span>}</td>
        <td className="px-3 py-2.5 whitespace-nowrap">
          <StatusBadge tone={st.tone} unknown={r.status === "unknown"}>
            {st.label}
          </StatusBadge>
        </td>
        <td className="px-3 py-2.5 text-[13px] text-muted">
          <span title={r.message}>{r.evidence ? `“${r.evidence.slice(0, 90)}${r.evidence.length > 90 ? "…" : ""}”` : r.message}</span>
        </td>
      </tr>
      {r.status === "unknown" && r.sensitive && !skip && (
        <tr className="bg-warn-soft/40">
          <td colSpan={5} className="px-3 py-3">
            <SensitiveInput k={r.sensitive} message={r.message} onSkip={() => setSkip(true)} />
          </td>
        </tr>
      )}
    </>
  );
}

const SENSITIVE_WHY: Record<SensitiveKey, string> = {
  incomeBracket: "학자금 지원구간 — 이 장학의 소득 조건 확인에만 씁니다",
  residenceRegion: "거주 지역(시·도) — 지역 장학의 주소 조건 확인에만 씁니다",
  highSchoolRegion: "출신 고교 지역(시·도) — 지역인재·지역 장학 확인에만 씁니다",
  flags: "해당 사항 — 보훈·장애·다자녀 등 대상 장학 확인에만 씁니다",
};

/** 민감정보는 필요해질 때 그 자리에서 (F11-R30~R33) — 저장하면 프로필(C2)에 들어가고 관련 공지를 모두 다시 판정한다. PC 밖으로 나가지 않는다. */
function SensitiveInput({ k, message, onSkip }: { k: SensitiveKey; message: string; onSkip: () => void }) {
  const { profile, updateProfile } = useAppData();
  const toast = useToast();
  const cur = profile?.profile;
  const [income, setIncome] = useState<string>(cur?.incomeBracket != null ? String(cur.incomeBracket) : "");
  const [region, setRegion] = useState<string>((k === "highSchoolRegion" ? cur?.highSchoolRegion : cur?.residenceRegion) ?? "");
  const [flags, setFlags] = useState<Record<string, boolean>>(cur?.flags ?? {});
  const save = async () => {
    const patch: ProfilePatch =
      k === "incomeBracket"
        ? { incomeBracket: income === "" ? null : Number(income) }
        : k === "flags"
          ? { flags: Object.fromEntries(Object.entries(flags).filter(([, v]) => v)) }
          : { [k]: region || null };
    const doc = await updateProfile(patch);
    if (doc) toast("저장했습니다 — 관련 장학을 모두 다시 판정합니다", { tone: "success" });
  };
  return (
    <div className="space-y-2">
      <p className="flex items-start gap-1.5 text-[13px] text-warn-text">
        <ShieldAlert className="mt-0.5 size-4 flex-none" aria-hidden />
        <span>
          {message}
          <br />
          <span className="text-muted">{SENSITIVE_WHY[k]} · 이 PC 밖으로 나가지 않고, 내 프로필에서 언제든 지울 수 있습니다.</span>
        </span>
      </p>
      <div className="flex flex-wrap items-center gap-2">
        {k === "incomeBracket" && (
          <select className="field field-sm w-auto" aria-label="학자금 지원구간" value={income} onChange={(e) => setIncome(e.target.value)}>
            <option value="">선택</option>
            {INCOME_BRACKETS.map((n) => (
              <option key={n} value={n}>
                {n === 0 ? "기초·차상위(0구간)" : `${n}구간`}
              </option>
            ))}
          </select>
        )}
        {(k === "residenceRegion" || k === "highSchoolRegion") && (
          <select className="field field-sm w-auto" aria-label={k === "residenceRegion" ? "거주 지역" : "출신 고교 지역"} value={region} onChange={(e) => setRegion(e.target.value)}>
            <option value="">선택</option>
            {REGIONS.map((r) => (
              <option key={r}>{r}</option>
            ))}
          </select>
        )}
        {k === "flags" &&
          Object.entries(FLAG_LABEL).map(([key, label]) => (
            <label key={key} className="inline-flex items-center gap-1.5 text-[13px]">
              <input type="checkbox" className="size-4 accent-[var(--primary)]" checked={!!flags[key]} onChange={(e) => setFlags({ ...flags, [key]: e.target.checked })} />
              {label}
            </label>
          ))}
        <button type="button" className="btn btn-primary btn-sm" onClick={() => void save()}>
          {k === "flags" ? "저장 (해당 없음도 저장)" : "저장"}
        </button>
        <button type="button" className="btn btn-ghost btn-sm" onClick={onSkip}>
          건너뛰기
        </button>
      </div>
    </div>
  );
}

function DraftView({ d, s, onMaterials }: { d: SchDetail; s: Sch; onMaterials: (forId?: string) => void }) {
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
      const nd = await api.makeScholarshipDraft(d.id, borrowFrom);
      s.setDetail(nd);
      await s.reload();
      toast(borrowFrom ? "이전 초안의 문단을 가져왔습니다 — 이 장학에 맞게 고치세요" : "초안을 만들었습니다", { tone: "success" });
    } catch (e) {
      if (e instanceof Error && e.message === "needsMaterials") onMaterials(d.id);
      else toast(`초안을 만들지 못했습니다: ${e instanceof Error ? e.message : e}`, { tone: "error" });
    } finally {
      setMaking(false);
    }
  };

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
              {d.otherDrafts.length > 0 && (
                <select className="field field-sm w-auto" aria-label="이전 초안 가져오기" value={borrow} onChange={(e) => e.target.value && void make(e.target.value)}>
                  <option value="">이전 초안 가져오기…</option>
                  {d.otherDrafts.map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.title.slice(0, 40)}
                    </option>
                  ))}
                </select>
              )}
            </>
          }
        >
          사실 정리 · 지원 동기 · 학업 계획 · 제출 서류 · 신청 방법을 한 문서로 만듭니다. 처음 한 번은 진로·활동 같은 재료를 묻고, 이후 초안에 다시 씁니다.
        </EmptyState>
        <p className="text-[12px] text-faint">이름·학번은 채우지 않습니다 — {"{{이름}}"} 자리로 남습니다. 재료에 없는 경험은 지어내지 않고 빈칸으로 둡니다.</p>
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
      {d.warning && <Banner tone="warn">{d.warning} — 그래도 지원하려면 원문 조건을 다시 확인하세요</Banner>}
      <div className="flex flex-wrap items-center gap-2">
        <Chip tone={blanks ? "warn" : "ok"}>채워야 할 곳 {blanks}</Chip>
        <Chip square>{by === "llm" ? "LLM 작성" : by === "borrowed" ? "가져옴" : "템플릿"}</Chip>
        {d.draft.borrowed.map((b) => (
          <Chip key={b.from} tone="info">
            {b.title.slice(0, 24)}에서 가져옴
          </Chip>
        ))}
        <span className="ml-auto flex flex-wrap gap-2">
          {d.otherDrafts.length > 0 && (
            <select className="field field-sm w-auto" aria-label="이전 초안 가져오기" value={borrow} onChange={(e) => { setBorrow(e.target.value); if (e.target.value) void make(e.target.value); }}>
              <option value="">이전 초안 가져오기…</option>
              {d.otherDrafts.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.title.slice(0, 40)}
                </option>
              ))}
            </select>
          )}
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
      <label htmlFor="sch-draft" className="label">
        편집
      </label>
      <textarea id="sch-draft" className="field min-h-[240px] font-mono text-[13px]" value={text} onChange={(e) => setText(e.target.value)} />
      <div className="flex flex-wrap items-center justify-end gap-2">
        <span className="mr-auto text-[12px] text-faint">{d.draft.updatedAt ? `저장 ${fmtRelative(d.draft.updatedAt)}` : ""}</span>
        <button type="button" className="btn btn-primary btn-sm" disabled={s.busy || text === d.draft.body} onClick={() => void s.run(() => api.saveScholarshipDraft(d.id, text), "초안을 저장했습니다")}>
          저장
        </button>
      </div>
    </div>
  );
}

function ApplyView({ d, s }: { d: SchDetail; s: Sch }) {
  const toast = useToast();
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(d.draft?.body ?? "");
      toast("초안을 복사했습니다", { tone: "success" });
    } catch {
      toast("복사하지 못했습니다 — 초안 탭에서 직접 선택해 주세요", { tone: "error" });
    }
  };
  const progress = (p: SchDetail["progress"], ok: string) => void s.run(() => api.patchScholarship(d.id, { progress: p }), ok);
  return (
    <div className="space-y-3 text-[14px]">
      <Banner tone="danger" icon={<ShieldAlert aria-hidden />}>
        제출은 시스템이 하지 않습니다. 확인 후 본인이 직접 제출하세요.
      </Banner>
      <dl className="grid grid-cols-[72px_1fr] items-center gap-3">
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
              <button type="button" className="btn btn-sm" disabled={s.busy} onClick={() => void s.run(() => api.scholarshipToCalendar(d.id), "캘린더에 넣었습니다")}>
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
        <p className="label">제출 서류</p>
        {d.documents.length === 0 ? (
          <p className="rounded-xl border border-dashed border-border-strong px-3 py-2 text-[13px] text-muted">공지에서 서류 목록을 읽지 못했습니다 — 원문·첨부 양식을 확인하세요.</p>
        ) : (
          <ul className="divide-y divide-border rounded-xl border border-border">
            {d.documents.map((doc, i) => {
              const sent = !!d.state.todos[String(i)];
              return (
                <li key={doc} className="flex items-center gap-3 px-3 py-2">
                  <span className="flex-1">{doc}</span>
                  {sent ? (
                    <Chip tone="ok">할 일에 있음</Chip>
                  ) : (
                    <button type="button" className="btn btn-ghost btn-sm" disabled={s.busy} onClick={() => void s.run(() => api.scholarshipToTodo(d.id, i), `'${doc.slice(0, 20)}' 할 일을 마감 하루 전으로 만들었습니다`)}>
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
        {(!d.progress || d.progress === "draft") && (
          <>
            <button type="button" className="btn btn-sm" onClick={() => progress("skipped", "반려했습니다 — 이력 탭에서 되돌릴 수 있습니다")}>
              반려
            </button>
            <button type="button" className="btn btn-primary btn-sm" onClick={() => progress("approved", "승인했습니다 — 마감 D-3·D-1 에 알려 드립니다")}>
              승인 (제출 예정)
            </button>
          </>
        )}
        {d.progress === "approved" && (
          <button type="button" className="btn btn-primary btn-sm" onClick={() => progress("applied", "신청함으로 기록했습니다")}>
            신청했어요
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

function MaterialsModal({ open, onClose, onSaved }: { open: boolean; onClose: () => void; onSaved: () => void }) {
  const toast = useToast();
  const [m, setM] = useState<SchMaterials | null>(null);
  useEffect(() => {
    if (!open) return;
    void api.scholarshipMaterials().then(setM, () => setM(null));
  }, [open]);
  const set = (k: keyof SchMaterials, v: string) => m && setM({ ...m, [k]: v });
  const fields: { k: "careerGoal" | "activities" | "hardship" | "highlights"; label: string; ph: string; opt?: boolean }[] = [
    { k: "careerGoal", label: "진로 목표", ph: "예: 임베디드 AI 분야 대학원 진학" },
    { k: "activities", label: "활동 경험", ph: "예: 교내 AI 경진대회 참가, 학과 튜터링 2학기" },
    { k: "hardship", label: "가정 형편 (선택)", ph: "생활·복지 장학 초안에만 쓰입니다", opt: true },
    { k: "highlights", label: "강조하고 싶은 점 (선택)", ph: "예: 꾸준함, 팀 프로젝트 리더 경험", opt: true },
  ];
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="초안 재료"
      footer={
        <>
          {m?.exists && (
            <button
              type="button"
              className="btn btn-ghost mr-auto"
              onClick={async () => {
                setM(await api.deleteScholarshipMaterials());
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
              await api.putScholarshipMaterials({ careerGoal: m.careerGoal, activities: m.activities, hardship: m.hardship, highlights: m.highlights, basic: m.basic });
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
        <p className="hint">
          한 번 적어 두면 이후 초안에 다시 쓰입니다(이미 만든 초안은 그대로). 적은 것만 근거로 쓰고, 없는 경험은 지어내지 않고 빈칸으로 남깁니다. 프로필과 따로 저장되고 따로 지울 수 있습니다.
        </p>
        {m && (
          <DraftBasicFields
            idPrefix="mat-basic"
            value={m.basic}
            onChange={(basic) => setM({ ...m, basic })}
            fromNote={m.basicFrom === "activity" ? "대외활동 초안 재료에 적어 둔 기본 정보를 불러왔습니다." : m.basicFrom === "profile" ? "학과·학년은 프로필에서 불러왔습니다." : null}
          />
        )}
        {m?.fromProfile && <p className="text-[12px] text-faint">프로필에 적어 둔 초안 재료를 불러왔습니다.</p>}
        {fields.map((f) => (
          <div key={f.k}>
            <label htmlFor={`mat-${f.k}`} className="label">
              {f.label}
            </label>
            <textarea id={`mat-${f.k}`} className="field min-h-[72px] text-[14px]" placeholder={f.ph} value={m?.[f.k] ?? ""} onChange={(e) => set(f.k, e.target.value)} />
          </div>
        ))}
      </div>
    </Modal>
  );
}

function HistoryTab({ onChanged }: { onChanged: () => void }) {
  const [h, setH] = useState<SchHistory | null>(null);
  const toast = useToast();
  const load = () => void api.scholarshipHistory().then(setH, () => setH({ semesters: [] }));
  useEffect(load, []);
  if (!h) return <SkeletonList rows={4} />;
  if (h.semesters.length === 0)
    return (
      <EmptyState icon={<HandCoins />} title="아직 기록이 없습니다">
        초안을 만들거나 승인·신청·선정을 표시하면 학기별로 여기 남습니다. 관심 없음으로 숨긴 장학도 여기서 되돌립니다.
      </EmptyState>
    );
  return (
    <div className="space-y-4">
      {h.semesters.map((g) => (
        <Section key={g.semester} title={`${g.semester.replace("-", "년 ")}학기`} action={<span className="num text-[13px] text-muted">신청 {g.applied} · 선정 {g.selected}{g.amountTotal ? ` · ${(g.amountTotal / 10000).toLocaleString()}만원` : ""}</span>}>
          <ul className="divide-y divide-border">
            {g.items.map((it) => (
              <li key={it.id} className="flex flex-wrap items-center gap-3 py-3 text-[14px]">
                <button type="button" className="min-w-0 flex-1 text-left font-medium hover:text-primary" onClick={() => navigateQuery({ tab: null, item: it.id }, "push")}>
                  {it.title}
                </button>
                {it.amount && <span className="num text-muted">{it.amount}</span>}
                <StatusBadge tone={PROGRESS_TONE[it.progress]}>{it.progressLabel}</StatusBadge>
                {it.progress === "selected" && <AmountInput id={it.id} value={it.amount} onSaved={load} />}
                {it.progress === "skipped" && (
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={async () => {
                      await api.patchScholarship(it.id, { progress: null });
                      toast("되돌렸습니다 — 장학 목록에 다시 보입니다");
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

function AmountInput({ id, value, onSaved }: { id: string; value: string | null; onSaved: () => void }) {
  const [v, setV] = useState(value ?? "");
  return (
    <form
      className="flex gap-1"
      onSubmit={async (e) => {
        e.preventDefault();
        await api.patchScholarship(id, { amount: v });
        onSaved();
      }}
    >
      <input className="field field-sm w-28" placeholder="받은 금액" aria-label="받은 금액" value={v} onChange={(e) => setV(e.target.value)} />
    </form>
  );
}

function SourcesTab({ onSync }: { onSync: () => void }) {
  const toast = useToast();
  const { profile } = useAppData();
  const [d, setD] = useState<SchSources | null>(null);
  const load = () => void api.scholarshipSources().then(setD, () => setD(null));
  useEffect(load, []);
  if (!d) return <SkeletonList rows={6} />;
  const toggle = async (src: SchSource, on: boolean) => {
    const r = await api.patchScholarshipSource(src.key, on === src.relevance.default ? null : on);
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
        {p?.department ? (
          <>
            <b>{p.deptPath ?? p.department}</b> 기준으로 학교 전체 원천과 관련 사업단·내 학과 게시판을 켰습니다.
          </>
        ) : (
          "프로필에 소속을 넣으면 학과에 맞는 사업단·학과 게시판을 자동으로 켭니다."
        )}{" "}
        {d.autosync ? `앱이 켜져 있으면 매일 ${d.slots.join(" · ")} 에 모읍니다(꺼져 있었으면 켜질 때 한 번).` : "이 실행에서는 자동 수집이 꺼져 있습니다 — '지금 수집'으로 모읍니다."}
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
                        {src.target.homepage ? (
                          <>
                            {src.target.listedAs} 홈페이지 {src.target.board ? `› ${src.target.boardLabel ?? "공지"}${src.target.categoryLabel ? ` (말머리 '${src.target.categoryLabel}')` : " (제목에 '장학'이 들어간 글)"}` : "— 다음 수집 때 게시판을 찾습니다"}
                          </>
                        ) : (
                          "프로필 소속의 홈페이지를 학교 목록에서 찾지 못했습니다"
                        )}
                      </p>
                    )}
                    {!src.relay && (
                      <p className={`mt-0.5 text-[12px] ${src.error ? "text-danger-text" : "text-faint"}`}>
                        {src.error ? `실패: ${src.error}` : src.lastOkAt ? `마지막 수집 ${fmtRelative(src.lastOkAt)} · 장학 글 ${src.lastCount ?? 0}건 · 모은 공지 ${src.stored}건` : "아직 수집 전"}
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
