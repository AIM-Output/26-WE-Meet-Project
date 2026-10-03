"use client";

import { useCallback, useEffect, useState } from "react";
import { useAppData } from "@/components/app/AppData";
import { useToast } from "@/components/ui/Toast";
import { api } from "./api";
import type { FeedItem, FeedList } from "./assignments";

// E클래스 새 글·자료 — 목록은 한 번에 받고(수십 건) 종류·과목은 화면에서 거른다.
// 수집이 끝나 /api/status 의 eclass.feed 가 바뀌면 다시 받는다. 읽음은 화면을 먼저 바꾼다(낙관적).

export function useEclassFeed() {
  const toast = useToast();
  const { status } = useAppData();
  const [data, setData] = useState<FeedList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const stamp = `${status?.eclass?.feed?.updatedAt ?? ""}|${status?.eclass?.feed?.total ?? ""}`;

  const load = useCallback(async () => {
    try {
      setData(await api.eclassFeed());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void Promise.resolve().then(load);
  }, [load, stamp]);

  const setRead = useCallback(
    async (ids: string[] | "all", read = true) => {
      const before = data;
      setData((d) =>
        d
          ? (() => {
              const items = d.items.map((it) => (ids === "all" || ids.includes(it.id) ? { ...it, read, isNew: read ? false : it.isNew } : it));
              return { ...d, items, counts: { ...d.counts, unread: items.filter((i) => !i.read).length } };
            })()
          : d,
      );
      try {
        await api.readFeed(ids === "all" ? { all: true } : { ids, read });
      } catch (e) {
        setData(before);
        toast(`저장하지 못했습니다: ${e instanceof Error ? e.message : String(e)}`, { tone: "error" });
      }
    },
    [data, toast],
  );

  const detail = useCallback(async (id: string): Promise<FeedItem | null> => {
    try {
      return await api.eclassFeedItem(id);
    } catch {
      return null;
    }
  }, []);

  return { data, error, loading: !data && !error, reload: load, setRead, detail };
}
