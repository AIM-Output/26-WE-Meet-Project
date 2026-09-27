"use client";

import { useCallback, useMemo, useSyncExternalStore } from "react";

// 브라우저 localStorage — 보던 뷰·접힘 같은 개인 편의와, 백엔드 API 가 생기기 전 임시 저장에만 쓴다.
// 사생활 모드·차단 환경에서는 접근이 throw 하므로 전부 try 로 감싼다.

const PREFIX = "univus:";
const EVENT = "univus-store";

function readRaw(key: string): string | null {
  try {
    return window.localStorage.getItem(PREFIX + key);
  } catch {
    return null;
  }
}

export function readStore<T>(key: string, fallback: T): T {
  const raw = readRaw(key);
  if (raw === null) return fallback;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

export function writeStore<T>(key: string, value: T): void {
  try {
    window.localStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch {
    /* 저장이 안 돼도 화면은 동작한다 */
  }
  window.dispatchEvent(new CustomEvent(EVENT, { detail: key }));
}

function subscribe(cb: () => void) {
  window.addEventListener(EVENT, cb);
  window.addEventListener("storage", cb); // 다른 탭에서 바꾼 값
  return () => {
    window.removeEventListener(EVENT, cb);
    window.removeEventListener("storage", cb);
  };
}

/** localStorage 와 묶인 상태. 같은 키를 쓰는 다른 컴포넌트·탭과도 동기화된다. 프리렌더에서는 fallback. */
export function useStored<T>(key: string, fallback: T): [T, (next: T | ((prev: T) => T)) => void] {
  const raw = useSyncExternalStore(
    subscribe,
    () => readRaw(key),
    () => null,
  );
  // fallback 은 매 렌더 새 객체일 수 있어 raw(문자열)만 기준으로 다시 파싱한다
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const value = useMemo<T>(() => (raw === null ? fallback : safeParse(raw, fallback)), [raw]);

  const set = useCallback(
    (next: T | ((prev: T) => T)) => {
      const prev = readStore(key, fallback);
      writeStore(key, typeof next === "function" ? (next as (p: T) => T)(prev) : next);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [key],
  );

  return [value, set];
}

function safeParse<T>(raw: string, fallback: T): T {
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}
