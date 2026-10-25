"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAppData } from "@/components/app/AppData";
import { useToast } from "@/components/ui/Toast";
import { api } from "./api";
import type { SchDetail, SchOverview } from "./scholarships";

// F11 장학 — /scholarships 화면 데이터. 판정은 서버(F11_Scholarship_agent)가 부를 때마다 지금 프로필로 계산한 값을 그대로 쓴다.
// 수집이 끝나거나(06·18시 자동·'지금 수집') 프로필이 바뀌면 /api/status 의 scholarship.updatedAt 이 바뀐다 → 목록·상세를 다시 부른다.
// 수집 중에는 AppData 폴링(1분)보다 촘촘히 3초마다 진행 상태를 본다.

const msg = (e: unknown) => (e instanceof Error ? e.message : String(e));

export function useScholarships(itemId: string | null) {
  const toast = useToast();
  const { status, refresh, profile } = useAppData();
  const [data, setData] = useState<SchOverview | null>(null);
  const [detail, setDetail] = useState<SchDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const stamp = `${status?.scholarship?.updatedAt ?? ""}|${profile?.updatedAt ?? ""}`;
  const seen = useRef<string | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await api.scholarships());
      setError(null);
    } catch (e) {
      setError(msg(e));
    } finally {
      setLoading(false);
    }
  }, []);

  const loadDetail = useCallback(async (id: string | null) => {
    if (!id) {
      setDetail(null);
      return;
    }
    try {
      setDetail(await api.scholarship(id));
    } catch {
      setDetail(null);
    }
  }, []);

  useEffect(() => {
    void Promise.resolve().then(load);
  }, [load]);

  useEffect(() => {
    void Promise.resolve().then(() => loadDetail(itemId));
  }, [itemId, loadDetail]);

  // 다른 곳에서 수집이 끝났거나 프로필(민감정보 포함)이 바뀌었다 → 다시 판정된 목록·상세
  useEffect(() => {
    if (seen.current !== null && seen.current !== stamp) {
      void Promise.resolve().then(() => Promise.all([load(), loadDetail(itemId)]));
    }
    seen.current = stamp;
  }, [stamp, load, loadDetail, itemId]);

  // 수집 중이면 3초마다
  const running = !!data?.sync?.running;
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => void load(), 3000);
    return () => clearInterval(t);
  }, [running, load]);
  const wasRunning = useRef(false);
  useEffect(() => {
    if (wasRunning.current && !running && data) {
      const c = data.sync.exit_code;
      toast(c === 0 ? "장학 공지를 모았습니다" : c === 2 ? "일부 게시판을 읽지 못했습니다 — 원천 탭에서 확인하세요" : "장학 공지를 모으지 못했습니다", {
        tone: c === 0 ? "success" : "error",
      });
      void refresh();
    }
    wasRunning.current = running;
  }, [running, data, toast, refresh]);

  /** 바꾸는 요청 하나 — 성공하면 상세를 그 응답으로, 목록·타일은 다시 부른다 */
  const run = useCallback(
    async (fn: () => Promise<SchDetail | void>, ok?: string): Promise<boolean> => {
      setBusy(true);
      try {
        const d = await fn();
        if (d) setDetail(d);
        await Promise.all([load(), refresh()]);
        if (ok) toast(ok, { tone: "success" });
        return true;
      } catch (e) {
        toast(`처리하지 못했습니다: ${msg(e)}`, { tone: "error" });
        return false;
      } finally {
        setBusy(false);
      }
    },
    [load, refresh, toast],
  );

  const sync = useCallback(async () => {
    try {
      const s = await api.syncScholarships();
      if (s.already_running) toast("이미 장학 공지를 모으는 중입니다");
      await load();
    } catch (e) {
      toast(`수집을 시작하지 못했습니다: ${msg(e)}`, { tone: "error" });
    }
  }, [load, toast]);

  return { data, detail, error, loading, busy, reload: load, reloadDetail: () => loadDetail(itemId), run, sync, setDetail };
}
