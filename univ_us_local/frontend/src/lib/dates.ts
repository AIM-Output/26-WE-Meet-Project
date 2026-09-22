// 날짜 유틸 — 전부 로컬 시간 기준. 백엔드도 tz 없는 ISO 문자열을 그대로 저장한다.

const pad = (n: number) => String(n).padStart(2, "0");

export const WEEKDAY_KO = ["일", "월", "화", "수", "목", "금", "토"];

/** Date → 'YYYY-MM-DD' */
export function toDateStr(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Date → 'YYYY-MM-DDTHH:MM:SS' (로컬, tz 없음) */
export function toLocalIso(d: Date): string {
  return `${toDateStr(d)}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

/** Date → datetime-local input 값 'YYYY-MM-DDTHH:MM' */
export function toInputDateTime(d: Date): string {
  return `${toDateStr(d)}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** 'YYYY-MM-DD' 또는 ISO → Date (로컬) */
export function parseLocal(s: string): Date {
  // Date 생성자는 'YYYY-MM-DD' 를 UTC 로 해석하므로 직접 쪼갠다.
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?/);
  if (!m) return new Date(s);
  return new Date(+m[1], +m[2] - 1, +m[3], +(m[4] ?? 0), +(m[5] ?? 0), +(m[6] ?? 0));
}

export function startOfDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

export function addDays(d: Date, n: number): Date {
  const r = new Date(d);
  r.setDate(r.getDate() + n);
  return r;
}

export function isSameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

/** 오늘 기준 D-day (양수 = 남음, 0 = 오늘, 음수 = 지남) */
export function daysUntil(target: Date, now = new Date()): number {
  const ms = startOfDay(target).getTime() - startOfDay(now).getTime();
  return Math.round(ms / 86_400_000);
}

export function ddayLabel(n: number): string {
  if (n === 0) return "D-Day";
  return n > 0 ? `D-${n}` : `D+${-n}`;
}

export function fmtTime(d: Date): string {
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** '9월 16일 (수) 16:00' */
export function fmtDateTime(d: Date, withTime = true): string {
  const base = `${d.getMonth() + 1}월 ${d.getDate()}일 (${WEEKDAY_KO[d.getDay()]})`;
  return withTime ? `${base} ${fmtTime(d)}` : base;
}

/** '2026년 9월 21일 월요일' */
export function fmtLongDate(d: Date): string {
  return `${d.getFullYear()}년 ${d.getMonth() + 1}월 ${d.getDate()}일 ${WEEKDAY_KO[d.getDay()]}요일`;
}

/** 'YYYY-MM-DD HH:MM' (동기화 시각 표시용) → '9/21 12:51' */
export function fmtShortStamp(s: string | null | undefined): string {
  if (!s) return "-";
  const d = parseLocal(s.replace(" ", "T"));
  if (isNaN(d.getTime())) return s;
  return `${d.getMonth() + 1}/${d.getDate()} ${fmtTime(d)}`;
}
