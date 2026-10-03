"use client";

import Link from "next/link";
import { useEffect, useMemo } from "react";
import { UserCheck } from "lucide-react";
import { Page, PageHeader } from "@/components/ui/Layout";
import { Tabs } from "@/components/ui/Tabs";
import { Banner, ErrorPanel, SkeletonCards } from "@/components/ui/Feedback";
import { CourseStatusCard } from "@/components/attendance/CourseStatusCard";
import { WeekCheck } from "@/components/attendance/WeekCheck";
import { TimetableEditor } from "@/components/attendance/TimetableEditor";
import { useAttendance } from "@/lib/useAttendance";
import { navigateQuery, useQueryParam, useQueryValue } from "@/lib/useQueryState";
import { LEVEL_RANK, num, type AttCourse } from "@/lib/attendance";
import { fmtMD, parseLocal } from "@/lib/dates";

// /attendance — 과목별 현황 / 이번 주 / 시간표 설정 (Frontend-Route 8절). 입력을 얼마나 쉽게 만드느냐가 화면의 전부다.
// 숫자(총 시수·허용·남은 여유·상태)는 전부 백엔드 계산(F3_Attendance_agent/attendance/calc.py)을 그대로 보여 준다.

const TABS = ["status", "week", "timetable"] as const;

export default function AttendancePage() {
  const [tab, setTab] = useQueryParam("tab", "status", TABS);
  const semParam = useQueryValue("semester");
  const open = useQueryValue("course");
  const att = useAttendance(semParam ?? undefined);
  const d = att.data;

  // ?course= 로 들어오면(알림·캘린더에서) 그 과목 카드로 스크롤
  useEffect(() => {
    if (!open || !d || tab !== "status") return;
    const id = window.setTimeout(() => document.getElementById(`course-${open}`)?.scrollIntoView({ behavior: "smooth", block: "start" }), 80);
    return () => window.clearTimeout(id);
  }, [open, d, tab]);

  const sorted = useMemo(() => {
    if (!d) return [];
    const rank = (c: AttCourse) => (c.excluded ? -3 : !c.timetable.meetings.length ? -2 : c.summary.level ? LEVEL_RANK[c.summary.level] : -1);
    return [...d.courses].sort((a, b) => rank(b) - rank(a));
  }, [d]);

  if (att.loading)
    return (
      <Page>
        <PageHeader icon={<UserCheck />} title="출결" />
        <SkeletonCards count={4} />
      </Page>
    );
  if (!d)
    return (
      <Page>
        <PageHeader icon={<UserCheck />} title="출결" />
        <ErrorPanel message={`불러오지 못했습니다 — ${att.error ?? ""}`} onRetry={() => void att.reload()} />
      </Page>
    );

  const sem = d.semester;
  const t = d.totals;
  const over = d.courses.filter((c) => !c.excluded && c.summary.level === "over");
  const isCurrent = sem.id === d.current;
  const w = d.academicWarning;

  return (
    <Page>
      <PageHeader
        icon={<UserCheck />}
        title="출결"
        subtitle={
          sem.start && sem.end
            ? `${sem.label} · 개강 ${fmtMD(parseLocal(sem.start))} ~ 종강 ${fmtMD(parseLocal(sem.end))}${sem.startSource === "user" ? " (직접 입력)" : " (학사일정)"}`
            : `${sem.label} · 개강·종강 미입력`
        }
        actions={
          <>
            <label className="sr-only" htmlFor="att-semester">
              학기
            </label>
            <select
              id="att-semester"
              className="field field-sm w-auto"
              value={sem.id}
              onChange={(e) => navigateQuery({ semester: e.target.value === d.current ? null : e.target.value, course: null }, "replace")}
            >
              {d.semesters.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                  {s.current ? " (이번 학기)" : ""}
                </option>
              ))}
            </select>
            <button type="button" className="btn btn-sm" onClick={() => setTab("timetable")}>
              시간표 설정
            </button>
          </>
        }
      />

      {att.busy && <div className="fixed inset-x-0 top-16 z-30 h-0.5 animate-pulse bg-primary" aria-hidden />}

      <div className="mb-5 space-y-3">
        {over.length > 0 && (
          <Banner tone="danger">
            출석 미달 — {over.map((c) => `${c.short}(결석 ${c.summary.effectiveAbsent}회 / 허용 ${num(c.summary.allowed)}회)`).join(", ")}. 결석이 1/4 을 넘었습니다 — 학과·교수님께 확인하세요.
          </Banner>
        )}
        <Banner tone="neutral">학교 공식 출결 기록이 아닙니다 — 내가 입력한 값 기준입니다.</Banner>
        {w.below && (
          <Banner tone="warn" action={<a href={w.sourceUrl} target="_blank" rel="noopener noreferrer" className="btn btn-sm">학사경고 기준</a>}>
            {w.message}
          </Banner>
        )}
        {!isCurrent && <Banner tone="info">지난 학기를 보고 있습니다 — 경고 알림은 이번 학기만 만듭니다.</Banner>}
        {d.courses.length === 0 ? (
          <Banner tone="warn" action={<Link href="/settings/sources" className="btn btn-sm">수집 원천</Link>}>
            e클래스 동기화를 먼저 해 주세요 — 과목 목록은 e클래스에서 가져옵니다.
          </Banner>
        ) : (
          (!sem.start || !sem.end) && (
            <Banner tone="warn" action={<button type="button" className="btn btn-sm" onClick={() => setTab("timetable")}>직접 입력</button>}>
              학사일정에서 개강·종강을 찾지 못했습니다 — 개강·종강이 있어야 수업 횟수를 셉니다.
            </Banner>
          )
        )}
        {t.unchecked > 0 && tab !== "week" && (
          <Banner tone="warn" action={<button type="button" className="btn btn-sm" onClick={() => setTab("week")}>지금 입력</button>}>
            확인하지 않은 수업 {t.unchecked}회
          </Banner>
        )}
      </div>

      <Tabs
        className="mb-5"
        label="출결 보기"
        value={tab}
        onChange={(k) => setTab(k)}
        items={[
          { key: "status", label: "과목별 현황" },
          { key: "week", label: "이번 주", count: t.unchecked || undefined },
          { key: "timetable", label: "시간표 설정", count: t.needsTimetable.length || undefined },
        ]}
      />

      {tab === "status" &&
        (d.courses.length === 0 ? null : (
          <ul className="space-y-3">
            {sorted.map((c) => (
              <CourseStatusCard key={c.id} course={c} att={att} periods={d.periods} expanded={open === c.id} />
            ))}
          </ul>
        ))}
      {tab === "week" && <WeekCheck courses={d.courses} att={att} />}
      {tab === "timetable" && <TimetableEditor data={d} att={att} />}
    </Page>
  );
}
