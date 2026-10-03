import { Building2, CalendarDays, ChartLine, Coffee, CreditCard, Flag, Info, NotebookPen, PencilLine } from "lucide-react";
import { typeMeta, type AcademicType } from "@/lib/academic";

// 학사 유형 아이콘 — 색만으로 구분하지 않도록 아이콘을 같이 쓴다 (요구사항정의서 F1 '색·아이콘').
const ICON: Record<AcademicType, typeof CreditCard> = {
  registration: Building2,
  tuition: CreditCard,
  course_reg: PencilLine,
  grade: ChartLine,
  exam: NotebookPen,
  vacation: CalendarDays,
  holiday: Coffee,
  event: Flag,
  etc: Info,
};

export function AcademicIcon({ type, size = 32 }: { type: string; size?: number }) {
  const Icon = ICON[type as AcademicType] ?? Info;
  const meta = typeMeta(type);
  return (
    <span
      className="grid flex-none place-items-center rounded-lg"
      style={{ width: size, height: size, background: `${meta.color}14`, color: meta.color }}
      title={meta.label}
    >
      <Icon style={{ width: size / 2, height: size / 2 }} aria-hidden />
    </span>
  );
}
