"use client";

import { useEffect, useSyncExternalStore } from "react";
import { useAppData } from "@/components/app/AppData";
import { api } from "./api";
import type { PriorityOverview } from "./priority";

// F7 우선순위 — GET /api/priority 하나를 대시보드의 여러 부품(먼저 할 것 · 할 일 · 기능 타일 · 과제 화면)이 같이 쓴다.
// 순위는 저장하지 않으므로(F7 6절) 다시 부르는 때:
//   ① 1분마다 — 시간이 흐르면 그룹이 바뀐다 (F7-R17)
//   ② /api/events 가 바뀔 때 — 수집 반영 · 내가 체크함 · 소요시간 수정 · 수업·일정 변경(오늘 남은 시간)
//   ③ 우선순위 설정을 저장했을 때
// 여러 부품이 같은 순간에 불러도 요청은 하나만 나간다. 도는 중에 또 부르면 끝난 뒤 한 번 더 부른다(방금 저장한 값을 놓치지 않게).

type Snap = { data: PriorityOverview | null; error: string | null; loading: boolean };

let snap: Snap = { data: null, error: null, loading: true };
let inflight: Promise<void> | null = null;
let again = false;
let timer: number | null = null;
let lastEvents: unknown = undefined;
const subs = new Set<() => void>();

function set(next: Partial<Snap>) {
  snap = { ...snap, ...next };
  subs.forEach((f) => f());
}

export function reloadPriority(): Promise<void> {
  if (inflight) {
    again = true;
    return inflight;
  }
  inflight = api
    .priority()
    .then((data) => set({ data, error: null, loading: false }))
    .catch((e: unknown) => set({ error: e instanceof Error ? e.message : String(e), loading: false }))
    .finally(() => {
      inflight = null;
      if (again) {
        again = false;
        void reloadPriority();
      }
    });
  return inflight;
}

function subscribe(fn: () => void) {
  subs.add(fn);
  if (timer === null) timer = window.setInterval(() => void reloadPriority(), 60_000);
  return () => {
    subs.delete(fn);
    if (subs.size === 0 && timer !== null) {
      window.clearInterval(timer);
      timer = null;
    }
  };
}

const getSnap = () => snap;

export function usePriority() {
  const { events } = useAppData();
  const s = useSyncExternalStore(subscribe, getSnap, getSnap);
  useEffect(() => {
    if (events === lastEvents) return; // 같은 목록을 본 다른 부품이 이미 불렀다
    lastEvents = events;
    void Promise.resolve().then(reloadPriority);
  }, [events]);
  return { ...s, reload: reloadPriority };
}
