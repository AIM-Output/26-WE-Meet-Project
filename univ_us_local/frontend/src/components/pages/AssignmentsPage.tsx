"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { CircleCheck, ClipboardList, RefreshCw, Sparkles, SquareCheck } from "lucide-react";
import { Page, PageHeader, Group } from "@/components/ui/Layout";
import { Tabs } from "@/components/ui/Tabs";
import { EmptyState, SkeletonList } from "@/components/ui/Feedback";
import { Chip, CourseChip, DdayChip, StatusBadge } from "@/components/ui/Chip";
import { ProgressBar } from "@/components/ui/Progress";
import { EventDetailHost } from "@/components/events/EventDetailHost";
import { EclassSyncBanner, useEclassSyncTone } from "@/components/assignments/EclassSyncBanner";
import { EclassNav } from "@/components/assignments/EclassNav";
import { useAppData } from "@/components/app/AppData";
import { useAssignments } from "@/lib/useAssignments";
import { navigateQuery, useQueryParam, useQueryValue } from "@/lib/useQueryState";
import { ESTIMATE_OPTIONS, GROUP_META, hoursLeftToday, isOpen, isStaleOverdue, sortByPriority, type Assignment, type PriorityGroup } from "@/lib/priority";
import { daysUntil, deadlineDay, fmtDeadline, fmtHours, fmtRelative, parseLocal } from "@/lib/dates";

// /assignments — 과제·동영상 (F6) + 우선순위 그룹 (F7). Frontend-Route 11-3 · 12-1.

const TABS = ["open", "done", "past"] as const;
const SORTS = ["priority", "due", "course"] as const;
type Tab = (typeof TABS)[number];
type Sort = (typeof SORTS)[number];

const GROUP_DOT: Record<PriorityGroup, string> = { overdue: "var(--danger)", now: "var(--accent)", week: "var(--border-strong)", later: "var(--border-strong)" };

function EstimatePicker({ a, onChange }: { a: Assignment; onChange: (h: number | null) => void }) {
  const [custom, setCustom] = useState(false);
  const preset = (ESTIMATE_OPTIONS as readonly number[]).includes(a.estimate);
  const commit = (v: string) => {
    setCustom(false);
    const n = Number(v);
    if (v.trim() && !isNaN(n) && n > 0) onChange(n);
  };
  return (
    <span className="flex items-center gap-1.5">
      <label className="sr-only" htmlFor={`est-${a.id}`}>
        {a.title} 예상 소요시간
      </label>
      {custom ? (
        <input
          id={`est-${a.id}`}
          type="number"
          min={0.25}
          step={0.25}
          autoFocus
          defaultValue={a.estimate}
          className="field field-sm w-[92px]"
          onBlur={(e) => commit(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") commit((e.target as HTMLInputElement).value);
            if (e.key === "Escape") setCustom(false);
          }}
        />
      ) : (
        <select
          id={`est-${a.id}`}
          className="field field-sm w-[92px]"
          value={preset ? String(a.estimate) : "current"}
          onChange={(e) => {
            if (e.target.value === "custom") setCustom(true);
            else if (e.target.value === "default") onChange(null);
            else if (e.target.value !== "current") onChange(Number(e.target.value));
          }}
        >
          {!preset && <option value="current">{fmtHours(a.estimate)}</option>}
          {ESTIMATE_OPTIONS.map((h) => (
            <option key={h} value={h}>
              {fmtHours(h)}
            </option>
          ))}
          <option value="custom">직접 입력…</option>
          {a.estimateSource === "user" && <option value="default">기본값으로</option>}
        </select>
      )}
      {a.estimateSource === "user" && (
        <Chip tone="primary" square>
          직접 입력
        </Chip>
      )}
    </span>
  );
}

function AssignmentRow({
  a,
  now,
  color,
  setUserDone,
  setEstimate,
}: {
  a: Assignment;
  now: Date;
  color?: string;
  setUserDone: (id: string, v: boolean) => void;
  setEstimate: (id: string, h: number | null) => void;
}) {
  return (
    <motion.li layout="position" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="border-b border-border last:border-b-0">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-3 py-3 transition-colors hover:bg-surface-2 md:flex-nowrap md:px-4">
        <span className="w-12 flex-none">
          <DdayChip date={deadlineDay(a.due)} done={!isOpen(a)} now={now} />
        </span>
        <button type="button" className="min-w-0 flex-1 basis-[60%] text-left" onClick={() => navigateQuery({ event: a.id }, "push")}>
          <span className="flex min-w-0 items-center gap-2">
            <span className="truncate text-[15px] font-semibold">{a.title}</span>
            <Chip square className="flex-none">
              {a.kindLabel}
            </Chip>
            {a.p.changed && isOpen(a) && (
              <Chip tone="accent" square className="flex-none" title={a.p.changed.before ? `이전 마감 ${fmtDeadline(parseLocal(a.p.changed.before), now)}` : undefined}>
                변경됨
              </Chip>
            )}
            {a.p.isNew && isOpen(a) && (
              <Chip tone="primary" square className="flex-none">
                새 과제
              </Chip>
            )}
          </span>
          <span className="mt-0.5 flex min-w-0 flex-wrap items-center gap-x-2 text-[13px]">
            <CourseChip name={a.p.courseShort} color={color ?? a.p.courseColor} />
            <span className="text-faint">·</span>
            {isOpen(a) ? <span className="text-muted">{a.reason}</span> : <span className="num text-muted">{fmtDeadline(a.due, now)}</span>}
          </span>
        </button>
        <span className="flex flex-none items-center gap-2 max-md:w-full max-md:justify-end">
          <span className="num hidden text-[13px] text-muted lg:inline">{fmtDeadline(a.due, now)}</span>
          {a.submitted ? (
            <StatusBadge tone="ok">{a.p.status || (a.kindLabel === "동영상" ? "시청 완료" : "제출 완료")}</StatusBadge>
          ) : a.userDone ? (
            <button type="button" onClick={() => setUserDone(a.id, false)} title="누르면 체크를 풉니다" className="rounded-full">
              <Chip tone="ok" dashed icon={<SquareCheck aria-hidden />}>
                내가 체크함
              </Chip>
            </button>
          ) : (
            <EstimatePicker a={a} onChange={(h) => setEstimate(a.id, h)} />
          )}
        </span>
      </div>
    </motion.li>
  );
}

export default function AssignmentsPage() {
  const { status, syncing, loading, startSync, courses, courseColor } = useAppData();
  const { list, setEstimate, setUserDone, now } = useAssignments();
  const syncState = useEclassSyncTone();
  const [tab, setTab] = useQueryParam<Tab>("tab", "open", TABS);
  const [sort, setSort] = useQueryParam<Sort>("sort", "priority", SORTS);
  const course = useQueryValue("course");

  const filtered = useMemo(() => (course ? list.filter((a) => a.ev.extendedProps.kind === "deadline" && a.p.courseShort === course) : list), [list, course]);
  const openList = filtered.filter((a) => isOpen(a) && a.group !== "overdue");
  const doneList = filtered.filter((a) => !isOpen(a)).sort((a, b) => b.due.getTime() - a.due.getTime());
  const pastList = filtered.filter((a) => isOpen(a) && a.group === "overdue").sort((a, b) => b.due.getTime() - a.due.getTime());

  const renderList = (items: Assignment[]) => (
    <ul className="overflow-hidden rounded-xl border border-border bg-surface">
      <AnimatePresence initial={false}>
        {items.map((a) => (
          <AssignmentRow key={a.id} a={a} now={now} color={courseColor(a.p.courseShort)} setUserDone={setUserDone} setEstimate={setEstimate} />
        ))}
      </AnimatePresence>
    </ul>
  );

  const grouped = () => {
    const sorted = sortByPriority(filtered.filter(isOpen));
    const groups: PriorityGroup[] = ["overdue", "now", "week", "later"];
    const left = hoursLeftToday(now);
    return groups.map((g) => {
      let items = sorted.filter((a) => a.group === g);
      const stale = g === "overdue" ? items.filter((a) => isStaleOverdue(a, now)) : [];
      if (g === "overdue") items = items.filter((a) => !isStaleOverdue(a, now));
      if (items.length === 0 && g !== "now") return null;
      const need = items.reduce((s, a) => s + a.estimate, 0);
      if (g === "now" && items.length === 0)
        return (
          <p key={g} className="mb-5 rounded-xl border border-dashed border-border-strong px-4 py-3 text-[14px] text-muted">
            지금 해야 할 과제가 없습니다
          </p>
        );
      return (
        <Group
          key={g}
          title={GROUP_META[g].label}
          count={items.length}
          dot={GROUP_DOT[g]}
          collapsible={g === "later"}
          defaultOpen={g !== "later"}
          extra={g === "now" ? `합계 ${fmtHours(need)}` : stale.length ? `2주 넘게 지난 ${stale.length}건 접음` : undefined}
        >
          {g === "now" && (
            <div className="mb-3 rounded-xl border border-border bg-surface px-4 py-3">
              <div className="mb-2 flex flex-wrap items-center gap-2 text-[13px]">
                <span className={need > left ? "font-semibold text-danger-text" : "text-muted"}>
                  오늘 남은 <b className="num">{fmtHours(left)}</b> 중 <b className="num">{fmtHours(need)}</b> 필요
                  {need > left && " — 오늘 다 하기는 빠듯합니다"}
                </span>
                <Link href="/?place=preview" className="btn btn-ghost btn-sm ml-auto text-study">
                  <Sparkles aria-hidden />
                  공강에 넣기
                </Link>
              </div>
              <ProgressBar value={need} max={Math.max(left, need)} tone={need > left ? "danger" : "accent"} label="오늘 남은 시간 대비 필요 시간" />
            </div>
          )}
          {renderList(items)}
        </Group>
      );
    });
  };

  const flat = (items: Assignment[]) => {
    const s = [...items];
    if (sort === "due") s.sort((a, b) => a.due.getTime() - b.due.getTime());
    else if (sort === "course") s.sort((a, b) => a.p.courseShort.localeCompare(b.p.courseShort, "ko") || a.due.getTime() - b.due.getTime());
    return renderList(s);
  };

  const courseNames = [...new Set(list.map((a) => a.p.courseShort))].sort((a, b) => a.localeCompare(b, "ko"));
  const syncedAt = status?.eclass?.lastOkAt ?? status?.updated_at;

  return (
    <Page>
      <PageHeader
        icon={<ClipboardList />}
        title="E클래스"
        meta={
          <Link href="/settings/sources" className="num inline-flex items-center gap-1.5 rounded-md px-1.5 py-1 hover:bg-surface-3">
            {syncState === "ok" ? <CircleCheck className="size-3.5 text-ok" aria-hidden /> : <RefreshCw className="size-3.5 text-warn" aria-hidden />}
            수집: {fmtRelative(syncedAt)}
          </Link>
        }
        actions={
          <>
            <label className="sr-only" htmlFor="sort">
              정렬
            </label>
            <select id="sort" className="field field-sm w-auto" value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
              <option value="priority">급한 순</option>
              <option value="due">마감 순</option>
              <option value="course">과목 순</option>
            </select>
            <label className="sr-only" htmlFor="course">
              과목
            </label>
            <select
              id="course"
              className="field field-sm w-auto max-w-[180px]"
              value={course ?? ""}
              onChange={(e) => navigateQuery({ course: e.target.value || null }, "replace")}
            >
              <option value="">전체 과목</option>
              {(courseNames.length ? courseNames : courses.map((c) => c.short)).map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </>
        }
      />
      <EclassNav />

      {syncState !== "ok" && (
        <div className="mb-5">
          <EclassSyncBanner />
        </div>
      )}

      <Tabs
        className="mb-5"
        label="과제 상태"
        value={tab}
        onChange={(t) => setTab(t)}
        items={[
          { key: "open", label: "진행 중", count: openList.length },
          { key: "done", label: "완료", count: doneList.length },
          { key: "past", label: "지난 마감", count: pastList.length || undefined },
        ]}
      />

      {loading ? (
        <SkeletonList />
      ) : list.length === 0 ? (
        <EmptyState
          icon={<ClipboardList />}
          title="e클래스에 연결하고 첫 수집을 해 주세요"
          action={
            <button type="button" className="btn btn-primary btn-sm" onClick={startSync} disabled={syncing}>
              시작하기
            </button>
          }
        />
      ) : tab === "open" ? (
        openList.length === 0 && pastList.length === 0 ? (
          <EmptyState icon={<CircleCheck />} title="마감이 남은 과제가 없습니다" />
        ) : sort === "priority" ? (
          <>{grouped()}</>
        ) : (
          flat(filtered.filter(isOpen))
        )
      ) : tab === "done" ? (
        doneList.length === 0 ? <EmptyState compact title="완료한 과제가 여기에 쌓입니다" /> : renderList(doneList)
      ) : pastList.length === 0 ? (
        <EmptyState compact icon={<CircleCheck />} title="놓친 마감이 없습니다" />
      ) : (
        <>
          <p className="mb-3 text-[13px] text-muted">
            마감이 지났지만 제출이 확인되지 않은 과제입니다. e클래스 밖에서 냈다면 &lsquo;내가 체크함&rsquo;으로 옮기세요.
          </p>
          {renderList(pastList)}
          <p className="mt-2 text-right text-[12px] text-faint">가장 오래된 것: {daysUntil(now, pastList[pastList.length - 1].due)}일 전</p>
        </>
      )}

      <EventDetailHost />
    </Page>
  );
}
