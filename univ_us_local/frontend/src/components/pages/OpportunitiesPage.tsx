"use client";

import { useMemo, useState } from "react";
import { Bookmark, BookmarkCheck, CalendarPlus, ChevronDown, Copy, ExternalLink, Gift, ListTodo, Settings2, ShieldAlert, Sparkles, X } from "lucide-react";
import { Page, PageHeader, Section, Group } from "@/components/ui/Layout";
import { Tabs } from "@/components/ui/Tabs";
import { Banner, DemoNotice, EmptyState } from "@/components/ui/Feedback";
import { Chip, DdayChip, StatusBadge, type Tone } from "@/components/ui/Chip";
import { Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { closeQuery, navigateQuery, useQueryParam, useQueryValue } from "@/lib/useQueryState";
import { useIsXl } from "@/lib/useMediaQuery";
import { demoDraft, demoHistory, demoOpportunities, INTEREST_TAGS, type Grade, type Opportunity, type OppTab, type Verdict } from "@/lib/demo";
import { parseLocal } from "@/lib/dates";

// /opportunities — 장학 / 대외활동 / 사업단 / 이력 (Frontend-Route 16·17절).
// 돈이 걸린 유일한 화면: 판정 근거와 "제출은 본인이 한다"는 사실이 한순간도 흐려지면 안 된다.

const TABS = ["scholarship", "activity", "program", "history"] as const;
const VIEWS = ["match", "draft", "apply"] as const;
const VERDICT_TONE: Record<Verdict, Tone> = { 해당: "ok", "확인 필요": "warn", 비해당: "neutral", 마감: "neutral" };
const GRADE_TONE: Record<Grade, Tone> = { 맞음: "ok", "관련 있음": "info", 아님: "neutral" };

export default function OpportunitiesPage() {
  const [tab] = useQueryParam<OppTab>("tab", "scholarship", TABS);
  const [show, setShow] = useQueryParam("show", "", ["", "all"] as const);
  const [saved, setSaved] = useQueryParam("saved", "", ["", "1"] as const);
  const itemId = useQueryValue("item");
  const isXl = useIsXl();
  const [items, setItems] = useState<Opportunity[]>(demoOpportunities);
  const [interestsOpen, setInterestsOpen] = useState(false);
  const item = items.find((o) => o.id === itemId) ?? null;

  const inTab = items.filter((o) => o.tab === tab && (!saved || o.saved));
  const patch = (id: string, p: Partial<Opportunity>) => setItems((xs) => xs.map((x) => (x.id === id ? { ...x, ...p } : x)));

  const groups = useMemo(() => {
    if (tab === "scholarship")
      return [
        { key: "해당", items: inTab.filter((o) => o.verdict === "해당"), dot: "var(--ok)", fold: false },
        { key: "확인 필요", items: inTab.filter((o) => o.verdict === "확인 필요"), dot: "var(--warn)", fold: false },
        { key: "비해당·마감", items: inTab.filter((o) => o.verdict === "비해당" || o.verdict === "마감"), dot: "var(--border-strong)", fold: true },
      ];
    return [
      { key: "맞음", items: inTab.filter((o) => o.grade === "맞음"), dot: "var(--ok)", fold: false },
      { key: "관련 있음", items: inTab.filter((o) => o.grade === "관련 있음"), dot: "var(--info)", fold: false },
      { key: "아님", items: inTab.filter((o) => o.grade === "아님"), dot: "var(--border-strong)", fold: true },
    ];
  }, [tab, inTab]);

  const list = (
    <div>
      {groups.map((g) =>
        g.fold && show !== "all" ? (
          g.items.length > 0 && (
            <button key={g.key} type="button" className="btn btn-ghost btn-sm mb-4" onClick={() => setShow("all")}>
              + {g.key} {g.items.length}건 더보기
              <ChevronDown aria-hidden />
            </button>
          )
        ) : g.items.length === 0 && g.fold ? null : (
          <Group key={g.key} title={g.key} count={g.items.length} dot={g.dot}>
            {g.items.length === 0 ? (
              <p className="rounded-xl border border-dashed border-border-strong px-4 py-3 text-[14px] text-muted">
                {tab === "scholarship" ? "지금 해당하는 장학이 없습니다" : "지금 관심사에 맞는 기회가 없습니다"}
              </p>
            ) : (
              <ul className="overflow-hidden rounded-xl border border-border bg-surface">
                {g.items.map((o) => (
                  <li key={o.id} className="border-b border-border last:border-b-0">
                    <button
                      type="button"
                      onClick={() => navigateQuery({ item: o.id, view: null }, "push")}
                      className={`flex w-full flex-wrap items-center gap-x-3 gap-y-1.5 px-4 py-3 text-left transition-colors hover:bg-surface-2 ${o.id === itemId ? "bg-primary-soft" : ""} ${o.verdict === "마감" ? "opacity-60" : ""}`}
                    >
                      <span className="min-w-0 flex-1 basis-[55%]">
                        <span className={`block truncate text-[15px] font-semibold ${o.verdict === "마감" ? "line-through" : ""}`}>{o.title}</span>
                        <span className="text-[13px] text-muted">
                          {o.org}
                          {o.amount && ` · ${o.amount}`}
                        </span>
                      </span>
                      <span className="flex flex-wrap items-center gap-1.5">
                        {o.reasonChips?.map((r) => (
                          <Chip key={r} tone={r === "LLM 판단" ? "neutral" : "primary"} square>
                            {r}
                          </Chip>
                        ))}
                        {o.unknownReason && <Chip tone="warn" square>{o.unknownReason}</Chip>}
                        {o.progress && <Chip tone="info">{o.progress}</Chip>}
                        {o.flipped && <Chip tone="accent">내가 바꿈</Chip>}
                        {o.saved && <BookmarkCheck className="size-4 text-primary" aria-label="담음" />}
                        <DdayChip date={parseLocal(o.deadline)} />
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Group>
        ),
      )}
    </div>
  );

  return (
    <Page wide>
      <PageHeader
        icon={<Gift />}
        title="기회"
        meta={<span className="num">수집: 오늘 06:00 · 카탈로그 9/21</span>}
        actions={
          tab !== "scholarship" &&
          tab !== "history" && (
            <>
              <button type="button" className="btn btn-sm" onClick={() => setInterestsOpen(true)}>
                <Settings2 aria-hidden />
                관심사 설정
              </button>
              <button type="button" aria-pressed={!!saved} className={`btn btn-sm ${saved ? "border-primary bg-primary-soft text-primary" : ""}`} onClick={() => setSaved(saved ? null : "1")}>
                <Bookmark aria-hidden />
                담은 것만
              </button>
            </>
          )
        }
      />
      <div className="mb-5">
        <DemoNotice what="장학·기회 매칭" />
      </div>
      <Tabs
        className="mb-5"
        label="기회 분류"
        value={tab}
        onChange={(t) => navigateQuery({ tab: t === "scholarship" ? null : t, item: null, view: null, show: null }, "replace")}
        items={[
          { key: "scholarship", label: "장학", count: items.filter((o) => o.tab === "scholarship" && o.verdict === "해당").length },
          { key: "activity", label: "대외활동" },
          { key: "program", label: "사업단" },
          { key: "history", label: "이력" },
        ]}
      />

      {tab === "history" ? (
        <Section title={demoHistory.summary}>
          <ul className="divide-y divide-border">
            {demoHistory.items.map((h) => (
              <li key={h.title} className="flex items-center gap-3 py-3 text-[14px]">
                <span className="flex-1 font-medium">{h.title}</span>
                {h.amount && <span className="num text-muted">{h.amount}</span>}
                <StatusBadge tone={h.state === "선정" ? "ok" : h.state === "탈락" ? "danger" : "neutral"}>{h.state}</StatusBadge>
                {h.state === "관심 없음" && <button type="button" className="btn btn-ghost btn-sm">되돌리기</button>}
              </li>
            ))}
          </ul>
        </Section>
      ) : inTab.length === 0 ? (
        <EmptyState icon={<Gift />} title={saved ? "담아 둔 기회가 없습니다" : "아직 수집한 공지가 없습니다"} />
      ) : (
        <div className={`grid gap-5 ${item && isXl ? "grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]" : ""}`}>
          {list}
          {item && isXl && (
            <aside className="sticky top-[calc(var(--header-h)+16px)] h-fit">
              <Detail o={item} patch={patch} />
            </aside>
          )}
        </div>
      )}

      <Modal open={!!item && !isXl} onClose={() => closeQuery(["item", "view"])} title={item?.title} size="lg">
        {item && <Detail o={item} patch={patch} bare />}
      </Modal>
      <InterestsModal open={interestsOpen} onClose={() => setInterestsOpen(false)} />
    </Page>
  );
}

function Detail({ o, patch, bare }: { o: Opportunity; patch: (id: string, p: Partial<Opportunity>) => void; bare?: boolean }) {
  const toast = useToast();
  const [view, setView] = useQueryParam("view", "match", VIEWS);
  const scholarship = o.tab === "scholarship";

  const body = (
    <div className="space-y-4">
      <p className="flex flex-wrap items-center gap-2 text-[14px] text-muted">
        {o.org}
        {o.amount && ` · ${o.amount}`} · 신청 ~{o.deadline.slice(5).replace("-", "/")} <DdayChip date={parseLocal(o.deadline)} />
        {o.verdict && <StatusBadge tone={VERDICT_TONE[o.verdict]}>{o.verdict}</StatusBadge>}
        {o.grade && <StatusBadge tone={GRADE_TONE[o.grade]}>{o.grade}</StatusBadge>}
        <a href={o.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 font-semibold text-primary hover:underline">
          원문
          <ExternalLink className="size-3.5" aria-hidden />
        </a>
      </p>
      {scholarship && (
        <Tabs
          variant="pill"
          size="sm"
          label="상세 단계"
          value={view}
          onChange={(v) => setView(v)}
          items={[
            { key: "match", label: "판정" },
            { key: "draft", label: "초안" },
            { key: "apply", label: "제출 준비" },
          ]}
        />
      )}

      {(!scholarship || view === "match") && (
        <>
          {o.match ? (
            <div className="overflow-x-auto rounded-xl border border-border">
              <table className="w-full min-w-[520px] text-[14px]">
                <thead className="bg-surface-2 text-left text-[12px] text-muted">
                  <tr>
                    <th className="px-3 py-2 font-semibold">조건</th>
                    <th className="px-3 py-2 font-semibold">내 값</th>
                    <th className="px-3 py-2 font-semibold">판정</th>
                    <th className="px-3 py-2 font-semibold">근거</th>
                  </tr>
                </thead>
                <tbody>
                  {o.match.map((m) => (
                    <FragmentRow key={m.condition} m={m} onSave={() => toast("저장했습니다 — 관련 공지를 다시 판정합니다 (예시)", { tone: "success" })} />
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Banner tone="neutral">
              {o.reasonChips?.includes("LLM 판단") ? "관심사 키워드로는 판단이 애매해 LLM 이 판단했습니다." : `걸린 관심사: ${o.reasonChips?.join(", ") ?? "—"}`}
            </Banner>
          )}
          {o.otherConditions && (
            <p className="text-[13px] text-muted">
              기타 조건 &ldquo;{o.otherConditions.join(", ")}&rdquo; <span className="text-faint">(자동 판정하지 않음)</span>
            </p>
          )}
          <div className="flex flex-wrap justify-end gap-2 border-t border-border pt-3">
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => {
                patch(o.id, { progress: "관심 없음" });
                toast("숨겼습니다 — 이력 탭에서 되돌릴 수 있습니다");
              }}
            >
              관심 없음
            </button>
            {scholarship ? (
              <>
                {o.verdict !== "해당" && (
                  <button
                    type="button"
                    className="btn btn-sm"
                    onClick={() => {
                      patch(o.id, { verdict: "해당", flipped: true });
                      toast("해당으로 표시했습니다", { action: { label: "되돌리기", onClick: () => patch(o.id, { verdict: o.verdict, flipped: false }) } });
                    }}
                  >
                    해당으로 표시
                  </button>
                )}
                <button type="button" className="btn btn-primary btn-sm" onClick={() => setView("draft")}>
                  <Sparkles aria-hidden />
                  초안 만들기
                </button>
              </>
            ) : (
              <button type="button" className="btn btn-primary btn-sm" onClick={() => patch(o.id, { saved: !o.saved })}>
                {o.saved ? <BookmarkCheck aria-hidden /> : <Bookmark aria-hidden />}
                {o.saved ? "담음" : "담기"}
              </button>
            )}
          </div>
        </>
      )}

      {scholarship && view === "draft" && <DraftEditor />}
      {scholarship && view === "apply" && <ApplyPanel o={o} patch={patch} />}
    </div>
  );

  if (bare) return body;
  return (
    <Section
      title={o.title}
      action={
        <button type="button" className="btn btn-ghost btn-icon btn-sm" aria-label="상세 닫기" onClick={() => closeQuery(["item", "view"])}>
          <X aria-hidden />
        </button>
      }
    >
      {body}
    </Section>
  );
}

function FragmentRow({ m, onSave }: { m: NonNullable<Opportunity["match"]>[number]; onSave: () => void }) {
  const [skip, setSkip] = useState(false);
  const tone: Tone = m.result === "충족" ? "ok" : m.result === "미달" ? "danger" : "warn";
  return (
    <>
      <tr className="border-t border-border first:border-t-0">
        <td className="px-3 py-2.5 font-medium">{m.condition}</td>
        <td className="num px-3 py-2.5">{m.mine ?? <span className="text-faint">—</span>}</td>
        <td className="px-3 py-2.5">
          <StatusBadge tone={tone} unknown={m.result === "모름"}>
            {m.result}
          </StatusBadge>
        </td>
        <td className="px-3 py-2.5 text-[13px] text-muted">
          &ldquo;{m.quote}&rdquo;{m.page && <span className="text-faint"> ({m.page})</span>}
        </td>
      </tr>
      {m.result === "모름" && m.sensitive && !skip && (
        <tr className="bg-warn-soft/40">
          <td colSpan={4} className="px-3 py-3">
            <p className="mb-2 flex items-center gap-1.5 text-[13px] text-warn-text">
              <ShieldAlert className="size-4" aria-hidden />
              {m.sensitive === "income" ? "소득구간" : m.sensitive === "region" ? "거주지역" : "출신고교"}을 넣으면 판정해 드립니다. 이 조건 확인에만 쓰고 PC 밖으로 나가지 않습니다.
            </p>
            <div className="flex flex-wrap gap-2">
              <select className="field field-sm w-auto" aria-label="값">
                {m.sensitive === "income" ? Array.from({ length: 10 }, (_, i) => <option key={i}>{i + 1}구간</option>) : <option>광주광역시</option>}
              </select>
              <button type="button" className="btn btn-primary btn-sm" onClick={onSave}>
                저장
              </button>
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setSkip(true)}>
                건너뛰기
              </button>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function DraftEditor() {
  const [text, setText] = useState(demoDraft);
  const blanks = (text.match(/\{\{[^}]+\}\}/g) ?? []).length;
  const parts = text.split(/(\{\{[^}]+\}\})/g);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Chip tone={blanks ? "warn" : "ok"}>채워야 할 곳 {blanks}</Chip>
        <button type="button" className="btn btn-ghost btn-sm ml-auto">
          이전 초안 가져오기
        </button>
      </div>
      <div className="rounded-xl border border-border bg-surface-2 p-3 text-[14px] leading-relaxed whitespace-pre-wrap" aria-label="빈칸 미리보기">
        {parts.map((p, i) =>
          p.startsWith("{{") ? (
            <mark key={i} className="rounded bg-blank px-1 text-text">
              {p}
            </mark>
          ) : (
            <span key={i}>{p}</span>
          ),
        )}
      </div>
      <label htmlFor="draft" className="label">
        편집
      </label>
      <textarea id="draft" className="field min-h-[240px] font-mono text-[13px]" value={text} onChange={(e) => setText(e.target.value)} />
      <p className="text-[12px] text-faint">템플릿만(LLM 미설정) · 이름·학번은 채우지 않습니다 — 적어 준 사실만 근거로 씁니다</p>
    </div>
  );
}

function ApplyPanel({ o, patch }: { o: Opportunity; patch: (id: string, p: Partial<Opportunity>) => void }) {
  const toast = useToast();
  return (
    <div className="space-y-3 text-[14px]">
      <Banner tone="danger" icon={<ShieldAlert aria-hidden />}>
        제출은 시스템이 하지 않습니다. 확인 후 본인이 직접 제출하세요.
      </Banner>
      <dl className="grid grid-cols-[72px_1fr] items-center gap-3">
        <dt className="text-muted">신청 방법</dt>
        <dd className="flex flex-wrap items-center gap-2">
          {o.applyHow ?? "원문 확인"}
          <a href={o.url} target="_blank" rel="noopener noreferrer" className="btn btn-sm">
            바로가기
            <ExternalLink aria-hidden />
          </a>
        </dd>
        <dt className="text-muted">마감</dt>
        <dd className="flex flex-wrap items-center gap-2">
          <span className="num">{o.deadline} 18:00</span>
          <button type="button" className="btn btn-sm" onClick={() => toast("캘린더에 넣었습니다 (예시)", { tone: "success" })}>
            <CalendarPlus aria-hidden />
            캘린더에 넣기
          </button>
        </dd>
      </dl>
      <div>
        <p className="label">제출 서류</p>
        <ul className="divide-y divide-border rounded-xl border border-border">
          {(o.documents ?? []).map((d) => (
            <li key={d} className="flex items-center gap-3 px-3 py-2">
              <input type="checkbox" className="size-4 accent-[var(--primary)]" aria-label={d} />
              <span className="flex-1">{d}</span>
              {!d.includes("초안") && (
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => toast(`'${d}' 할 일을 마감 하루 전으로 만들었습니다 (예시)`)}>
                  <ListTodo aria-hidden />
                  할 일로 보내기
                </button>
              )}
            </li>
          ))}
        </ul>
      </div>
      <div className="flex flex-wrap justify-end gap-2 border-t border-border pt-3">
        <button
          type="button"
          className="btn btn-sm"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(demoDraft);
              toast("복사했습니다", { tone: "success" });
            } catch {
              toast("복사하지 못했습니다 — 초안 탭에서 직접 선택해 주세요", { tone: "error" });
            }
          }}
        >
          <Copy aria-hidden />
          초안 전체 복사
        </button>
        {o.progress === "신청함" ? (
          <>
            <button type="button" className="btn btn-sm" onClick={() => patch(o.id, { progress: "탈락" })}>
              탈락
            </button>
            <button type="button" className="btn btn-primary btn-sm" onClick={() => patch(o.id, { progress: "선정" })}>
              선정
            </button>
          </>
        ) : (
          <button type="button" className="btn btn-primary btn-sm" onClick={() => patch(o.id, { progress: "신청함" })}>
            신청했어요
          </button>
        )}
      </div>
    </div>
  );
}

function InterestsModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const toast = useToast();
  const [tags, setTags] = useState<string[]>(["AI·SW", "공모전·경진대회", "인턴·채용"]);
  const [keywords, setKeywords] = useState(["반도체", "공정실습"]);
  const [excludes, setExcludes] = useState(["대학원생"]);
  const [kw, setKw] = useState("");
  const [ex, setEx] = useState("");
  const add = (v: string, list: string[], set: (x: string[]) => void, clear: () => void) => {
    const t = v.trim();
    if (t.length < 2) {
      toast("두 글자 이상 입력하세요", { tone: "error" });
      return;
    }
    if (!list.includes(t) && list.length < 20) set([...list, t]);
    clear();
  };
  const ChipList = ({ list, set }: { list: string[]; set: (x: string[]) => void }) => (
    <>
      {list.map((k) => (
        <span key={k} className="chip bg-surface-3 text-text">
          {k}
          <button type="button" aria-label={`${k} 삭제`} onClick={() => set(list.filter((x) => x !== k))}>
            <X aria-hidden />
          </button>
        </span>
      ))}
    </>
  );
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="관심사 설정"
      footer={
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => {
            onClose();
            toast("32건을 다시 분류했습니다 (예시)", { tone: "success" });
          }}
        >
          저장
        </button>
      }
    >
      <div className="space-y-5 pt-1">
        <fieldset>
          <legend className="label">태그</legend>
          <div className="flex flex-wrap gap-2">
            {INTEREST_TAGS.map((t) => {
              const on = tags.includes(t);
              return (
                <button key={t} type="button" aria-pressed={on} onClick={() => setTags(on ? tags.filter((x) => x !== t) : [...tags, t])} className={`btn btn-sm ${on ? "border-primary bg-primary-soft text-primary" : ""}`}>
                  {t}
                </button>
              );
            })}
          </div>
        </fieldset>
        {[
          { label: "키워드 (최대 20)", list: keywords, set: setKeywords, v: kw, setV: setKw },
          { label: "제외 — 걸리면 무조건 '아님'", list: excludes, set: setExcludes, v: ex, setV: setEx },
        ].map((f) => (
          <div key={f.label}>
            <p className="label">{f.label}</p>
            <div className="flex flex-wrap items-center gap-2">
              <ChipList list={f.list} set={f.set} />
              <form
                className="flex gap-1"
                onSubmit={(e) => {
                  e.preventDefault();
                  add(f.v, f.list, f.set, () => f.setV(""));
                }}
              >
                <input className="field field-sm w-28" value={f.v} onChange={(e) => f.setV(e.target.value)} placeholder="+ 추가" aria-label={`${f.label} 추가`} />
              </form>
            </div>
          </div>
        ))}
        <p className="hint">바꾸면 기존 공지를 다시 분류합니다.</p>
      </div>
    </Modal>
  );
}
