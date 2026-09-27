"use client";

import { useMemo } from "react";
import { useStored } from "./storage";
import { demoAcademic, type AcademicEvent } from "./demo";

// F1 학사일정 (예시 데이터 + 사용자가 바꾼 값). PATCH /api/academic/events/{id} 가 생기면 그쪽으로 옮긴다.
type Override = Partial<Pick<AcademicEvent, "status" | "memo" | "reminders" | "start" | "end">>;

export function useAcademic() {
  const [overrides, setOverrides] = useStored<Record<string, Override>>("academic-overrides", {});

  const list = useMemo(() => demoAcademic.map((e) => ({ ...e, ...overrides[e.id] })), [overrides]);

  const update = (id: string, patch: Override) => setOverrides((m) => ({ ...m, [id]: { ...m[id], ...patch } }));

  return { list, update, reviewCount: list.filter((e) => e.status === "review").length };
}
