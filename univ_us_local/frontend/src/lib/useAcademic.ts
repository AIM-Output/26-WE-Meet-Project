"use client";

import { useAppData } from "@/components/app/AppData";

// F1 학사일정 — GET /api/academic/events 한 번을 모든 화면이 나눠 쓴다(AppDataProvider). 탭 전환은 화면에서 거른다.
export function useAcademic() {
  const { academic, academicError, academicSyncing, updateAcademic, refreshAcademic, startAcademicSync, status } = useAppData();
  return {
    data: academic,
    list: academic?.items ?? [],
    loading: academic === null && !academicError,
    error: academicError,
    update: updateAcademic,
    refresh: refreshAcademic,
    sync: startAcademicSync,
    syncing: academicSyncing,
    reviewCount: status?.academic?.reviewCount ?? 0,
    status: status?.academic ?? null,
  };
}
