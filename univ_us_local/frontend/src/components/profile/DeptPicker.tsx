"use client";

import { useMemo, useState } from "react";
import { Check, Search } from "lucide-react";
import { demoDepartments, deptPath, type Department } from "@/lib/demo";

// 학과 선택기 — 한 입력창에 '인공지능'을 치면 `단과대 › 학과 › 전공` 경로 후보가 뜬다(Frontend-Route 5-2).
// 같은 이름의 학과가 여러 단과대에 있으므로 경로를 늘 보여 준다.

export function DeptPicker({ value, onChange }: { value: string | null; onChange: (d: Department) => void }) {
  const [q, setQ] = useState("");
  const results = useMemo(() => {
    const t = q.trim().replace(/\s+/g, "");
    if (!t) return demoDepartments;
    return demoDepartments.filter((d) => deptPath(d).replace(/\s|›/g, "").includes(t));
  }, [q]);

  return (
    <div>
      <label htmlFor="dept-q" className="label">
        학과 검색
      </label>
      <div className="relative">
        <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-faint" aria-hidden />
        <input
          id="dept-q"
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
        {results.length === 0 ? (
          <li className="px-4 py-6 text-center text-[14px] text-faint">찾는 학과가 없습니다 — 다른 낱말로 검색해 보세요</li>
        ) : (
          results.map((d) => {
            const on = d.code === value;
            return (
              <li key={d.code} role="option" aria-selected={on} className="border-b border-border last:border-b-0">
                <button
                  type="button"
                  onClick={() => onChange(d)}
                  className={`flex w-full items-center gap-3 px-4 py-2.5 text-left text-[14px] transition-colors ${on ? "bg-primary-soft" : "hover:bg-surface-2"}`}
                >
                  <span className="min-w-0 flex-1">
                    <span className="text-faint">{d.college} › </span>
                    <span className="font-semibold">{d.dept}</span>
                    {d.major && <span className="text-muted"> › {d.major}</span>}
                  </span>
                  {on && <Check className="size-4 flex-none text-primary" aria-hidden />}
                </button>
              </li>
            );
          })
        )}
      </ul>
      <p className="hint">예시 목록 {demoDepartments.length}개 · 실제는 교육과정검색에서 61개 단과대를 내려받습니다(학과 목록 갱신).</p>
    </div>
  );
}
