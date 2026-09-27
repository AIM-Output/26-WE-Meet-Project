"use client";

import Link from "next/link";
import { useMemo } from "react";
import { motion } from "motion/react";
import { FEATURES } from "@/lib/features";
import { useAssignments } from "@/lib/useAssignments";
import { useAcademic } from "@/lib/useAcademic";
import { isOpen } from "@/lib/priority";
import { attendanceStats, demoAttendance, demoExams, demoGradStatus, demoMaterialCounts, demoOpportunities, demoTeam } from "@/lib/demo";
import { daysUntil, parseLocal } from "@/lib/dates";

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
  const { list: academic, reviewCount } = useAcademic();

  const data = useMemo<Record<string, TileData>>(() => {
    const openList = list.filter(isOpen);
    const soon = openList.filter((a) => a.remainingHours >= 0 && a.remainingHours <= 72).length;
    const risky = demoAttendance.filter((c) => c.planned > 0 && ["위험", "초과"].includes(attendanceStats(c).level));
    const upcomingExam = demoExams
      .filter((e) => e.status === "confirmed" && daysUntil(parseLocal(e.date)) >= 0)
      .sort((a, b) => a.date.localeCompare(b.date))[0];
    const month = new Date().toISOString().slice(0, 7);
    const materials = Object.values(demoMaterialCounts).reduce((s, x) => s + x.files, 0);
    const eligible = demoOpportunities.filter((o) => o.verdict === "해당").length;
    return {
      academic: reviewCount
        ? { value: `확인 필요 ${reviewCount}건`, sub: "공지에서 찾은 일정", tone: "warn", demo: true }
        : { value: `${academic.filter((a) => a.start.startsWith(month)).length}건`, sub: "이번 달 학사일정", demo: true },
      assignments: { value: `${openList.length}건`, sub: soon ? `3일 안 마감 ${soon}건` : "진행 중인 과제", tone: soon ? "warn" : "default" },
      graduation: { value: `${demoGradStatus.total.required - demoGradStatus.total.earned}학점`, sub: "졸업까지", demo: true },
      attendance: risky.length
        ? { value: `위험 ${risky.length}과목`, sub: risky.map((c) => c.name).join(", "), tone: "danger", demo: true }
        : { value: "안전", sub: "모든 과목", tone: "ok", demo: true },
      courses: { value: `자료 ${materials}개`, sub: "요약·예상 문제", demo: true },
      exams: upcomingExam
        ? { value: `D-${daysUntil(parseLocal(upcomingExam.date))}`, sub: `${upcomingExam.course} ${upcomingExam.kind}`, demo: true }
        : { value: "없음", sub: "등록된 시험", demo: true },
      opportunities: { value: `해당 ${eligible}건`, sub: "장학 · 대외활동", tone: eligible ? "ok" : "default", demo: true },
      team: { value: "투표 중", sub: `${demoTeam.name} · 내일 18:00 마감`, demo: true },
      briefing: { value: "오늘", sub: "지난 30일 브리핑" },
      chat: { value: "물어보기", sub: "일정 등록 · 조회 · 이동", demo: true },
    };
  }, [list, academic, reviewCount]);

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
                  <span className="grid size-8 flex-none place-items-center rounded-lg bg-primary-soft text-primary transition-colors group-hover:bg-primary group-hover:text-white">
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
