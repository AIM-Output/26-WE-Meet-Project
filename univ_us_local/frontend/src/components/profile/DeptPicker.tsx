"use client";

import { useMemo, useState } from "react";
import { Check, RefreshCw, Search } from "lucide-react";
import { useDepartments } from "@/lib/useProfile";
import type { DeptEntry } from "@/lib/profile";
import { fmtShortStamp } from "@/lib/dates";

// 학과 선택기 — 한 입력창에 '인공지능'을 치면 `단과대 › 학과 › 전공` 경로 후보가 뜬다(Frontend-Route 5-2).
// 목록은 교육과정검색에서 받은 학과 마스터(C2_Profile_agent) — 같은 이름의 학과가 여러 단과대에 있어 경로를 늘 보여 준다.
// 고르면 코드로 저장된다(자유 입력 금지, C2-D1).

const MAX_SHOWN = 80;
const squash = (s: string) => s.replace(/[\s›·]/g, "").toLowerCase();

export function DeptPicker({ value, onChange }: { value: string | null; onChange: (d: DeptEntry) => void }) {
  const { data, entries, error, syncing, sync, reload } = useDepartments();
  const [q, setQ] = useState("");
  const results = useMemo(() => {
    const t = squash(q.trim());
    const live = entries.filter((e) => !e.retired || e.code === value);
    const hit = t ? entries.filter((e) => squash(e.path).includes(t)) : live;
    return hit;
  }, [q, entries, value]);
  const shown = results.slice(0, MAX_SHOWN);

  return (
    <div>
      <label htmlFor="dept-q" className="label">
        학과 검색
      </label>
      <div className="relative">
        <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-faint" aria-hidden />
        <input
          id="dept-q"
          data-autofocus
          className="field pl-9"
          placeholder="예) 인공지능, 컴퓨터, 경영"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          role="combobox"
          aria-expanded
          aria-controls="dept-list"
          aria-autocomplete="list"
        />
      </div>
      <ul id="dept-list" role="listbox" aria-label="학과 후보" className="thin-scroll mt-2 max-h-[300px] overflow-y-auto rounded-xl border border-border">
        {error && !data ? (
          <li className="flex flex-col items-center gap-2 px-4 py-6 text-center text-[14px] text-danger-text">
            학과 목록을 불러오지 못했습니다
            <button type="button" className="btn btn-sm" onClick={() => void reload()}>
              다시 시도
            </button>
          </li>
        ) : !data ? (
          Array.from({ length: 5 }, (_, i) => (
            <li key={i} className="border-b border-border px-4 py-3 last:border-b-0">
              <span className="block h-3.5 w-2/3 animate-pulse rounded bg-surface-3" />
            </li>
          ))
        ) : shown.length === 0 ? (
          <li className="px-4 py-6 text-center text-[14px] text-faint">찾는 학과가 없습니다 — 다른 낱말로 검색하거나 아래에서 목록을 갱신해 보세요</li>
        ) : (
          shown.map((d) => {
            const on = d.code === value;
            return (
              <li key={d.code} role="option" aria-selected={on} className="border-b border-border last:border-b-0">
                <button
                  type="button"
                  onClick={() => onChange(d)}
                  className={`flex w-full items-center gap-3 px-4 py-2.5 text-left text-[14px] transition-colors ${on ? "bg-primary-soft" : "hover:bg-surface-2"}`}
                >
                  <span className={`min-w-0 flex-1 ${d.retired ? "opacity-60" : ""}`}>
                    <span className="text-faint">{d.college} › </span>
                    <span className="font-semibold">{d.department}</span>
                    {d.major && <span className="text-muted"> › {d.major}</span>}
                    {d.note && <span className="ml-1.5 text-[12px] text-faint">({d.note})</span>}
                    {d.retired && <span className="ml-1.5 text-[12px] text-warn-text">(개편·폐지)</span>}
                  </span>
                  {on && <Check className="size-4 flex-none text-primary" aria-hidden />}
                </button>
              </li>
            );
          })
        )}
      </ul>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <p className="text-[13px] text-faint">
          {data
            ? `${data.year ?? "?"}학년도 교육과정검색 기준 ${entries.length}곳${results.length > MAX_SHOWN ? ` · ${results.length}곳 중 ${MAX_SHOWN}곳 표시 — 검색어를 더 적어 주세요` : ""} · ${data.source === "local" ? `${fmtShortStamp(data.updatedAt)} 갱신` : "기본 목록"}`
            : "학과 목록을 불러오는 중…"}
        </p>
        <button type="button" className="btn btn-ghost btn-sm" disabled={syncing} onClick={() => void sync()}>
          <RefreshCw className={syncing ? "animate-spin" : ""} aria-hidden />
          {syncing ? "받는 중… (1분쯤)" : "학과 목록 갱신"}
        </button>
      </div>
    </div>
  );
}
