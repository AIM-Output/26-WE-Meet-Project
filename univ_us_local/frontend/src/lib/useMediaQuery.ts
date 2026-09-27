"use client";

import { useSyncExternalStore } from "react";

/** CSS 미디어 쿼리 일치 여부. 프리렌더 중에는 false. */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (cb) => {
      const m = window.matchMedia(query);
      m.addEventListener("change", cb);
      return () => m.removeEventListener("change", cb);
    },
    () => window.matchMedia(query).matches,
    () => false,
  );
}

export const useIsXl = () => useMediaQuery("(min-width: 1280px)");
