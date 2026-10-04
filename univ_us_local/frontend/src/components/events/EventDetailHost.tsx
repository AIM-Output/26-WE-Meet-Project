"use client";

import { useState } from "react";
import Link from "next/link";
import { CalendarCheck, CalendarDays, CalendarMinus, CalendarPlus, Check, ExternalLink, Eye, EyeOff, Paperclip, Pencil, SquareCheck, Target, Trash2 } from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { Chip, CourseChip, DdayChip, StatusBadge } from "@/components/ui/Chip";
import { Banner } from "@/components/ui/Feedback";
import { KV } from "@/components/ui/Layout";
import { useToast } from "@/components/ui/Toast";
import { useAppData } from "@/components/app/AppData";
import { closeQuery, navigateQuery, useQueryValue } from "@/lib/useQueryState";
import { useAcademic } from "@/lib/useAcademic";
import { useAssignments } from "@/lib/useAssignments";
import { api } from "@/lib/api";
import { academicPeriod, audienceText, lastDay, typeMeta, type AcademicEvent } from "@/lib/academic";
import type { CalEvent, ExamProps, UserEventInput } from "@/lib/types";
import { autoCancelText, num, type SessionPatch } from "@/lib/attendance";
import { AttendanceChips, LevelBadge } from "@/components/attendance/AttendanceChips";
import { addDays, daysUntil, deadlineDay, fmtDateTime, fmtDeadlineLong, fmtHours, fmtRelative, fmtTime, parseLocal } from "@/lib/dates";
import { ESTIMATE_OPTIONS } from "@/lib/priority";
import { EventForm, DEFAULT_CATEGORIES, type EventDraft } from "./EventForm";

// 일정 상세 — `?event=` 가 붙으면 열리고, 뒤로가기·ESC 로 닫힌다. 소스 5종이 같은 자리를 쓴다(Frontend-Route 4-4).
// `/`·`/academic`·`/assignments` 가 같은 컴포넌트를 쓴다.

export function EventDetailHost() {
  const id = useQueryValue("event");
  const [last, setLast] = useState(id);
  if (id && id !== last) setLast(id);
  const shown = id ?? last;
  const close = () => closeQuery(["event"]);

  const { events, loading } = useAppData();
  const { list: academic, loading: academicLoading } = useAcademic();

  let body: React.ReactNode = null;
  let title: React.ReactNode = "일정";
  if (shown?.startsWith("ac:")) {
    const ev = academic.find((e) => e.id === shown);
    if (ev) {
      return <AcademicHost key={ev.id} ev={ev} open={!!id} onClose={close} />;
    } else if (academicLoading) {
      body = <p className="py-8 text-center text-[14px] text-muted">불러오는 중…</p>;
    }
  } else if (shown?.startsWith("ex:")) {
    const ev = events.find((e) => e.id === shown);
    if (ev?.extendedProps.kind === "exam") {
      title = ev.title;
      body = <ExamDetailBody ev={ev} />;
    }
  } else if (shown?.startsWith("cl:")) {
    const ev = events.find((e) => e.id === shown);
    if (ev?.extendedProps.kind === "class") {
      title = `${ev.title} 수업`;
      body = <ClassDetail ev={ev} onClose={close} />;
    }
  } else if (shown) {
    const ev = events.find((e) => e.id === shown);
    if (ev?.extendedProps.kind === "deadline") {
      title = ev.title;
      body = <DeadlineDetail ev={ev} />;
    } else if (ev) {
      return <UserDetail ev={ev} open={!!id} onClose={close} />;
    }
  }
  if (!body) body = <p className="py-8 text-center text-[14px] text-muted">{loading ? "불러오는 중…" : "일정을 찾을 수 없습니다. 삭제되었거나 수집 목록에서 빠졌을 수 있습니다."}</p>;

  return (
    <Modal open={!!id} onClose={close} title={title}>
      {body}
    </Modal>
  );
}

/* ---------------------------------------------------------------- F6 과제 */

function DeadlineDetail({ ev }: { ev: CalEvent }) {
  const toast = useToast();
  const { courseColor } = useAppData();
  const { list, setUserDone, setEstimate } = useAssignments();
  const [showAll, setShowAll] = useState(false);
  if (ev.extendedProps.kind !== "deadline") return null;
  const p = ev.extendedProps;
  const a = list.find((x) => x.id === ev.id);
  const due = parseLocal(p.due);
  const desc = (p.description || "").trim();
  const done = p.submitted || !!a?.userDone;
  const video = p.type === "동영상"; // 동영상은 '제출' 대신 '시청' — 진도율이 출석인정 요구시간을 넘으면 시청 완료
  const doneWord = video ? "시청 완료" : "제출 완료";
  const notWord = video ? "미시청" : "미제출";

  return (
    <div className="space-y-4 pt-1">
      <div className="flex flex-wrap items-center gap-2">
        <CourseChip name={`${p.courseShort}${p.courseCode ? ` (${p.courseCode})` : ""}`} color={courseColor(p.courseShort) ?? p.courseColor} />
        <Chip square>{a?.kindLabel ?? p.type ?? "과제"}</Chip>
        {p.isNew && !done && (
          <Chip tone="primary" square>
            새 과제
          </Chip>
        )}
      </div>
      <KV
        rows={[
          [
            "마감",
            <span key="d" className="flex flex-wrap items-center gap-2 font-semibold">
              {fmtDeadlineLong(due)}
              {p.changed?.before && (
                <>
                  <span className="text-[13px] font-normal text-faint line-through" title={`${fmtRelative(p.changed.at)} 바뀜`}>
                    {fmtDeadlineLong(parseLocal(p.changed.before))}
                  </span>
                  <Chip tone="accent" square>
                    변경됨
                  </Chip>
                </>
              )}
              <DdayChip date={deadlineDay(due)} done={done} />
            </span>,
          ],
          [
            video ? "시청" : "제출",
            p.submitted ? (
              <span key="s" className="flex flex-wrap items-center gap-2">
                <StatusBadge tone="ok">{p.status || doneWord}</StatusBadge>
                {p.promoted && <span className="text-[12px] text-muted">내가 체크한 항목이 e클래스에서 {video ? "시청 완료" : "제출"}로 확인됐습니다</span>}
              </span>
            ) : a?.userDone ? (
              <Chip tone="ok" dashed icon={<SquareCheck aria-hidden />}>
                내가 체크함
              </Chip>
            ) : daysUntil(deadlineDay(due)) < 0 ? (
              <StatusBadge tone="danger">{p.status || notWord} · 마감 지남</StatusBadge>
            ) : (
              <StatusBadge tone="warn">{p.status || notWord}</StatusBadge>
            ),
          ],
          ...(p.graded ? [["채점", p.graded] as [string, string]] : []),
          ...(p.attachmentCount > 0
            ? [
                [
                  "첨부",
                  <span key="a" className="flex flex-col gap-0.5">
                    {(p.attachments ?? []).map((f) => (
                      <span key={f.path} className="inline-flex min-w-0 items-center gap-1.5" title={`F6_Eclass_agent/${f.path.replace(/\\/g, "/")}`}>
                        <Paperclip className="size-3.5 flex-none text-faint" aria-hidden />
                        <span className="truncate">{f.name}</span>
                      </span>
                    ))}
                    <span className="text-[12px] text-faint">이 PC 의 F6_Eclass_agent/data 에 받아 두었습니다 (공유 금지)</span>
                  </span>,
                ] as [string, React.ReactNode],
              ]
            : []),
          ...(a && !p.submitted
            ? [
                [
                  "소요",
                  <span key="e" className="flex flex-wrap items-center gap-2">
                    <select
                      className="field field-sm w-auto"
                      aria-label="예상 소요시간"
                      value={ESTIMATE_OPTIONS.includes(a.estimate as (typeof ESTIMATE_OPTIONS)[number]) ? a.estimate : ""}
                      onChange={(e) => setEstimate(ev.id, Number(e.target.value))}
                    >
                      {!ESTIMATE_OPTIONS.includes(a.estimate as (typeof ESTIMATE_OPTIONS)[number]) && <option value="">{fmtHours(a.estimate)}</option>}
                      {ESTIMATE_OPTIONS.map((h) => (
                        <option key={h} value={h}>
                          {fmtHours(h)}
                        </option>
                      ))}
                    </select>
                    <span className="text-[13px] text-muted">{a.reason}</span>
                  </span>,
                ] as [string, React.ReactNode],
              ]
            : []),
        ]}
      />
      {desc && (
        <div className="rounded-xl bg-surface-2 p-3 text-[14px] leading-relaxed whitespace-pre-wrap text-muted">
          {desc.length > 200 && !showAll ? `${desc.slice(0, 200)}…` : desc}
          {desc.length > 200 && (
            <button type="button" className="ml-1 font-semibold text-primary" onClick={() => setShowAll((v) => !v)}>
              {showAll ? "접기" : "더 보기"}
            </button>
          )}
        </div>
      )}
      {!p.submitted && (
        <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-dashed border-border-strong p-3">
          <input
            type="checkbox"
            className="mt-0.5 size-4 accent-[var(--ok)]"
            checked={!!a?.userDone}
            onChange={async (e) => {
              const v = e.target.checked;
              const ok = await setUserDone(ev.id, v);
              if (ok && v) toast("완료로 표시했습니다", { tone: "success", action: { label: "되돌리기", onClick: () => void setUserDone(ev.id, false) } });
            }}
          />
          <span>
            <span className="block text-[14px] font-semibold">내가 체크함</span>
            <span className="text-[13px] text-muted">{video ? "다른 기기에서 봤는데 아직 반영되지 않은 경우. 다음 수집에서 진도율이 확인되면 ‘시청 완료’로 바뀝니다." : "e클래스 밖에서 제출한 경우. 다음 수집에서 제출이 확인되면 ‘제출 완료’로 바뀝니다."}</span>
          </span>
        </label>
      )}
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-4">
        <span className="text-[13px] text-faint">e클래스에서 가져온 일정은 여기서 고칠 수 없습니다.</span>
        {p.url && (
          <a className="btn btn-primary" href={p.url} target="_blank" rel="noopener noreferrer">
            e클래스에서 열기
            <ExternalLink aria-hidden />
          </a>
        )}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- F1 학사 */

const LONG_PERIOD_DAYS = 14; // 이보다 긴 신청 기간은 내 일정에 '마감일'로 넣는다 (전체 뷰를 막대로 덮지 않게)

/** 학사 일정 → '내 일정에 넣기' 폼의 초기값. 사용자가 폼에서 고쳐 저장한다. */
function academicDraft(ev: AcademicEvent): EventDraft {
  const s = parseLocal(ev.start!);
  const last = lastDay(ev)!;
  const src = ev.sources[0];
  const memo = [`학사일정 · ${academicPeriod(ev)}`, src ? `출처: ${src.name} ${src.url}` : ""].filter(Boolean).join("\n");
  const base = { title: ev.title, category: "study" as const, memo, isTodo: false, done: false };
  if (ev.allDay) {
    const days = Math.round((last.getTime() - s.getTime()) / 86_400_000);
    if (days > LONG_PERIOD_DAYS) return { ...base, title: `${ev.title} 마감`, start: last, end: null, allDay: true };
    return { ...base, start: s, end: days > 0 ? last : null, allDay: true };
  }
  const end = ev.end ? parseLocal(ev.end) : null;
  return { ...base, start: s, end: end && end > s ? end : new Date(s.getTime() + 3_600_000), allDay: false };
}

/** 학사 일정 상세 ↔ '내 일정에 넣기' 폼. `?add=1`(목록의 빠른 버튼)이면 폼부터 열고, 닫으면 상세 없이 닫힌다. */
function AcademicHost({ ev, open, onClose }: { ev: AcademicEvent; open: boolean; onClose: () => void }) {
  const toast = useToast();
  const { events, refresh, status } = useAppData();
  const direct = useQueryValue("add") === "1";
  const [adding, setAdding] = useState(direct);
  const mine = events.find((e) => e.extendedProps.kind === "user" && e.extendedProps.origin === ev.id) ?? null;

  if (adding && ev.start && !mine) {
    const done = () => (direct ? closeQuery(["event", "add"]) : setAdding(false));
    return (
      <EventForm
        open={open}
        mode="create"
        heading="내 일정에 넣기"
        draft={academicDraft(ev)}
        categories={status?.categories ?? DEFAULT_CATEGORIES}
        onClose={done}
        onSave={async (input: UserEventInput) => {
          await api.createEvent({ ...input, origin: ev.id });
          await refresh();
          done();
          toast("내 일정에 넣었습니다 — 캘린더 전체 뷰에 보입니다", { tone: "success" });
        }}
      />
    );
  }
  return (
    <Modal open={open} onClose={onClose} title={ev.title}>
      <AcademicDetail ev={ev} onClose={onClose} mine={mine} onAdd={() => setAdding(true)} />
    </Modal>
  );
}

/** 학사 일정 상세 (F1-S07·S08) — 근거·출처·대상·신뢰도·알림 시점·메모·숨기기·내 일정에 넣기 */
function AcademicDetail({ ev, onClose, mine, onAdd }: { ev: AcademicEvent; onClose: () => void; mine: CalEvent | null; onAdd: () => void }) {
  const toast = useToast();
  const { update } = useAcademic();
  const meta = typeMeta(ev.type);
  const before = ev.changed?.before;

  const hide = () => {
    void update(ev.id, { status: "hidden" });
    onClose();
    toast("숨겼습니다", { action: { label: "되돌리기", onClick: () => void update(ev.id, { status: "restore" }) } });
  };

  return (
    <div className="space-y-4 pt-1">
      <div className="flex flex-wrap items-center gap-2">
        <span className="chip chip-square text-white" style={{ background: meta.color }}>
          {meta.label}
        </span>
        {ev.status === "review" && <Chip tone="warn">확인 필요</Chip>}
        {ev.status === "approved" && <Chip tone="primary" square>내가 등록</Chip>}
        {ev.status === "hidden" && <Chip tone="neutral">숨김</Chip>}
        {ev.changed && <Chip tone="warn">변경됨</Chip>}
        {ev.removed && <Chip tone="danger" square>원문 삭제됨</Chip>}
        {ev.pinned && <Chip tone="primary" square>학사 캘린더에 담음</Chip>}
        {mine && (
          <Chip tone="ok" square icon={<Check aria-hidden />}>
            내 일정에 있음
          </Chip>
        )}
      </div>
      <p className="num text-[15px] font-semibold">
        {academicPeriod(ev)}
        {before?.start && (
          <span className="ml-2 text-[13px] font-normal text-faint line-through" title="바뀌기 전 날짜">
            {academicPeriod(before)}
          </span>
        )}
      </p>
      {ev.status === "review" && (
        <Banner tone="warn" action={<Link href="/academic?tab=review" className="btn btn-sm" onClick={onClose}>확인하러 가기</Link>}>
          {ev.needsOcr ? "본문이 이미지라 날짜를 읽지 못했습니다." : "신뢰도가 자동 등록 기준(0.80)보다 낮아 캘린더에 넣지 않았습니다."}
        </Banner>
      )}
      <KV
        rows={[
          [
            "대상",
            <span key="t" className="flex flex-wrap items-center gap-2">
              {audienceText(ev.audience)}
              {ev.appliesToMe === true && <StatusBadge tone="ok">내 해당</StatusBadge>}
              {ev.appliesToMe === false && <StatusBadge tone="neutral">해당 없음</StatusBadge>}
              {ev.appliesToMe === null && <StatusBadge tone="warn" unknown>판단 불가</StatusBadge>}
            </span>,
          ],
          [
            "신뢰도",
            <span key="c" className="num">
              {ev.confidence.toFixed(2)}
              {ev.weak && <span className="ml-1.5 text-danger-text">· 근거 약함</span>}
              {ev.sources.length > 1 && <span className="ml-1.5 text-faint">· 원천 {ev.sources.length}곳이 일치</span>}
            </span>,
          ],
          ...(ev.evidence.length
            ? [
                [
                  "근거",
                  <ul key="q" className="space-y-1">
                    {ev.evidence.slice(0, 3).map((q) => (
                      <li key={q.quote}>
                        <q className="text-muted">{q.quote}</q> <span className="text-[12px] text-faint">— {q.source}</span>
                      </li>
                    ))}
                  </ul>,
                ] as [string, React.ReactNode],
              ]
            : []),
          [
            "출처",
            <ul key="s" className="space-y-0.5">
              {ev.sources.map((s) => (
                <li key={s.key + s.url} className="flex flex-wrap items-center gap-2">
                  <a href={s.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 font-semibold text-primary hover:underline">
                    {s.name}
                    {s.postedAt && <span className="num font-normal text-faint">({s.postedAt.slice(5).replace("-", "/")})</span>}
                    <ExternalLink className="size-3.5" aria-hidden />
                  </a>
                  {s.removed && <span className="text-[12px] font-medium text-danger-text">원문 삭제됨</span>}
                </li>
              ))}
            </ul>,
          ],
        ]}
      />
      {ev.reminders.length > 0 && (
        <div className="border-t border-border pt-4">
          <span className="label">알림</span>
          <div className="flex flex-wrap gap-2">
            {ev.reminders.map((r) => (
              <button
                key={r.code}
                type="button"
                aria-pressed={r.enabled}
                className={`btn btn-sm ${r.enabled ? "border-primary bg-primary-soft text-primary hover:bg-primary-soft" : ""}`}
                onClick={() => void update(ev.id, { reminders: { [r.code]: !r.enabled } })}
              >
                {r.enabled && <Check aria-hidden />}
                {r.label}
              </button>
            ))}
          </div>
          <p className="hint">
            {ev.onCalendar ? "기준 시각은 " : "학사 캘린더에 없는 일정이라 알림이 울리지 않습니다 · 기준 시각은 "}
            <Link href="/settings/notifications" className="underline">
              알림 설정
            </Link>
          </p>
        </div>
      )}
      <div>
        <label className="label" htmlFor="ac-memo">
          메모
        </label>
        <textarea
          id="ac-memo"
          key={ev.id}
          className="field"
          defaultValue={ev.memo}
          onBlur={(e) => {
            if (e.target.value !== ev.memo) void update(ev.id, { memo: e.target.value });
          }}
        />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-4">
        <div className="flex flex-wrap gap-2">
          {ev.status === "hidden" ? (
            <button type="button" className="btn btn-ghost" onClick={() => void update(ev.id, { status: "restore" })}>
              <Eye aria-hidden />
              다시 보이기
            </button>
          ) : (
            <button type="button" className="btn btn-ghost" onClick={hide}>
              <EyeOff aria-hidden />
              숨기기
            </button>
          )}
          {/* 예전 '내 캘린더에 담기'(pinned)로 학사 캘린더에 넣어 둔 것만 뺄 수 있게 남긴다 */}
          {ev.pinned && (
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => {
                void update(ev.id, { pinned: false });
                toast("학사 캘린더에서 뺐습니다");
              }}
            >
              <CalendarMinus aria-hidden />
              학사 캘린더에서 빼기
            </button>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {ev.actionUrl && (
            <a href={ev.actionUrl} target="_blank" rel="noopener noreferrer" className="btn">
              {ev.actionLabel ?? "바로가기"}
              <ExternalLink aria-hidden />
            </a>
          )}
          {ev.start && ev.onCalendar && (
            <Link href={`/?date=${ev.start.slice(0, 7)}&filter=academic`} className="btn" onClick={onClose}>
              <CalendarDays aria-hidden />
              학사 캘린더
            </Link>
          )}
          {mine ? (
            <button type="button" className="btn" onClick={() => navigateQuery({ event: mine.id }, "replace")}>
              <CalendarCheck aria-hidden />
              내 일정 보기
            </button>
          ) : (
            ev.start &&
            ev.status !== "hidden" && (
              <button type="button" className="btn btn-primary" onClick={onAdd}>
                <CalendarPlus aria-hidden />
                내 일정에 넣기
              </button>
            )
          )}
        </div>
      </div>
      {!mine && ev.start && ev.status !== "hidden" && (
        <p className="hint -mt-2">학사 일정은 캘린더의 &lsquo;학사&rsquo; 보기에만 나옵니다. 내 일정에 넣으면 전체 보기에도 보이고, 날짜·제목을 고칠 수 있습니다.</p>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- F5 시험 (학습 블록은 공부 캘린더에만 — /study-calendar) */

/** 시험 상세 (F5-R05) — 캘린더에서는 보기만 한다. 근거 원문과 계획으로 이어 준다. */
function ExamDetailBody({ ev }: { ev: CalEvent }) {
  const { courseColor } = useAppData();
  const p = ev.extendedProps as ExamProps;
  return (
    <div className="space-y-4 pt-1">
      <div className="flex flex-wrap items-center gap-2">
        <CourseChip name={p.course} color={courseColor(p.course) ?? p.courseColor} />
        <Chip tone="danger" square>
          {p.typeLabel}
        </Chip>
        {p.needsReview && <StatusBadge tone="warn">확인 필요</StatusBadge>}
        {p.isAuto && <Chip dashed>임의 일정</Chip>}
        <DdayChip date={parseLocal(ev.start)} />
      </div>
      <KV
        rows={[
          [
            "일시",
            <span key="d" className="num font-semibold">
              {p.timeUnknown ? `${fmtDateTime(parseLocal(ev.start), false)} · 시각 미정` : fmtDateTime(parseLocal(ev.start))}
            </span>,
          ],
          [
            "장소",
            p.place || (
              <span key="x" className="text-faint">
                미정
              </span>
            ),
          ],
          [
            "원천",
            p.source === "notice" ? `e클래스 공지 (신뢰도 ${Math.round(p.confidence * 100)}%)` : p.isAuto ? "임의 일정" : "직접 추가",
          ],
        ]}
      />
      {p.isAuto && p.note && (
        <p className="rounded-lg border border-dashed border-border-strong px-3 py-2 text-[13px] text-muted">
          {p.note}. 공지에서 일정이 나오면 바뀌고, 시험 화면에서 직접 고칠 수도 있습니다.
        </p>
      )}
      {p.evidence.length > 0 && (
        <div>
          <h3 className="mb-1.5 text-[13px] font-bold text-muted">공지 원문 근거</h3>
          <ul className="space-y-1.5">
            {p.evidence.map((e, i) => (
              <li key={i} className="rounded-lg bg-surface-2 px-3 py-2 text-[13px] text-muted">
                {e.quote}
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="flex flex-wrap items-center justify-end gap-2 border-t border-border pt-3">
        {p.noticeUrl && (
          <a href={p.noticeUrl} target="_blank" rel="noopener noreferrer" className="btn mr-auto">
            <ExternalLink aria-hidden />
            공지 원문 보기
          </a>
        )}
        <Link href={`/exams?exam=${encodeURIComponent(p.examId)}`} className="btn btn-primary">
          <Target aria-hidden />
          {p.needsReview ? "확인하기" : "공부 계획"}
        </Link>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- F3 수업 회차 */

/** 수업 일정 상세 (F3-R25·S07) — 캘린더의 수업을 눌러 바로 출결·휴강. 회차는 /attendance 와 같은 데이터다(8-6). */
function ClassDetail({ ev, onClose }: { ev: CalEvent; onClose: () => void }) {
  const toast = useToast();
  const { refresh } = useAppData();
  const [busy, setBusy] = useState(false);
  if (ev.extendedProps.kind !== "class") return null;
  const p = ev.extendedProps;
  const s = parseLocal(ev.start);
  const e = ev.end ? parseLocal(ev.end) : null;

  const patch = async (body: SessionPatch) => {
    setBusy(true);
    try {
      const r = await api.patchSession(ev.id, body);
      await refresh();
      for (const a of r.alerts) toast(`${a.title} — ${a.body}`, { tone: a.level === "caution" ? "default" : "error", duration: 8000 });
      if (body.state === "canceled") toast("휴강으로 표시했습니다 — 총 횟수에서 빠집니다", { action: { label: "되돌리기", onClick: () => void patch({ state: "scheduled" }) } });
    } catch (err) {
      toast(`저장하지 못했습니다: ${err instanceof Error ? err.message : String(err)}`, { tone: "error" });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4 pt-1">
      <div className="flex flex-wrap items-center gap-2">
        <CourseChip name={`${p.courseName}`} color={p.color} />
        {p.sessionKind === "makeup" && <Chip tone="info" square>{p.origin === "school" ? `학교 보강일${p.makeupName ? ` · ${p.makeupName}` : ""}` : "보강"}</Chip>}
        {p.state === "canceled" && <Chip tone="neutral">휴강{p.cancelSource && p.cancelSource !== "user" ? " · 자동" : ""}</Chip>}
      </div>
      {p.autoCancel && (
        <p className="text-[13px] text-muted">
          {p.state === "canceled" ? "자동 휴강 — " : "자동 휴강이었지만 수업함으로 바꿈 — "}
          {p.autoCancel.url ? (
            <a href={p.autoCancel.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-0.5 font-semibold text-primary hover:underline">
              {autoCancelText(p.autoCancel)}
              <ExternalLink className="size-3.5" aria-hidden />
            </a>
          ) : (
            autoCancelText(p.autoCancel)
          )}
        </p>
      )}
      <KV
        rows={[
          ["시간", <span key="t" className="num font-semibold">{fmtDateTime(s)}{e ? ` ~ ${fmtTime(e)}` : ""} · {p.periodsText}</span>],
          ...(p.room ? [["강의실", p.room] as [string, string]] : []),
          [
            "출결 한도",
            <span key="l" className="flex flex-wrap items-center gap-2">
              <LevelBadge level={p.level} />
              {p.level && <span className="text-[13px] text-muted">{p.level === "over" ? `${num(-p.remaining)}회 초과` : `남은 여유 ${p.spareSessions}회`}</span>}
            </span>,
          ],
        ]}
      />
      <div>
        <span className="label">출결</span>
        <AttendanceChips state={p.state} value={p.attendance} future={!p.started} onChange={(v) => void patch(v)} disabled={busy} />
        {!p.started && p.state === "scheduled" && <p className="hint">아직 시작하지 않은 수업 — 공결·휴강만 미리 적을 수 있습니다.</p>}
      </div>
      <div className="flex flex-wrap items-center justify-end gap-2 border-t border-border pt-4">
        <Link href={`/attendance?course=${encodeURIComponent(p.courseId)}`} className="btn" onClick={onClose}>
          출결에서 보기
        </Link>
      </div>
      <p className="hint">학교 공식 출결 기록이 아닙니다 — 내가 입력한 값 기준입니다.</p>
    </div>
  );
}

/* ---------------------------------------------------------------- 내 일정·할 일 */

function UserDetail({ ev, open, onClose }: { ev: CalEvent; open: boolean; onClose: () => void }) {
  const toast = useToast();
  const { refresh, status } = useAppData();
  const [editing, setEditing] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  if (ev.extendedProps.kind !== "user") return null;
  const p = ev.extendedProps;
  const categories = status?.categories ?? DEFAULT_CATEGORIES;

  if (editing) {
    const start = parseLocal(ev.start);
    let end: Date | null = ev.end ? parseLocal(ev.end) : null;
    if (ev.allDay && end) end = addDays(end, -1);
    const draft: EventDraft = { title: ev.title, start, end, allDay: ev.allDay, category: p.category, memo: p.memo, isTodo: p.isTodo, done: p.done };
    return (
      <EventForm
        open={open}
        mode="edit"
        draft={draft}
        categories={categories}
        onClose={() => setEditing(false)}
        onSave={async (input: UserEventInput) => {
          await api.updateEvent(ev.id, input);
          await refresh();
          setEditing(false);
          toast("저장했습니다", { tone: "success" });
        }}
      />
    );
  }

  const s = parseLocal(ev.start);
  let when: string;
  if (ev.allDay) {
    const last = ev.end ? addDays(parseLocal(ev.end), -1) : null;
    when = last && last > s ? `${fmtDateTime(s, false)} ~ ${fmtDateTime(last, false)} · 종일` : `${fmtDateTime(s, false)} · 종일`;
  } else {
    when = ev.end ? `${fmtDateTime(s)} ~ ${fmtDateTime(parseLocal(ev.end)).split(") ")[1] ?? ""}` : fmtDateTime(s);
  }

  const toggleDone = async (done: boolean) => {
    try {
      await api.updateEvent(ev.id, { done });
      await refresh();
    } catch (e) {
      toast(`저장하지 못했습니다: ${e instanceof Error ? e.message : String(e)}`, { tone: "error" });
    }
  };

  return (
    <Modal open={open} onClose={onClose} title={<span className={p.isTodo && p.done ? "text-muted line-through" : ""}>{ev.title}</span>}>
      <div className="space-y-4 pt-1">
        <div className="flex flex-wrap items-center gap-2">
          <Chip square>
            <span className="size-2 rounded-full" style={{ background: p.color }} aria-hidden />
            {p.categoryLabel}
          </Chip>
          <Chip tone={p.isTodo ? "accent" : "primary"} square>
            {p.isTodo ? "할 일" : "내 일정"}
          </Chip>
          {p.origin?.startsWith("ac:") && (
            <button type="button" className="inline-flex items-center gap-1 text-[13px] font-semibold text-primary hover:underline" onClick={() => navigateQuery({ event: p.origin }, "replace")}>
              <CalendarDays className="size-3.5" aria-hidden />
              학사 일정에서 가져옴
            </button>
          )}
        </div>
        <p className="text-[15px] font-semibold">{when}</p>
        {p.isTodo && (
          <label className="flex cursor-pointer items-center gap-3 rounded-xl bg-surface-2 px-3 py-2.5 text-[14px] font-semibold">
            <input type="checkbox" className="size-4 accent-[var(--ok)]" checked={p.done} onChange={(e) => toggleDone(e.target.checked)} />
            {p.done ? "완료됨 — 체크를 풀면 다시 할 일로" : "완료로 표시"}
          </label>
        )}
        {p.memo && <p className="rounded-xl bg-surface-2 p-3 text-[14px] whitespace-pre-wrap text-muted">{p.memo}</p>}
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-4">
          {confirm ? (
            <div className="flex items-center gap-2 text-[14px]">
              <span className="font-semibold text-danger-text">정말 삭제할까요?</span>
              <button
                type="button"
                className="btn btn-sm btn-danger"
                disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  try {
                    await api.deleteEvent(ev.id);
                    onClose();
                    await refresh();
                    toast("삭제했습니다");
                  } catch (e) {
                    setBusy(false);
                    toast(`삭제하지 못했습니다: ${e instanceof Error ? e.message : String(e)}`, { tone: "error" });
                  }
                }}
              >
                삭제
              </button>
              <button type="button" className="btn btn-sm" onClick={() => setConfirm(false)} disabled={busy}>
                취소
              </button>
            </div>
          ) : (
            <button type="button" className="btn btn-ghost btn-danger" onClick={() => setConfirm(true)}>
              <Trash2 aria-hidden />
              삭제
            </button>
          )}
          <button type="button" className="btn btn-primary" onClick={() => setEditing(true)}>
            <Pencil aria-hidden />
            수정
          </button>
        </div>
      </div>
    </Modal>
  );
}
