"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAppData } from "@/components/app/AppData";
import { useToast } from "@/components/ui/Toast";
import { api } from "./api";
import type { MaterialItem, MaterialKind, MaterialsOverview } from "./materials";

// F4 강의자료 — /courses 화면 데이터. 목록·쪽수·상태는 전부 서버(F4_Textbook_agent)가 만든 값 그대로 쓴다.
// e클래스 동기화(F6)가 끝나 /api/status 의 materials.updatedAt 이 바뀌면 자동으로 다시 부른다 (F4-R05).

const msg = (e: unknown) => (e instanceof Error ? e.message : String(e));

export interface UseMaterials {
  data: MaterialsOverview | null;
  loading: boolean;
  error: string | null;
  busy: boolean;
  reload: () => Promise<void>;
  rescan: (force?: boolean) => Promise<void>;
  upload: (files: Iterable<File>) => Promise<MaterialItem[]>;
  remove: (m: MaterialItem) => Promise<boolean>;
}

export function useMaterials(courseId?: string | null, kind?: MaterialKind | null): UseMaterials {
  const toast = useToast();
  const { status } = useAppData();
  const [data, setData] = useState<MaterialsOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const stamp = status?.materials?.updatedAt ?? null;
  const seen = useRef<string | null | undefined>(undefined);

  const load = useCallback(async () => {
    try {
      const d = await api.materials({ course: courseId, kind });
      setData(d);
      seen.current = d.updatedAt;
      setError(null);
    } catch (e) {
      setError(msg(e));
    } finally {
      setLoading(false);
    }
  }, [courseId, kind]);

  useEffect(() => {
    void Promise.resolve().then(load);
  }, [load]);

  // 다른 화면에서 e클래스 동기화가 끝났다 → 새 자료가 들어왔을 수 있다 (F4-R05)
  useEffect(() => {
    if (seen.current !== undefined && stamp !== seen.current) void Promise.resolve().then(load);
  }, [stamp, load]);

  const rescan = useCallback(
    async (force = false) => {
      setBusy(true);
      try {
        const d = await api.rescanMaterials(force);
        setData(courseId || kind ? await api.materials({ course: courseId, kind }) : d);
        seen.current = d.updatedAt;
        const s = d.scan;
        toast(
          s && (s.new || s.changed || s.removed)
            ? `자료 ${s.files}개 — 새로 ${s.new} · 바뀜 ${s.changed} · 사라짐 ${s.removed}`
            : `자료 ${d.totals.files}개 — 바뀐 것이 없습니다`,
        );
      } catch (e) {
        toast(`다시 훑지 못했습니다: ${msg(e)}`, { tone: "error" });
      } finally {
        setBusy(false);
      }
    },
    [courseId, kind, toast],
  );

  const upload = useCallback(
    async (files: Iterable<File>) => {
      const list = [...files];
      if (!courseId || !list.length) return [];
      setBusy(true);
      const added: MaterialItem[] = [];
      try {
        for (const f of list) {
          try {
            added.push(await api.uploadMaterial(courseId, f)); // 한 번에 하나씩 — 실패한 파일만 짚어 준다
          } catch (e) {
            toast(`${f.name} — ${msg(e)}`, { tone: "error" });
          }
        }
        if (added.length) {
          await load();
          toast(`${added.length}개 자료를 추가했습니다`, { tone: "success" });
        }
      } finally {
        setBusy(false);
      }
      return added;
    },
    [courseId, load, toast],
  );

  const remove = useCallback(
    async (m: MaterialItem) => {
      setBusy(true);
      try {
        await api.deleteMaterial(m.id);
        setData((d) => (d ? { ...d, materials: d.materials.filter((x) => x.id !== m.id) } : d));
        await load();
        toast(`${m.title} 을(를) 지웠습니다`);
        return true;
      } catch (e) {
        toast(`지우지 못했습니다: ${msg(e)}`, { tone: "error" });
        return false;
      } finally {
        setBusy(false);
      }
    },
    [load, toast],
  );

  return { data, loading, error, busy, reload: load, rescan, upload, remove };
}
