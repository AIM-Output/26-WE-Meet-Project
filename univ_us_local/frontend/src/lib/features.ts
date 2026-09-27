// 라우트 목록 — Frontend-Route 2-1. 새 라우트를 더하면 여기(=대시보드 기능 타일)만 늘린다. 헤더는 고치지 않는다(3절).

import {
  BookOpen,
  ClipboardList,
  Gift,
  GraduationCap,
  Landmark,
  MessageCircle,
  Sun,
  Target,
  UserCheck,
  Users,
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
  { key: "assignments", label: "과제·마감", href: "/assignments", icon: ClipboardList, fid: "F6·F7" },
  { key: "graduation", label: "졸업요건", href: "/graduation", icon: GraduationCap, fid: "F2" },
  { key: "attendance", label: "출결", href: "/attendance", icon: UserCheck, fid: "F3" },
  { key: "courses", label: "강의자료", href: "/courses", icon: BookOpen, fid: "F4" },
  { key: "exams", label: "시험", href: "/exams", icon: Target, fid: "F5" },
  { key: "opportunities", label: "기회", href: "/opportunities", icon: Gift, fid: "F11~13" },
  { key: "team", label: "팀플", href: "/team", icon: Users, fid: "F16" },
  { key: "briefing", label: "브리핑", href: "/briefing", icon: Sun, fid: "F10" },
  { key: "chat", label: "대화", href: "/chat", icon: MessageCircle, fid: "F9" },
];

export const SETTINGS = [
  { href: "/settings/profile", label: "내 프로필" },
  { href: "/settings/sources", label: "수집 원천" },
  { href: "/settings/requirements", label: "졸업요건 기준" },
  { href: "/settings/availability", label: "가용 시간" },
  { href: "/settings/notifications", label: "알림·브리핑" },
] as const;
