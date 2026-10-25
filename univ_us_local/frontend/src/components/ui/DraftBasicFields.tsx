import type { DraftBasic } from "@/lib/scholarships";

const FIELDS: { k: keyof DraftBasic; label: string; ph: string; wide?: boolean; type?: string; numeric?: boolean; auto?: string }[] = [
  { k: "name", label: "이름", ph: "예: 홍길동", auto: "name" },
  { k: "studentId", label: "학번", ph: "예: 2023000000", numeric: true },
  { k: "department", label: "학과(소속)", ph: "예: AI융합대학 인공지능학부", wide: true },
  { k: "grade", label: "학년", ph: "예: 3", numeric: true },
  { k: "phone", label: "연락처", ph: "예: 010-0000-0000", type: "tel", auto: "tel" },
  { k: "email", label: "이메일 (선택)", ph: "예: me@example.com", type: "email", wide: true, auto: "email" },
];

/** 초안 재료의 기본 정보 칸 — 장학·대외활동 재료 창이 같이 쓴다. 초안 '1. 기본 정보'와 문단의 {{이름}} 빈칸에 들어간다(F11 basicinfo). */
export function DraftBasicFields({
  value,
  onChange,
  idPrefix,
  fromNote,
}: {
  value: DraftBasic;
  onChange: (next: DraftBasic) => void;
  idPrefix: string;
  fromNote?: string | null;
}) {
  return (
    <fieldset className="space-y-2">
      <legend className="label">기본 정보</legend>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {FIELDS.map((f) => (
          <div key={f.k} className={f.wide ? "sm:col-span-2" : undefined}>
            <label htmlFor={`${idPrefix}-${f.k}`} className="mb-1 block text-[12px] text-muted">
              {f.label}
            </label>
            <input
              id={`${idPrefix}-${f.k}`}
              className="field text-[14px]"
              type={f.type ?? "text"}
              inputMode={f.numeric ? "numeric" : undefined}
              autoComplete={f.auto ?? "off"}
              placeholder={f.ph}
              value={value[f.k]}
              onChange={(e) => onChange({ ...value, [f.k]: e.target.value })}
            />
          </div>
        ))}
      </div>
      {fromNote && <p className="text-[12px] text-faint">{fromNote}</p>}
      <p className="hint">
        작성일은 초안을 만든 날짜로 들어갑니다. 이름·학번·연락처는 이 PC 의 초안 재료에만 저장되고 AI 문단 작성(LLM)에는 보내지 않습니다 — 초안을 다 만든 뒤 이 PC 에서 채워 넣습니다.
      </p>
    </fieldset>
  );
}
