"use client";

import { useEffect, useMemo, useState } from "react";
import { useAppData } from "@/components/app/AppData";
import { api } from "./api";
import { readStore, writeStore } from "./storage";
import { buildAssignments, type Assignment } from "./priority";
import { usePriority } from "./usePriority";

// 과제 목록(F6) + 우선순위(F7). '내가 체크함'·소요시간은 서버(F6 과제 원장)에 저장한다 — 재수집해도 유지된다(F6-R34).
// 순위·이유·오늘 남은 시간은 서버(F7, GET /api/priority)가 계산한다 — 저장하지 않고 1분마다·과제가 바뀔 때 다시 받는다(usePriority).

const LEGACY_DONE = "assignment-user-done";
const LEGACY_EST = "assignment-estimates";
let migrating = false;

/** 예전엔 브라우저에만 두었던 값을 서버로 한 번 옮긴다 (예전 id·새 id 둘 다 받는다). 서버에 값이 있으면 서버가 이긴다. */
function useLegacyMigration(ready: boolean, refresh: () => Promise<void>) {
  useEffect(() => {
    if (!ready || migrating) return;
    const done = readStore<Record<string, boolean>>(LEGACY_DONE, {});
    const est = readStore<Record<string, number>>(LEGACY_EST, {});
    if (!Object.keys(done).length && !Object.keys(est).length) return;
    migrating = true;
    api
      .migrateAssignments({ userDone: done, estimates: est })
      .then(async (r) => {
        writeStore(LEGACY_DONE, {});
        writeStore(LEGACY_EST, {});
        if (r.userDone || r.estimates) await refresh();
      })
      .catch(() => {
        /* 서버가 꺼져 있으면 다음에 다시 */
      })
      .finally(() => {
        migrating = false;
      });
  }, [ready, refresh]);
}

export function useAssignments() {
  const { events, loading, refresh, patchAssignment } = useAppData();
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(id);
  }, []);
  useLegacyMigration(!loading && events.length > 0, refresh);

  const priority = usePriority();
  const list: Assignment[] = useMemo(() => buildAssignments(events, priority.data, now), [events, priority.data, now]);

  return {
    list,
    now,
    priority: priority.data,
    priorityError: priority.error,
    priorityLoading: priority.loading,
    reloadPriority: priority.reload,
    setEstimate: (id: string, hours: number | null) =>
      void patchAssignment(id, { estimatedHours: hours === null ? null : Math.max(0.25, hours) }),
    setUserDone: (id: string, done: boolean) => patchAssignment(id, { userDone: done }),
  };
}
