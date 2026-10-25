// 라우트 목록 — Frontend-Route 2-1. 새 라우트를 더하면 여기(=대시보드 기능 타일)만 늘린다. 헤더는 고치지 않는다(3절).

import {
  BookOpen,
  ClipboardList,
  GraduationCap,
  HandCoins,
  Landmark,
  MessageCircle,
  Sun,
  Target,
  Trophy,
  UserCheck,
  type LucideIcon,
} from "lucide-react";

export interface Feature {
  key: string;
  label: string;
  href: string;
  icon: LucideIcon;
  fid: string;
}

export const FEATURES: Feature[] = [
  { key: "academic", label: "학사일정", href: "/academic", icon: Landmark, fid: "F1" },
  { key: "assignments", label: "E클래스", href: "/assignments", icon: ClipboardList, fid: "F6·F7" }, // 과제·동영상 + 공지·자료 (/eclass/posts)
  { key: "graduation", label: "졸업요건", href: "/graduation", icon: GraduationCap, fid: "F2" },
  { key: "attendance", label: "출결", href: "/attendance", icon: UserCheck, fid: "F3" },
  { key: "courses", label: "강의자료", href: "/courses", icon: BookOpen, fid: "F4" },
  { key: "exams", label: "시험·발표", href: "/exams", icon: Target, fid: "F5" },
  // 2026-10-09 '기회'(F11~13 한 화면)를 나눴다 — 장학(F11)은 /scholarships, 대외활동·사업단(F12·F13)은 /opportunities.
  // 팀플(F16, /team) 타일 자리에 대외활동을 둔다(10칸 배치 유지). /team 화면은 남아 있고 타일만 빠졌다.
  { key: "scholarships", label: "장학", href: "/scholarships", icon: HandCoins, fid: "F11" },
  { key: "opportunities", label: "대외활동", href: "/opportunities", icon: Trophy, fid: "F12·F13" },
  { key: "briefing", label: "브리핑", href: "/briefing", icon: Sun, fid: "C4·F10" }, // 공통 기능 C4 가 F10 요구사항을 구현
  { key: "chat", label: "대화", href: "/chat", icon: MessageCircle, fid: "F9" },
];

export const SETTINGS = [
  { href: "/settings/profile", label: "내 프로필" },
  { href: "/settings/sources", label: "수집 원천" },
  { href: "/settings/requirements", label: "졸업요건 기준" },
  { href: "/settings/availability", label: "가용 시간" },
  { href: "/settings/notifications", label: "알림·브리핑" },
] as const;
