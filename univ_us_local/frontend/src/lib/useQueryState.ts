"use client";

import { useCallback } from "react";
import { useSearchParams } from "next/navigation";

// Frontend-Route 19절 규칙을 한곳에 가둔다.
//   모달(event·new·item·poll…) = push → 뒤로가기로 닫힌다
//   탭·필터·정렬              = replace → 히스토리를 어지럽히지 않는다
//   알 수 없는 값은 기본값으로 떨어뜨리고, 기본값은 URL 에서 뺀다(빈 URL 도 늘 유효).
// Next 16 은 window.history.pushState/replaceState 를 useSearchParams 와 동기화한다 (linking-and-navigating 문서).

export type HistoryMode = "push" | "replace";

// 이 탭에서 우리가 push 로 연 주소들. 닫을 때 이 목록에 있으면 history.back(), 없으면(직접 들어온 링크) replace 로 뺀다.
const pushed = new Set<string>();
const here = () => window.location.pathname + window.location.search;

export function navigateQuery(updates: Record<string, string | null | undefined>, mode: HistoryMode = "replace") {
  const before = here();
  const params = new URLSearchParams(window.location.search);
  for (const [k, v] of Object.entries(updates)) {
    if (v === null || v === undefined || v === "") params.delete(k);
    else params.set(k, v);
  }
  const qs = params.toString();
  const url = window.location.pathname + (qs ? `?${qs}` : "") + window.location.hash;
  if (mode === "push") {
    window.history.pushState(null, "", url);
    pushed.add(here());
  } else {
    window.history.replaceState(null, "", url);
    if (pushed.delete(before)) pushed.add(here());
  }
}

/** 모달 닫기 — push 로 열었으면 뒤로가기, 딥링크로 들어왔으면 파라미터만 지운다. */
export function closeQuery(keys: string[]) {
  const cur = here();
  if (pushed.has(cur)) {
    pushed.delete(cur);
    window.history.back();
    return;
  }
  navigateQuery(Object.fromEntries(keys.map((k) => [k, null])), "replace");
}

/** 쿼리 파라미터 하나 ↔ 상태. `allowed` 밖의 값은 기본값. */
export function useQueryParam<T extends string>(
  key: string,
  fallback: T,
  allowed?: readonly T[],
): [T, (value: T | null, mode?: HistoryMode) => void] {
  const sp = useSearchParams();
  const raw = sp.get(key);
  const value = raw !== null && (!allowed || (allowed as readonly string[]).includes(raw)) ? (raw as T) : fallback;
  const set = useCallback(
    (v: T | null, mode: HistoryMode = "replace") =>
      navigateQuery({ [key]: v === null || (v === fallback && mode === "replace") ? null : v }, mode),
    [key, fallback],
  );
  return [value, set];
}

/** 값이 자유로운(모달 id 같은) 파라미터 */
export function useQueryValue(key: string): string | null {
  return useSearchParams().get(key);
}
