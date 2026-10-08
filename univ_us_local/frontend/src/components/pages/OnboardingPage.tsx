"use client";

import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import { ArrowLeft, ArrowRight, Check, Download, GraduationCap } from "lucide-react";
import { Page } from "@/components/ui/Layout";
import { Chip } from "@/components/ui/Chip";
import { useToast } from "@/components/ui/Toast";
import { DeptPicker } from "@/components/profile/DeptPicker";
import { ImportProblem } from "@/components/pages/SettingsPages";
import { useProfile, useProfileImport } from "@/lib/useProfile";
import { navigateQuery, useQueryParam } from "@/lib/useQueryState";
import { fmtGpa, TRACK_LABEL, type Track } from "@/lib/profile";

// /onboarding — 첫 설정 3단계: 학과 → 입학년도·이수유형 → 학사시스템에서 가져오기(선택). Frontend-Route 5-1.
// 단계 이동은 push(뒤로가기로 이전 단계), 2단계를 마치면 이미 쓸 수 있으므로 3단계는 언제든 건너뛴다.

const STEPS = ["1", "2", "3"] as const;
const LABELS = ["학과", "입학년도 · 이수유형", "가져오기"];

export default function OnboardingPage() {
  const router = useRouter();
  const toast = useToast();
  const { doc, profile: p, update, source } = useProfile();
  const imp = useProfileImport();
  const [step] = useQueryParam<(typeof STEPS)[number]>("step", "1", STEPS);
  const n = Number(step);
  const go = (s: number) => navigateQuery({ step: String(s) }, "push");
  const year = new Date().getFullYear();
  const imported = !!doc?.importedAt;

  const finish = async (msg: string) => {
    if (doc?.onboardingSkipped) await update({ onboardingSkipped: false });
    toast(msg, { tone: "success" });
    router.push("/");
  };

  return (
    <Page>
      <div className="mx-auto max-w-[640px]">
        <div className="mb-6 flex items-center gap-3">
          <span className="grid size-10 place-items-center rounded-xl bg-primary text-on-primary">
            <GraduationCap className="size-5" aria-hidden />
          </span>
          <div>
            <h1 className="text-[24px] font-bold tracking-tight">첫 설정</h1>
            <p className="text-[14px] text-muted">내 학과·입학년도에 맞는 학사일정과 졸업요건을 골라 드립니다</p>
          </div>
        </div>

        <ol className="mb-6 flex items-center gap-2" aria-label="진행 단계">
          {LABELS.map((l, i) => {
            const done = i + 1 < n;
            const on = i + 1 === n;
            return (
              <li key={l} className="flex flex-1 items-center gap-2" aria-current={on ? "step" : undefined}>
                <span
                  className={`num grid size-7 flex-none place-items-center rounded-full text-[13px] font-bold transition-colors ${
                    done ? "bg-primary text-on-primary" : on ? "bg-primary-soft text-primary ring-2 ring-primary" : "bg-surface-3 text-faint"
                  }`}
                >
                  {done ? <Check className="size-4" aria-hidden /> : i + 1}
                </span>
                <span className={`hidden text-[13px] font-semibold sm:inline ${on ? "text-text" : "text-faint"}`}>{l}</span>
                {i < 2 && <span className={`h-px flex-1 ${done ? "bg-primary" : "bg-border"}`} aria-hidden />}
              </li>
            );
          })}
        </ol>

        <div className="card overflow-hidden p-5 md:p-6">
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={step}
              initial={{ opacity: 0, x: 16 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -16 }}
              transition={{ type: "spring", bounce: 0, visualDuration: 0.22 }}
            >
              {n === 1 && (
                <section aria-labelledby="s1">
                  <h2 id="s1" className="mb-4 text-[18px] font-bold">
                    학과를 골라 주세요
                  </h2>
                  <DeptPicker value={p?.majorCode ?? p?.deptCode ?? null} onChange={(d) => void update({ affiliation: { deptCode: d.deptCode, majorCode: d.majorCode } })} />
                  {p?.deptPath && (
                    <p className="mt-3 text-[14px]">
                      선택: <b>{p.deptPath}</b>
                    </p>
                  )}
                </section>
              )}

              {n === 2 && (
                <section aria-labelledby="s2" className="space-y-5">
                  <h2 id="s2" className="text-[18px] font-bold">
                    입학년도와 이수유형
                  </h2>
                  <div>
                    <label htmlFor="adm" className="label">
                      입학년도
                    </label>
                    <select
                      id="adm"
                      className="field w-40"
                      value={p?.admissionYear ?? ""}
                      onChange={(e) => void update({ admissionYear: e.target.value ? Number(e.target.value) : null })}
                    >
                      <option value="">선택</option>
                      {Array.from({ length: 10 }, (_, i) => year - i).map((y) => (
                        <option key={y} value={y}>
                          {y}학년도
                        </option>
                      ))}
                    </select>
                  </div>
                  <fieldset>
                    <legend className="label">이수유형</legend>
                    <div className="grid grid-cols-3 gap-2" role="radiogroup">
                      {(Object.keys(TRACK_LABEL) as Track[]).map((t) => (
                        <button
                          key={t}
                          type="button"
                          role="radio"
                          aria-checked={p?.track === t}
                          onClick={() => void update({ track: t })}
                          className={`btn ${p?.track === t ? "border-primary bg-primary-soft text-primary hover:bg-primary-soft" : ""}`}
                        >
                          {TRACK_LABEL[t]}
                        </button>
                      ))}
                    </div>
                  </fieldset>
                  {p?.admissionYear && p.track && p.deptCode && (
                    <p className="rounded-xl bg-primary-soft px-4 py-3 text-[14px] text-primary">
                      졸업요건 기준이 <b>{p.admissionYear} {p.major ?? p.department}</b> 로 붙습니다. 이제 바로 쓸 수 있어요.
                    </p>
                  )}
                </section>
              )}

              {n === 3 && (
                <section aria-labelledby="s3" className="space-y-4">
                  <h2 id="s3" className="text-[18px] font-bold">
                    학사정보시스템에서 가져오기 <span className="text-[14px] font-medium text-faint">(선택)</span>
                  </h2>
                  <p className="text-[14px] text-muted">학년·학적·평점·이수학점을 이 PC 의 로그인 창으로 가져옵니다. 로그인 정보는 PC 밖으로 나가지 않습니다.</p>
                  <ImportProblem imp={imp} />
                  {imported && p ? (
                    <ul className="grid grid-cols-2 gap-2 text-[14px]">
                      {(
                        [
                          ["학년", "grade", p.grade ? `${p.grade}학년` : null],
                          ["학적", "enrollmentStatus", p.enrollmentStatus],
                          ["평점", "gpa", fmtGpa(p.gpa)],
                          ["취득학점", "earnedCredits", p.earnedCredits !== null ? `${p.earnedCredits}학점` : null],
                        ] as const
                      ).map(([label, key, v]) => (
                        <li key={key} className="flex items-center justify-between rounded-lg bg-surface-2 px-3 py-2">
                          <span className="text-muted">{label}</span>
                          <span className="flex items-center gap-2 font-semibold">
                            {v ?? <span className="font-normal text-faint">못 읽음</span>}
                            {source(key) === "auto" && (
                              <Chip tone="primary" square>
                                자동
                              </Chip>
                            )}
                          </span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <button type="button" className="btn btn-primary" disabled={imp.running} onClick={() => void imp.start()}>
                      {imp.running ? <span className="spin" aria-hidden /> : <Download aria-hidden />}
                      {imp.running ? "가져오는 중… (30초쯤)" : "학사정보시스템에서 가져오기"}
                    </button>
                  )}
                </section>
              )}
            </motion.div>
          </AnimatePresence>
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-2">
          {n > 1 ? (
            <button type="button" className="btn btn-ghost" onClick={() => navigateQuery({ step: String(n - 1) }, "replace")}>
              <ArrowLeft aria-hidden />
              이전
            </button>
          ) : (
            <button
              type="button"
              className="btn btn-ghost"
              onClick={async () => {
                await update({ onboardingSkipped: true });
                router.push("/");
              }}
            >
              나중에 하기
            </button>
          )}
          <div className="ml-auto flex gap-2">
            {n === 3 && (
              <button type="button" className="btn" onClick={() => void finish("설정을 마쳤습니다")}>
                건너뛰기
              </button>
            )}
            {n < 3 ? (
              <button
                type="button"
                className="btn btn-primary"
                disabled={(n === 1 && !p?.deptCode) || (n === 2 && (!p?.admissionYear || !p?.track))}
                onClick={() => go(n + 1)}
              >
                다음
                <ArrowRight aria-hidden />
              </button>
            ) : (
              imported && (
                <button type="button" className="btn btn-primary" onClick={() => void finish("설정을 마쳤습니다 — 이제 내 해당 일정만 골라 드립니다")}>
                  완료
                  <Check aria-hidden />
                </button>
              )
            )}
          </div>
        </div>
      </div>
    </Page>
  );
}
