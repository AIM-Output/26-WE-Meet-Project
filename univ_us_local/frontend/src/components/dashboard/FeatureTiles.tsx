"use client";

import Link from "next/link";
import { useMemo } from "react";
import { motion } from "motion/react";
import { FEATURES } from "@/lib/features";
import { useAssignments } from "@/lib/useAssignments";
import { useAcademic } from "@/lib/useAcademic";
import { isOpen } from "@/lib/priority";
import { demoOpportunities, demoTeam } from "@/lib/demo";
import { useAppData } from "@/components/app/AppData";
import { hm } from "@/lib/exams";

// 기능 타일 = 메뉴(GNB 대신). 단순 링크가 아니라 숫자가 살아 있는 타일이다(Frontend-Route 3절).

type Tone = "default" | "warn" | "danger" | "ok";
interface TileData {
  value: string;
  sub: string;
  tone?: Tone;
  demo?: boolean;
}

const VALUE_TONE: Record<Tone, string> = { default: "text-text", warn: "text-warn-text", danger: "text-danger-text", ok: "text-ok-text" };

export default function FeatureTiles() {
  const { list } = useAssignments();
  const { reviewCount, status: academicStatus } = useAcademic();
  const { status } = useAppData();
  const grad = status?.graduation;
  const attd = status?.attendance;
  const mats = status?.materials;
  const exams = status?.exams;
  const feedUnread = status?.eclass?.feed?.unread ?? 0; // E클래스 새 공지·자료 (안 읽음)

  const data = useMemo<Record<string, TileData>>(() => {
    const openList = list.filter(isOpen);
    const soon = openList.filter((a) => a.remainingHours !== null && a.remainingHours >= 0 && a.remainingHours <= 72).length;
    const urgent = openList.filter((a) => a.group === "now").length; // F7 '지금 해야 함' (서버 계산)
    const risky = attd?.risky ?? [];
    const eligible = demoOpportunities.filter((o) => o.verdict === "해당").length;
    return {
      academic: reviewCount
        ? { value: `확인 필요 ${reviewCount}건`, sub: "공지에서 찾은 일정", tone: "warn" }
        : academicStatus?.available
          ? { value: `${academicStatus.counts?.thisMonth ?? 0}건`, sub: "이번 달 내 학사일정" }
          : { value: "—", sub: "학사일정 수집 전" },
      assignments: {
        value: `과제 ${openList.length}건`,
        sub: [urgent ? `지금 해야 함 ${urgent}건` : soon ? `3일 안 마감 ${soon}건` : "진행 중인 과제", feedUnread ? `새 공지·자료 ${feedUnread}건` : null]
          .filter(Boolean)
          .join(" · "),
        tone: urgent || soon ? "warn" : "default",
      },
      graduation: !grad?.available
        ? { value: "—", sub: "졸업요건 계산 전" }
        : grad.profileMissing?.length
          ? { value: "학과 입력", sub: "학과·입학년도가 있어야 계산합니다", tone: "warn" }
          : !grad.hasData
            ? { value: "가져오기", sub: "이수 내역을 아직 안 가져옴" }
            : grad.unmapped
              ? { value: `미분류 ${grad.unmapped}건`, sub: "과목 구분을 지정하세요", tone: "warn" }
              : grad.verdict === "충족"
                ? { value: "요건 충족", sub: "참고용 · 공식 졸업사정 아님", tone: "ok" }
                : { value: grad.remaining === null || grad.remaining === undefined ? "—" : `${grad.remaining}학점`, sub: `참고용 · ${grad.headline || "졸업까지 남은 학점"}` },
      // F3-S08 — 위험·초과가 있으면 빨강 요약, 없으면 '출결 이상 없음'
      attendance: !attd?.available
        ? { value: "—", sub: "출결 계산 전" }
        : !attd.courses
          ? { value: "—", sub: "e클래스 동기화 후 과목이 생깁니다" }
          : risky.length
            ? { value: `위험 ${risky.length}과목`, sub: risky.map((c) => `${c.name} ${c.levelLabel}`).join(", "), tone: "danger" }
            : !attd.withTimetable
              ? { value: "시간표 입력", sub: "요일·교시를 넣으면 수업 횟수를 셉니다", tone: "warn" }
              : attd.caution?.length
                ? { value: `주의 ${attd.caution.length}과목`, sub: attd.caution.join(", "), tone: "warn" }
                : { value: "이상 없음", sub: attd.unchecked ? `확인 안 한 수업 ${attd.unchecked}회` : "모든 과목 출결 이상 없음", tone: "ok" },
      // F4-S01 — 1차는 자료 모으기·열람까지. 요약·예상 문제는 아직 예시다.
      courses: !mats?.available
        ? { value: "—", sub: "강의자료를 아직 훑지 않았습니다" }
        : !mats.files
          ? { value: "없음", sub: mats.eclassAvailable ? "e클래스에 받은 자료가 없습니다" : "e클래스 동기화가 먼저입니다" }
          : {
              value: `자료 ${mats.files}개`,
              sub: `${mats.pages ?? 0}쪽${mats.attention ? ` · 확인 필요 ${mats.attention}건` : " · 열기·내려받기"}`,
              tone: mats.attention ? "warn" : "default",
            },
      // F5-S09 — 확인 필요·밀림이 먼저, 그다음 오늘 분량, 그다음 가장 가까운 시험
      exams: !exams?.available
        ? { value: "—", sub: "시험을 아직 찾지 않았습니다" }
        : exams.review
          ? { value: `확인 필요 ${exams.review}건`, sub: "공지에서 찾은 시험", tone: "warn" }
          : exams.behind
            ? { value: `밀림 ${exams.behind}개`, sub: "학습 계획을 재조정하세요", tone: "warn" }
            : exams.todayMinutes
              ? {
                  value: exams.todayPages ? `오늘 ${exams.todayPages}쪽` : hm(exams.todayMinutes),
                  sub: exams.todayText || `오늘 공부 ${hm(exams.todayMinutes)}`,
                }
              : exams.nextExam
                ? { value: exams.nextExam.ddayLabel, sub: `${exams.nextExam.course} ${exams.nextExam.typeLabel}` }
                : { value: "없음", sub: exams.eclassAvailable ? "등록된 시험이 없습니다" : "e클래스 동기화가 먼저입니다" },
      opportunities: { value: `해당 ${eligible}건`, sub: "장학 · 대외활동", tone: eligible ? "ok" : "default", demo: true },
      team: { value: "투표 중", sub: `${demoTeam.name} · 내일 18:00 마감`, demo: true },
      briefing: { value: "오늘", sub: "지난 30일 브리핑" },
      chat: { value: "물어보기", sub: "일정 등록 · 조회 · 이동", demo: true },
    };
  }, [list, academicStatus, reviewCount, grad, attd, mats, exams, feedUnread]);

  return (
    <section aria-labelledby="features-title">
      <h2 id="features-title" className="mb-3 text-[13px] font-bold tracking-wide text-muted">
        기능
      </h2>
      <ul className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
        {FEATURES.map((f, i) => {
          const d = data[f.key];
          const Icon = f.icon;
          return (
            <motion.li
              key={f.key}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.03, type: "spring", bounce: 0, visualDuration: 0.3 }}
            >
              <Link
                href={f.href}
                className="group card card-hover flex h-full flex-col gap-3 p-4 hover:bg-surface-2"
                aria-label={`${f.label} — ${d.value}, ${d.sub}`}
              >
                <span className="flex items-center gap-2">
                  <span className="grid size-8 flex-none place-items-center rounded-lg bg-primary-soft text-primary transition-colors group-hover:bg-primary group-hover:text-on-primary">
                    <Icon className="size-4" aria-hidden />
                  </span>
                  <span className="text-[14px] font-bold">{f.label}</span>
                  {d.demo && <span className="ml-auto rounded bg-surface-3 px-1.5 text-[11px] font-semibold text-faint">예시</span>}
                </span>
                <span>
                  <span className={`num block text-[20px] font-bold tracking-tight ${VALUE_TONE[d.tone ?? "default"]}`}>{d.value}</span>
                  <span className="block truncate text-[12px] text-muted">{d.sub}</span>
                </span>
              </Link>
            </motion.li>
          );
        })}
      </ul>
    </section>
  );
}
