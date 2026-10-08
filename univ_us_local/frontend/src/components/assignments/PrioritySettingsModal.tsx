"use client";

import { useEffect, useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Banner } from "@/components/ui/Feedback";
import { api } from "@/lib/api";
import { fmtHours } from "@/lib/dates";
import type { PrioritySettingsView, TaskKind } from "@/lib/priority";

// 우선순위 설정 (F7-R05 · S08) — 안전계수 · 유형별 기본 소요시간 · 취침 시각.
// 값은 서버(F7_Task_agent/data/settings.json)에 저장되고, 기본값과 같은 값은 서버가 저장하지 않는다
// (그래야 나중에 기본값을 고치면 손대지 않은 사람에게 그대로 간다).

// 취침 시각 — 18:00 ~ 다음 날 05:00, 30분 단위. 24:00 = 자정, 01:30 = 새벽 1시 반 (서버 규칙과 같다)
const BED_CHOICES = (() => {
  const out: { value: string; label: string }[] = [];
  for (let m = 18 * 60; m <= 29 * 60; m += 30) {
    const mm = m % 60 ? "30" : "00";
    if (m === 24 * 60) out.push({ value: "24:00", label: "24:00 (자정)" });
    else if (m > 24 * 60) {
      const hh = Math.floor((m - 24 * 60) / 60);
      out.push({ value: `${String(hh).padStart(2, "0")}:${mm}`, label: `새벽 ${hh}:${mm}` });
    } else out.push({ value: `${Math.floor(m / 60)}:${mm}`, label: `${Math.floor(m / 60)}:${mm}` });
  }
  return out;
})();

/** 칸에 넣는 숫자 — 소수 둘째 자리까지 (동영상 기본 50분 = 0.8333…시간 → 0.83, 서버는 이 값을 기본값으로 본다) */
const num = (x: number) => String(Math.round(x * 100) / 100);

export function PrioritySettingsModal({ open, onClose, onSaved }: { open: boolean; onClose: () => void; onSaved: () => void }) {
  return (
    <Modal open={open} onClose={onClose} title="우선순위 설정">
      {open && <Loader onClose={onClose} onSaved={onSaved} />}
    </Modal>
  );
}

function Loader({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [view, setView] = useState<PrioritySettingsView | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    void Promise.resolve()
      .then(() => api.prioritySettings())
      .then(setView)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, []);
  if (error) return <Banner tone="danger">설정을 불러오지 못했습니다: {error}</Banner>;
  if (!view) return <p className="py-6 text-center text-[14px] text-muted">불러오는 중…</p>;
  return <Form view={view} onClose={onClose} onSaved={onSaved} />;
}

function Form({ view, onClose, onSaved }: { view: PrioritySettingsView; onClose: () => void; onSaved: () => void }) {
  const [safety, setSafety] = useState(num(view.safetyFactor));
  const [hours, setHours] = useState<Record<string, string>>(() => Object.fromEntries(view.kinds.map((k) => [k.key, num(view.defaultHours[k.key])])));
  const [bed, setBed] = useState(view.bedTime);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [sLo, sHi] = view.limits.safetyFactor;
  const [hLo, hHi] = view.limits.defaultHours;
  const bedChoices = BED_CHOICES.some((c) => c.value === bed) ? BED_CHOICES : [{ value: bed, label: bed }, ...BED_CHOICES];

  const toDefaults = () => {
    setSafety(num(view.defaults.safetyFactor));
    setHours(Object.fromEntries(view.kinds.map((k) => [k.key, num(view.defaults.defaultHours[k.key])])));
    setBed(view.defaults.bedTime);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const sf = Number(safety);
    if (!Number.isFinite(sf) || sf < sLo || sf > sHi) return setError(`안전계수는 ${sLo} ~ ${sHi} 사이로 넣어 주세요`);
    const dh: Partial<Record<TaskKind, number>> = {};
    for (const k of view.kinds) {
      const n = Number(hours[k.key]);
      if (!Number.isFinite(n) || n < hLo || n > hHi) return setError(`${k.label}: ${hLo} ~ ${hHi}시간 사이로 넣어 주세요`);
      dh[k.key] = n;
    }
    setBusy(true);
    try {
      await api.patchPrioritySettings({ safetyFactor: sf, defaultHours: dh, bedTime: bed });
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form noValidate className="space-y-5 pt-1 text-[14px]" onSubmit={(e) => void submit(e)}>
      {error && <Banner tone="danger">{error}</Banner>}

      <div>
        <label className="label" htmlFor="prio-safety">
          안전계수
        </label>
        <div className="flex items-center gap-2">
          <input id="prio-safety" type="number" min={sLo} max={sHi} step={0.1} className="field num w-[110px]" value={safety} onChange={(e) => setSafety(e.target.value)} />
          <span className="text-muted">배</span>
        </div>
        <p className="hint mt-1">
          사람은 예상보다 오래 걸립니다. 필요 시간 = 예상 소요시간 × 안전계수 (기본 {view.defaults.safetyFactor.toFixed(1)}). 예: 3시간 과제는 {fmtHours(3 * (Number(safety) || view.safetyFactor))} 필요로 셉니다.
        </p>
      </div>

      <div>
        <p className="label">유형별 기본 소요시간</p>
        <div className="grid gap-3 sm:grid-cols-4">
          {view.kinds.map((k) => (
            <div key={k.key}>
              <label className="mb-1 block text-[13px] text-muted" htmlFor={`prio-h-${k.key}`}>
                {k.label}
              </label>
              <div className="flex items-center gap-1.5">
                <input
                  id={`prio-h-${k.key}`}
                  type="number"
                  min={hLo}
                  max={hHi}
                  // 위아래 버튼은 0.25시간씩. 단계는 min(0.25) 기준으로 잡히므로 0.5 로 두면 첫 번만 0.25(격자 맞추기), 그 뒤 0.5 씩 움직였다.
                  // noValidate 로 브라우저 검사를 끄고 submit 이 범위만 본다
                  step={0.25}
                  className="field num"
                  value={hours[k.key] ?? ""}
                  onChange={(e) => setHours((v) => ({ ...v, [k.key]: e.target.value }))}
                />
                <span className="flex-none text-muted">시간</span>
              </div>
              <p className="mt-1 text-[12px] text-faint">기본 {fmtHours(view.defaults.defaultHours[k.key])}</p>
            </div>
          ))}
        </div>
        <p className="hint mt-1">과제마다 직접 고친 시간은 그대로 둡니다 — 고치지 않은 과제에만 쓰입니다.</p>
      </div>

      <div>
        <label className="label" htmlFor="prio-bed">
          취침 시각
        </label>
        <select id="prio-bed" className="field w-auto" value={bed} onChange={(e) => setBed(e.target.value)}>
          {bedChoices.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </select>
        <p className="hint mt-1">오늘 남은 시간 = 취침 시각 − 지금 − 오늘 남은 수업·일정 − 오늘 공부 분량</p>
      </div>

      <div className="flex flex-wrap justify-end gap-2 border-t border-border pt-4">
        <button type="button" className="btn btn-ghost mr-auto" disabled={busy} onClick={toDefaults}>
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
