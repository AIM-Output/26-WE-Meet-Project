import { Building2, CalendarDays, ChartLine, Coffee, CreditCard, Flag, NotebookPen, PencilLine } from "lucide-react";
import { ACADEMIC_TYPE_META, type AcademicType } from "@/lib/demo";

// 학사 유형 아이콘 — 색만으로 구분하지 않도록 아이콘을 같이 쓴다.
const ICON: Record<AcademicType, typeof CreditCard> = {
  register: PencilLine,
  payment: CreditCard,
  semester: CalendarDays,
  exam: NotebookPen,
  leave: Building2,
  grade: ChartLine,
  holiday: Coffee,
  etc: Flag,
};

export function AcademicIcon({ type, size = 32 }: { type: AcademicType; size?: number }) {
  const Icon = ICON[type];
  const meta = ACADEMIC_TYPE_META[type];
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
