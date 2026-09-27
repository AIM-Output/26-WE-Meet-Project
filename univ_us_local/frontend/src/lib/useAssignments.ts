"use client";

import { useEffect, useMemo, useState } from "react";
import { useAppData } from "@/components/app/AppData";
import { useStored } from "./storage";
import { buildAssignments, type Assignment } from "./priority";

// 과제 목록(F6) + 우선순위(F7). 소요시간 수정·'내가 체크함'은 PATCH /api/assignments 가 생기기 전까지 브라우저에 둔다.
// 순위는 저장하지 않고 1분마다 다시 계산한다(시간이 흐르면 그룹이 바뀐다).

export function useAssignments() {
  const { events } = useAppData();
  const [estimates, setEstimates] = useStored<Record<string, number>>("assignment-estimates", {});
  const [userDone, setUserDone] = useStored<Record<string, boolean>>("assignment-user-done", {});
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(id);
  }, []);

  const list: Assignment[] = useMemo(() => buildAssignments(events, estimates, userDone, now), [events, estimates, userDone, now]);

  return {
    list,
    now,
    setEstimate: (id: string, hours: number | null) =>
      setEstimates((m) => {
        const next = { ...m };
        if (hours === null) delete next[id];
        else next[id] = Math.max(0.25, hours);
        return next;
      }),
    setUserDone: (id: string, done: boolean) =>
      setUserDone((m) => {
        const next = { ...m };
        if (done) next[id] = true;
        else delete next[id];
        return next;
      }),
  };
}
