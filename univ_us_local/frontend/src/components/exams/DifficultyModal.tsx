"use client";

import { useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Banner } from "@/components/ui/Feedback";
import type { Difficulty } from "@/lib/exams";

// 난이도 시간 설정 (2026-10-02) — 난이도별로 한 쪽을 공부하는 데 몇 분이 드는지.
// 기본 쉬움 1 · 보통 1.5 · 어려움 2분. 저장하면 앞으로 만드는 계획에 쓰인다(이미 등록한 계획은 그대로).

type Row = { key: Difficulty; label: string; pageMinutes: number; defaultMinutes?: number };

export function DifficultyModal({
  open,
  rows,
  busy,
  onClose,
  onSave,
}: {
  open: boolean;
  rows: Row[];
  busy?: boolean;
  onClose: () => void;
  onSave: (values: Partial<Record<Difficulty, number | null>>) => Promise<boolean>;
}) {
  return (
    <Modal open={open} onClose={onClose} title="난이도 시간 설정">
      {/* 열 때마다 저장된 값으로 새로 잡는다 — key 로 다시 마운트 */}
      <Body key={rows.map((r) => `${r.key}:${r.pageMinutes}`).join("|")} rows={rows} busy={busy} onClose={onClose} onSave={onSave} />
    </Modal>
  );
}

function Body({
  rows,
  busy,
  onClose,
  onSave,
}: {
  rows: Row[];
  busy?: boolean;
  onClose: () => void;
  onSave: (values: Partial<Record<Difficulty, number | null>>) => Promise<boolean>;
}) {
  const [values, setValues] = useState<Record<string, string>>(() => Object.fromEntries(rows.map((r) => [r.key, String(r.pageMinutes)])));
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const out: Partial<Record<Difficulty, number | null>> = {};
    for (const r of rows) {
      const n = Number(values[r.key]);
      if (!Number.isFinite(n) || n < 0.1 || n > 30) {
        setError(`${r.label}: 쪽당 0.1~30분 사이로 넣어 주세요`);
        return;
      }
      out[r.key] = n;
    }
    if (await onSave(out)) onClose();
  };

  return (
    <form noValidate className="space-y-4 pt-1 text-[14px]" onSubmit={(e) => void submit(e)}>
      <p className="text-muted">한 쪽을 공부하는 데 걸리는 시간입니다. 계획을 만들 때 고른 난이도의 값으로 하루 공부 시간을 셉니다.</p>
      {error && <Banner tone="danger">{error}</Banner>}
      <div className="grid gap-3 sm:grid-cols-3">
        {rows.map((r) => (
          <div key={r.key}>
            <label className="label" htmlFor={`diff-${r.key}`}>
              {r.label}
            </label>
            <div className="flex items-center gap-2">
              <input
                id={`diff-${r.key}`}
                type="number"
                min={0.5}
                max={30}
                // 위아래 버튼은 0.5분씩. 0.5 단위가 아닌 값(1.25 등)도 받는다 — 폼의 noValidate 로 브라우저 검사를 끄고
                // submit 이 0.1~30 범위만 본다(브라우저 검사는 단위가 안 맞으면 저장을 조용히 막았다)
                step={0.5}
                className="field num"
                value={values[r.key] ?? ""}
                onChange={(e) => setValues((v) => ({ ...v, [r.key]: e.target.value }))}
              />
              <span className="flex-none text-muted">분/쪽</span>
            </div>
            {r.defaultMinutes !== undefined && <p className="mt-1 text-[12px] text-faint">기본 {r.defaultMinutes}분</p>}
          </div>
        ))}
      </div>
      <p className="hint">이미 등록한 계획은 바뀌지 않습니다 — 다시 계산하려면 그 시험의 계획을 다시 만드세요.</p>
      <div className="flex flex-wrap justify-end gap-2 border-t border-border pt-4">
        <button
          type="button"
          className="btn btn-ghost mr-auto"
          disabled={busy}
          onClick={() => setValues(Object.fromEntries(rows.map((r) => [r.key, String(r.defaultMinutes ?? r.pageMinutes)])))}
        >
          기본값으로
        </button>
        <button type="button" className="btn" onClick={onClose} disabled={busy}>
          취소
        </button>
        <button type="submit" className="btn btn-primary" disabled={busy}>
          저장
        </button>
      </div>
    </form>
  );
}
