"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { BookOpen, CheckCheck, ExternalLink, FileText, Megaphone, MonitorPlay, Paperclip } from "lucide-react";
import { Page, PageHeader, KV } from "@/components/ui/Layout";
import { Tabs } from "@/components/ui/Tabs";
import { EmptyState, ErrorPanel, SkeletonList } from "@/components/ui/Feedback";
import { Chip, CourseChip, type Tone } from "@/components/ui/Chip";
import { Modal } from "@/components/ui/Modal";
import { EclassNav } from "@/components/assignments/EclassNav";
import { EclassSyncBanner, useEclassSyncTone } from "@/components/assignments/EclassSyncBanner";
import { useAppData } from "@/components/app/AppData";
import { useEclassFeed } from "@/lib/useEclassFeed";
import { closeQuery, navigateQuery, useQueryParam, useQueryValue } from "@/lib/useQueryState";
import { FEED_KIND_LABEL, type FeedItem, type FeedKind } from "@/lib/assignments";
import { daysUntil, fmtDateTime, fmtRelative, fmtTime, parseLocal, WEEKDAY_KO } from "@/lib/dates";

// /eclass/posts — E클래스 공지·자료: 수집기가 받아 둔 공지 게시판 글 · 자료실 글 · 강의자료 파일을 '새로 올라왔다'는 소식으로.
// 탭 = ?filter= (replace) · 과목 = ?course= (replace) · 글 상세 = ?post= (push, 모달). 열면 읽음.

const FILTERS = ["all", "unread", "notice", "board", "material"] as const;
type Filter = (typeof FILTERS)[number];

const KIND_TONE: Record<FeedKind, Tone> = { notice: "accent", board: "primary", material: "study" };
const KIND_ICON: Record<FeedKind, React.ReactNode> = {
  notice: <Megaphone aria-hidden />,
  board: <FileText aria-hidden />,
  material: <MonitorPlay aria-hidden />,
};

/** 올라온 시각 — e클래스에 올라온 시각(글은 작성일, 파일은 올린 시각). 모르면 받은 시각 */
const whenOf = (it: FeedItem) => parseLocal(it.postedAt ?? it.fetchedAt ?? it.firstSeen);

function dayLabel(d: Date, now: Date): string {
  const n = daysUntil(d, now);
  if (n === 0) return "오늘";
  if (n === -1) return "어제";
  return `${d.getMonth() + 1}월 ${d.getDate()}일 (${WEEKDAY_KO[d.getDay()]})`;
}

function fmtSize(b: number | null): string {
  if (!b) return "";
  return b >= 1024 * 1024 ? `${(b / 1024 / 1024).toFixed(1)}MB` : `${Math.max(1, Math.round(b / 1024))}KB`;
}

function FeedRow({ it, color, onOpen }: { it: FeedItem; color?: string; onOpen: () => void }) {
  const when = whenOf(it);
  return (
    <motion.li layout="position" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="border-b border-border last:border-b-0">
      <button type="button" onClick={onOpen} className="flex w-full items-start gap-3 px-3 py-3 text-left transition-colors hover:bg-surface-2 md:px-4">
        <span className="mt-1.5 flex size-2 flex-none items-center justify-center" aria-hidden>
          {!it.read && <span className="size-2 rounded-full bg-accent" />}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex min-w-0 items-center gap-2">
            <Chip tone={KIND_TONE[it.kind]} square icon={KIND_ICON[it.kind]} className="flex-none">
              {FEED_KIND_LABEL[it.kind]}
            </Chip>
            <span className={`truncate text-[15px] ${it.read ? "font-medium text-muted" : "font-semibold"}`}>{it.title}</span>
            {it.isNew && (
              <Chip tone="primary" square className="flex-none">
                새 글
              </Chip>
            )}
          </span>
          <span className="mt-0.5 flex min-w-0 flex-wrap items-center gap-x-2 text-[13px]">
            <CourseChip name={it.courseShort} color={color} />
            <span className="text-faint">·</span>
            <span className="truncate text-muted">{it.kind === "material" ? `${it.board}${it.size ? ` · ${fmtSize(it.size)}` : ""}` : it.excerpt || it.board}</span>
            {it.attachments.length > 0 && (
              <span className="inline-flex items-center gap-1 text-faint">
                <Paperclip className="size-3.5" aria-hidden />
                {it.attachments.length}
              </span>
            )}
          </span>
        </span>
        <span className="num flex-none pt-0.5 text-[12px] text-faint" title={fmtDateTime(when)}>
          {fmtTime(when) === "00:00" ? "" : fmtTime(when)}
        </span>
      </button>
    </motion.li>
  );
}

function FeedDetail({ id, items, onRead, load }: { id: string; items: FeedItem[]; onRead: (ids: string[], read?: boolean) => void; load: (id: string) => Promise<FeedItem | null> }) {
  const { courseColor } = useAppData();
  const base = items.find((x) => x.id === id) ?? null;
  const [full, setFull] = useState<FeedItem | null>(null);
  useEffect(() => {
    let alive = true;
    void load(id).then((d) => alive && setFull(d));
    return () => {
      alive = false;
    };
  }, [id, load]);
  const it = full && full.id === id ? { ...full, read: base?.read ?? full.read } : base;
  if (!it) return <p className="py-8 text-center text-[14px] text-muted">불러오는 중…</p>;
  const when = whenOf(it);
  return (
    <div className="space-y-4 pt-1">
      <div className="flex flex-wrap items-center gap-2">
        <CourseChip name={it.courseShort} color={courseColor(it.courseShort)} />
        <Chip tone={KIND_TONE[it.kind]} square icon={KIND_ICON[it.kind]}>
          {FEED_KIND_LABEL[it.kind]}
        </Chip>
      </div>
      <KV
        rows={[
          [it.kind === "material" ? "자료 활동" : "게시판", it.board],
          [it.postedAt ? (it.kind === "material" ? "올린 시각" : "작성일") : "받은 시각", fmtDateTime(when)],
          ...(it.kind === "material" && it.size ? [["크기", fmtSize(it.size)] as [string, string]] : []),
          ...(it.attachments.length
            ? [
                [
                  "첨부",
                  <span key="a" className="flex flex-col gap-0.5">
                    {it.attachments.map((f) => (
                      <span key={f} className="inline-flex min-w-0 items-center gap-1.5">
                        <Paperclip className="size-3.5 flex-none text-faint" aria-hidden />
                        <span className="truncate">{f}</span>
                      </span>
                    ))}
                  </span>,
                ] as [string, React.ReactNode],
              ]
            : []),
        ]}
      />
      {it.kind !== "material" &&
        (it.body === undefined ? (
          <p className="text-[13px] text-muted">본문 불러오는 중…</p>
        ) : (
          <div className="thin-scroll max-h-[50vh] overflow-auto rounded-xl bg-surface-2 p-3 text-[14px] leading-relaxed whitespace-pre-wrap">{it.body || "(본문 없음)"}</div>
        ))}
      <p className="text-[12px] text-faint">
        {it.kind === "material" ? "파일" : it.attachments.length ? "글과 첨부" : "글"}은 이 PC 의 F6_Eclass_agent/data 에 받아 두었습니다 (공유 금지). 강의자료 요약은 강의자료 화면에서.
      </p>
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-4">
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => onRead([it.id], !it.read)}>
          {it.read ? "안 읽음으로" : "읽음으로"}
        </button>
        {it.url && (
          <a className="btn btn-primary" href={it.url} target="_blank" rel="noopener noreferrer">
            e클래스에서 열기
            <ExternalLink aria-hidden />
          </a>
        )}
      </div>
    </div>
  );
}

export default function EclassFeedPage() {
  const { status, courseColor } = useAppData();
  const { data, error, loading, reload, setRead, detail } = useEclassFeed();
  const syncTone = useEclassSyncTone();
  const [filter, setFilter] = useQueryParam<Filter>("filter", "all", FILTERS);
  const course = useQueryValue("course");
  const postId = useQueryValue("post");
  const [shown, setShown] = useState(postId);
  if (postId && postId !== shown) setShown(postId);
  const now = new Date();

  const items = useMemo(() => (data?.items ?? []).filter((it) => !course || it.courseShort === course), [data, course]);
  const visible = useMemo(
    () => items.filter((it) => (filter === "all" ? true : filter === "unread" ? !it.read : it.kind === filter)),
    [items, filter],
  );
  const count = (f: Filter) => items.filter((it) => (f === "all" ? true : f === "unread" ? !it.read : it.kind === f)).length;
  const courses = [...new Set((data?.items ?? []).map((i) => i.courseShort))].sort((a, b) => a.localeCompare(b, "ko"));

  // 글을 열면 읽음 (F6 새 글 — 알림의 링크로 들어와도 같다)
  useEffect(() => {
    if (!postId || !data) return;
    const it = data.items.find((x) => x.id === postId);
    if (it && !it.read) void setRead([postId]);
  }, [postId, data, setRead]);

  const groups = useMemo(() => {
    const out: { label: string; items: FeedItem[] }[] = [];
    for (const it of visible) {
      const label = dayLabel(whenOf(it), now);
      const g = out.at(-1);
      if (g && g.label === label) g.items.push(it);
      else out.push({ label, items: [it] });
    }
    return out;
    // now 는 렌더마다 바뀌지만 날짜 묶음만 쓴다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  const unread = data?.counts.unread ?? 0;
  const shownItem = data?.items.find((x) => x.id === shown);

  return (
    <Page>
      <PageHeader
        icon={<Megaphone />}
        title="E클래스"
        meta={<span className="num text-[13px] text-muted">수집: {fmtRelative(status?.eclass?.lastOkAt ?? status?.updated_at)}</span>}
        actions={
          <>
            <label className="sr-only" htmlFor="feed-course">
              과목
            </label>
            <select
              id="feed-course"
              className="field field-sm w-auto max-w-[180px]"
              value={course ?? ""}
              onChange={(e) => navigateQuery({ course: e.target.value || null }, "replace")}
            >
              <option value="">전체 과목</option>
              {courses.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
            <button type="button" className="btn btn-sm" disabled={!unread} onClick={() => void setRead("all")}>
              <CheckCheck aria-hidden />
              모두 읽음
            </button>
          </>
        }
      />
      <EclassNav />

      {/* 종류 탭 줄 — 위(E클래스 탭) 구분선과 아래(종류 탭) 구분선 사이 세로 가운데에 '강의자료' 바로가기(F4).
          -mt-6 으로 E클래스 탭 아래 여백을 이 줄 안으로 끌어와, 두 구분선 사이 전체 높이에서 가운데를 잡는다. */}
      <div className="-mt-6 mb-5 flex min-h-16 items-center gap-2 border-b border-border">
        <Tabs
          className="min-w-0 flex-1 self-end border-b-0!"
          label="글·자료 종류"
          value={filter}
          onChange={setFilter}
          items={[
            { key: "all", label: "전체", count: count("all") },
            { key: "unread", label: "안 읽음", count: count("unread") || undefined },
            { key: "notice", label: "공지", count: count("notice") },
            { key: "board", label: "자료실 글", count: count("board") },
            { key: "material", label: "강의자료", count: count("material") },
          ]}
        />
        <Link href="/courses" className="btn btn-sm flex-none" title="강의자료 화면(F4)으로 — 받아 둔 자료 열람·요약">
          <BookOpen aria-hidden />
          강의자료
        </Link>
      </div>

      {syncTone !== "ok" && (
        <div className="mb-5">
          <EclassSyncBanner />
        </div>
      )}

      {error ? (
        <ErrorPanel message={`불러오지 못했습니다: ${error}`} onRetry={() => void reload()} />
      ) : loading ? (
        <SkeletonList />
      ) : (data?.counts.all ?? 0) === 0 ? (
        <EmptyState icon={<Megaphone />} title="아직 받아 둔 공지·자료가 없습니다">
          e클래스 동기화를 하면 과목의 공지사항·자료실 글과 강의자료가 여기에 모입니다.
        </EmptyState>
      ) : visible.length === 0 ? (
        <EmptyState compact title={filter === "unread" ? "새로 올라온 글·자료를 다 봤습니다" : "해당하는 글·자료가 없습니다"} />
      ) : (
        <div className="space-y-5">
          {groups.map((g) => (
            <section key={g.label}>
              <h2 className="mb-2 text-[13px] font-bold tracking-wide text-muted">{g.label}</h2>
              <ul className="overflow-hidden rounded-xl border border-border bg-surface">
                <AnimatePresence initial={false}>
                  {g.items.map((it) => (
                    <FeedRow key={it.id} it={it} color={courseColor(it.courseShort)} onOpen={() => navigateQuery({ post: it.id }, "push")} />
                  ))}
                </AnimatePresence>
              </ul>
            </section>
          ))}
          <p className="text-[12px] text-faint">
            교수·조교가 올리는 공지사항·자료실 게시판과 강의자료만 모읍니다(Q&amp;A·팀빌딩처럼 학생 글이 올라오는 게시판은 모으지 않습니다). 새 글은 알림 센터에도 옵니다 — 알림·브리핑 설정에서 끌 수 있습니다.
          </p>
        </div>
      )}

      <Modal open={!!postId} onClose={() => closeQuery(["post"])} title={shownItem?.title ?? "글"} size="lg">
        {shown && <FeedDetail id={shown} items={data?.items ?? []} onRead={(ids, read) => void setRead(ids, read)} load={detail} />}
      </Modal>
    </Page>
  );
}
