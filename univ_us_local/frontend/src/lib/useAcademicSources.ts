"use client";

import { useCallback, useEffect, useState } from "react";
import { useAppData } from "@/components/app/AppData";
import { useToast } from "@/components/ui/Toast";
import { api } from "./api";
import type { SourceRowApi, SourcesResponse } from "./types";

// F1 학사 수집 원천 4곳 — 설정 › 수집 원천(/settings/sources)과 /academic 이 같이 쓴다 (F1-S12).
//   ① jnu_calendar 학교 학사일정 표   ② jnu_notice 학교 공지 › 학사안내
//   ④ my_dept 내 학부 공지            ③ my_college 내 단과대학 공지   (③·④ 는 프로필 소속으로 홈페이지를 찾는다)
// 끄면 새로 받지 않고, 그 원천에서만 온 일정은 목록·캘린더에서 바로 빠진다(서버가 거른다). 다시 켜면 돌아온다.

/** 화면에 보일 이름 — 내 소속 원천은 소속 이름으로 ('내 학부 공지' → '인공지능학부 공지') */
export const sourceTitle = (r: Pick<SourceRowApi, "name" | "scope" | "target">) => (r.scope && r.target ? `${r.target} 공지` : r.name);

/** 켰을 때 바로 받아 와야 하나 — 한 번도 안 받았거나 소속이 바뀐 뒤 아직 안 받은 것 (프로필에 소속이 없으면 받을 게 없다) */
const needsFetch = (r: SourceRowApi) => r.enabled && (r.state === "never" || r.stale) && r.resolve !== "needs_profile" && r.resolve !== "not_found";

export function useAcademicSources() {
  const toast = useToast();
  const { status, academicSyncing, startAcademicSync, refresh, refreshAcademic, profile } = useAppData();
  const [data, setData] = useState<SourcesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await api.sources());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  // 수집이 끝나거나(updatedAt) 프로필 소속이 바뀌면(③·④ 대상이 달라진다) 다시 부른다
  const stamp = status?.academic?.updatedAt;
  const profileStamp = profile?.updatedAt;
  useEffect(() => {
    void Promise.resolve().then(load);
  }, [load, stamp, academicSyncing, profileStamp]);

  const replace = (row: SourceRowApi) => setData((d) => (d ? { ...d, sources: d.sources.map((x) => (x.key === row.key ? row : x)) } : d));

  const toggle = async (r: SourceRowApi, on: boolean) => {
    const title = sourceTitle(r);
    replace({ ...r, enabled: on });
    setBusy(r.key);
    try {
      const row = await api.patchSource(r.key, { enabled: on });
      replace(row);
      await Promise.all([refresh(), refreshAcademic()]); // 목록·캘린더에서 빠지거나 돌아온다
      if (on && needsFetch(row)) {
        void startAcademicSync(row.key); // 처음 켠 원천은 바로 받아 온다
      } else {
        toast(
          on
            ? `${title} 켰습니다${row.items ? ` — 일정 ${row.items}건이 다시 보입니다` : ""}`
            : `${title} 껐습니다 — 여기서만 온 일정은 목록·캘린더에서 빠집니다`,
          { action: { label: "되돌리기", onClick: () => void toggle(row, !on) } },
        );
      }
    } catch (e) {
      replace(r);
      toast(`바꾸지 못했습니다: ${e instanceof Error ? e.message : String(e)}`, { tone: "error" });
    } finally {
      setBusy(null);
    }
  };

  /** ③·④ 게시판 직접 지정 — null 이면 자동으로(프로필 소속 → 홈페이지 메뉴) 되돌린다. 켜져 있으면 바로 받아 온다. */
  const setOverride = async (r: SourceRowApi, url: string | null): Promise<boolean> => {
    setBusy(r.key);
    try {
      const row = await api.patchSource(r.key, { overrideUrl: url });
      replace(row);
      if (row.enabled) void startAcademicSync(row.key);
      else toast(url ? "게시판을 지정했습니다 — 켜면 받아 옵니다" : "자동으로 되돌렸습니다 — 켜면 받아 옵니다");
      return true;
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), { tone: "error" });
      return false;
    } finally {
      setBusy(null);
    }
  };

  return {
    data,
    sources: data?.sources ?? [],
    error,
    busy,
    syncing: academicSyncing,
    reload: load,
    toggle,
    setOverride,
    sync: startAcademicSync,
  };
}
