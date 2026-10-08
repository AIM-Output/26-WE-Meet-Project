"use client";

import { useCallback, useEffect, useState } from "react";
import { RotateCcw } from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { Banner, ErrorPanel, SkeletonList } from "@/components/ui/Feedback";
import { StackedBar } from "@/components/ui/Progress";
import { useToast } from "@/components/ui/Toast";
import { api } from "@/lib/api";
import type { ScopeMaterial, StudyMaterials } from "@/lib/exams";

// 자료 체크 (2026-10-06) — 서비스 밖(수업·혼자 공부)에서 공부한 강의자료를 체크한다.
// 체크는 과목 단위다(중간·기말에서 따로 하지 않는다). 체크한 쪽수는 카드의 공부 진도 그래프에 들어가고,
// 계획을 만들 때 남은 분량에서 빠진다. 이미 등록한 계획은 저절로 바뀌지 않는다 — 다시 만들기를 권한다.

const msg = (e: unknown) => (e instanceof Error ? e.message : String(e));

export function StudyMaterialsModal({
  examId,
  onClose,
  onChanged,
  onReplan,
}: {
  examId: string | null;
  onClose: () => void;
  /** 체크가 바뀌었다 — 목록 카드의 그래프를 다시 받는다 */
  onChanged: () => void;
  /** '계획 다시 만들기' — 그 시험의 계획 옵션으로 */
  onReplan: (examId: string) => void;
}) {
  return (
    <Modal open={!!examId} onClose={onClose} title="자료 체크" size="lg">
      {examId && <Body key={examId} examId={examId} onChanged={onChanged} onReplan={onReplan} />}
    </Modal>
  );
}

function Body({ examId, onChanged, onReplan }: { examId: string; onChanged: () => void; onReplan: (examId: string) => void }) {
  const toast = useToast();
  const [data, setData] = useState<StudyMaterials | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<Set<string>>(new Set());

  const load = useCallback(async () => {
    try {
      setData(await api.examMaterials(examId));
      setError(null);
    } catch (e) {
      setError(msg(e));
    }
  }, [examId]);

  useEffect(() => {
    void Promise.resolve().then(load);
  }, [load]);

  const toggle = async (ids: string[], done: boolean) => {
    if (!ids.length) return;
    setPending((p) => new Set([...p, ...ids]));
    try {
      const out = await api.patchExamMaterials(examId, ids, done);
      setData(out);
      if (out.changed) onChanged();
    } catch (e) {
      toast(`체크를 저장하지 못했습니다: ${msg(e)}`, { tone: "error" });
    } finally {
      setPending((p) => new Set([...p].filter((x) => !ids.includes(x))));
    }
  };

  if (error) return <ErrorPanel message={`자료를 불러오지 못했습니다: ${error}`} onRetry={() => void load()} />;
  if (!data) return <SkeletonList rows={5} />;

  const e = data.exam;
  const st = e.study;
  const unit = st?.unit === "files" ? "개" : "쪽";
  const undone = data.materials.filter((m) => !m.done).map((m) => m.id);
  const doneIds = data.materials.filter((m) => m.done).map((m) => m.id);

  return (
    <div className="space-y-4 pt-1 text-[14px]">
      <div>
        <p className="font-semibold">
          {e.course} {e.typeLabel} <span className="font-normal text-muted">· 범위 {e.scope.note || e.scope.label || "—"}</span>
        </p>
        <p className="mt-1 text-[13px] text-muted">
          수업이나 혼자 공부하면서 이미 본 자료를 체크하세요. 체크한 쪽수는 공부 진도에 들어가고, 계획을 만들 때 남은 분량에서 빠집니다.
        </p>
      </div>

      {st && st.total > 0 && (
        <div className="space-y-1.5 rounded-xl border border-border px-3 py-2.5">
          <StackedBar
            max={st.total}
            height={10}
            segments={[
              { value: st.checked, tone: "primary" },
              { value: st.planned, tone: "study" },
            ]}
            label="공부 진도"
          />
          <p className="num flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-muted">
            <span>
              공부 <b className="font-semibold text-text">{st.done}</b>/{st.total}
              {unit} ({st.percent}%)
            </span>
            <span className="inline-flex items-center gap-1">
              <i className="size-2 rounded-full bg-primary" aria-hidden />
              직접 체크 {st.checked}
              {unit}
            </span>
            {st.planned > 0 && (
              <span className="inline-flex items-center gap-1">
                <i className="size-2 rounded-full bg-study" aria-hidden />
                계획에서 완료 {st.planned}
                {unit}
              </span>
            )}
            <span>
              남은 {st.remaining}
              {unit}
            </span>
          </p>
        </div>
      )}

      {data.planStale && (
        <Banner
          tone="warn"
          action={
            <button type="button" className="btn btn-sm" onClick={() => onReplan(examId)}>
              <RotateCcw aria-hidden />
              계획 다시 만들기
            </button>
          }
        >
          {data.planStale.message}
        </Banner>
      )}

      {data.materials.length === 0 ? (
        <Banner tone="info">{data.available ? "범위 안에 강의자료가 없습니다." : data.note}</Banner>
      ) : (
        <section aria-label="범위 안 강의자료">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <h3 className="mr-auto text-[13px] font-semibold text-muted">
              범위 안 자료 {data.materials.length}개 · 체크 {doneIds.length}개
            </h3>
            <button type="button" className="btn btn-ghost btn-sm" disabled={!undone.length || pending.size > 0} onClick={() => void toggle(undone, true)}>
              모두 체크
            </button>
            <button type="button" className="btn btn-ghost btn-sm" disabled={!doneIds.length || pending.size > 0} onClick={() => void toggle(doneIds, false)}>
              모두 해제
            </button>
          </div>
          <MaterialList items={data.materials} pending={pending} onToggle={(m) => void toggle([m.id], !m.done)} />
        </section>
      )}

      {data.others.length > 0 && (
        <details className="rounded-xl border border-border px-3 py-2">
          <summary className="cursor-pointer text-[13px] font-semibold text-muted">
            범위 밖 자료 {data.others.length}개 — 체크는 과목에 남아 다른 시험에도 쓰입니다
          </summary>
          <div className="mt-2">
            <MaterialList items={data.others} pending={pending} onToggle={(m) => void toggle([m.id], !m.done)} />
          </div>
        </details>
      )}
    </div>
  );
}

function MaterialList({ items, pending, onToggle }: { items: ScopeMaterial[]; pending: Set<string>; onToggle: (m: ScopeMaterial) => void }) {
  return (
    <ul className="divide-y divide-border rounded-xl border border-border">
      {items.map((m) => (
        <li key={m.id}>
          <label className={`flex cursor-pointer items-center gap-3 px-3 py-2 ${m.done ? "bg-primary-soft/30" : ""}`}>
            <input
              type="checkbox"
              className="size-4 flex-none accent-[var(--primary)]"
              checked={!!m.done}
              disabled={pending.has(m.id)}
              onChange={() => onToggle(m)}
              aria-label={`${m.title} 공부 완료`}
            />
            <span className="num w-9 flex-none text-[12px] text-muted">{m.week ? `${m.week}주` : "—"}</span>
            <span className={`min-w-0 flex-1 truncate ${m.done ? "text-muted" : ""}`} title={m.title}>
              {m.title}
            </span>
            <span className={`num flex-none text-[13px] ${m.pages ? "text-muted" : "text-faint"}`}>{m.pages ? `${m.pages}쪽` : "쪽수 —"}</span>
          </label>
        </li>
      ))}
    </ul>
  );
}
