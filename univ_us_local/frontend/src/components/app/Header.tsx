"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import {
  Bell,
  CalendarClock,
  ChevronRight,
  Gift,
  Landmark,
  Plus,
  RefreshCw,
  Settings,
  Sun,
  TriangleAlert,
  UserCheck,
  WifiOff,
} from "lucide-react";
import { Popover } from "@/components/ui/Layout";
import { useAppData } from "./AppData";
import { navigateQuery } from "@/lib/useQueryState";
import { useStored } from "@/lib/storage";
import { demoNotifications, type AppNotification } from "@/lib/demo";
import { SETTINGS } from "@/lib/features";
import { fmtRelative, parseLocal } from "@/lib/dates";

// 헤더 — 로고 · 알림 · 일정 추가 · 설정. 메뉴 링크(GNB)는 두지 않는다(Frontend-Route 3절, 전역 결정 G4).

export function useOpenNewEvent() {
  const pathname = usePathname();
  const router = useRouter();
  return (kind: "event" | "todo" = "event") => {
    if (pathname === "/") navigateQuery({ new: kind }, "push");
    else router.push(`/?new=${kind}`);
  };
}

export default function Header() {
  const { error, status, syncing } = useAppData();
  const openNew = useOpenNewEvent();

  return (
    <>
      <header className="sticky top-0 z-40 border-b border-border bg-surface/90 backdrop-blur-md">
        <div className="mx-auto flex h-[var(--header-h)] max-w-[1600px] items-center gap-3 px-4 md:px-6">
          <Link href="/" className="flex items-center gap-2.5 rounded-lg pr-2" aria-label="유니버스 대시보드로">
            <span className="grid size-8 place-items-center rounded-lg bg-primary text-[15px] font-extrabold text-white" style={{ fontFamily: "var(--font-display)" }}>
              U
            </span>
            <span className="text-[17px] font-extrabold tracking-tight">유니버스</span>
            <span className="hidden text-[12px] font-semibold tracking-wide text-faint sm:inline" style={{ fontFamily: "var(--font-display)" }}>
              Univ-Us
            </span>
          </Link>

          <div className="ml-auto flex items-center gap-1.5">
            {status && (
              <Link
                href="/settings/sources"
                className="mr-1 hidden h-8 items-center gap-1.5 rounded-md px-2 text-[13px] text-muted transition-colors hover:bg-surface-3 hover:text-text md:inline-flex"
                title="수집 원천 상태"
              >
                {syncing ? (
                  <>
                    <RefreshCw className="size-3.5 animate-spin text-primary" aria-hidden />
                    {status.sync.source === "external" ? "예약 동기화 진행 중…" : "동기화 중…"}
                  </>
                ) : (
                  <>
                    <span className={`size-2 rounded-full ${status.sync.exit_code === 0 || status.sync.exit_code === null ? "bg-ok" : "bg-warn"}`} aria-hidden />
                    수집 {fmtRelative(status.updated_at)}
                  </>
                )}
              </Link>
            )}
            <NotificationButton />
            <button type="button" className="btn btn-primary btn-sm hidden md:inline-flex" onClick={() => openNew("event")}>
              <Plus aria-hidden />
              일정 추가
            </button>
            <SettingsMenu />
          </div>
        </div>
        {error && (
          <div role="alert" className="flex items-center justify-center gap-2 bg-danger px-4 py-2 text-center text-[13px] font-semibold text-white">
            <WifiOff className="size-4 flex-none" aria-hidden />
            백엔드에 연결할 수 없습니다. <code className="rounded bg-white/15 px-1">run.cmd</code> 가 실행 중인지 확인하세요.
          </div>
        )}
      </header>

      {/* 폰: 일정 추가는 오른쪽 아래 떠 있는 버튼(3-2) */}
      <motion.button
        type="button"
        onClick={() => openNew("event")}
        whileTap={{ scale: 0.94 }}
        className="fixed right-4 bottom-5 z-40 grid size-14 place-items-center rounded-2xl bg-primary text-white md:hidden"
        style={{ boxShadow: "var(--shadow-pop)" }}
        aria-label="일정 추가"
      >
        <Plus className="size-6" aria-hidden />
      </motion.button>
    </>
  );
}

const KIND_ICON: Record<AppNotification["kind"], React.ReactNode> = {
  academic: <Landmark aria-hidden />,
  deadline: <CalendarClock aria-hidden />,
  change: <RefreshCw aria-hidden />,
  briefing: <Sun aria-hidden />,
  opportunity: <Gift aria-hidden />,
  attendance: <UserCheck aria-hidden />,
};

function NotificationButton() {
  const router = useRouter();
  const [readMap, setReadMap] = useStored<Record<string, boolean>>("notifications-read", {});
  const items = demoNotifications.map((n) => ({ ...n, read: n.read || !!readMap[n.id] }));
  const unread = items.filter((n) => !n.read).length;
  const missed = items.filter((n) => n.missed);
  const today = items.filter((n) => !n.missed);

  const markAll = () => setReadMap(Object.fromEntries(items.map((n) => [n.id, true])));

  const Row = ({ n, close }: { n: (typeof items)[number]; close: () => void }) => (
    <li>
      <button
        type="button"
        className="flex w-full items-start gap-3 rounded-lg px-3 py-2.5 text-left transition-colors hover:bg-surface-2"
        onClick={() => {
          setReadMap((m) => ({ ...m, [n.id]: true }));
          close();
          router.push(n.href);
        }}
      >
        <span className={`mt-0.5 grid size-7 flex-none place-items-center rounded-lg [&>svg]:size-3.5 ${n.read ? "bg-surface-3 text-faint" : "bg-primary-soft text-primary"}`}>
          {KIND_ICON[n.kind]}
        </span>
        <span className="min-w-0 flex-1">
          <span className={`block text-[14px] leading-snug ${n.read ? "text-muted" : "font-semibold text-text"}`}>{n.title}</span>
          <span className="num text-[12px] text-faint">{fmtRelative(parseLocal(n.at))}</span>
        </span>
        {!n.read && <span className="mt-2 size-2 flex-none rounded-full bg-accent" aria-label="안 읽음" />}
      </button>
    </li>
  );

  return (
    <Popover
      label="알림"
      width={380}
      trigger={({ open, toggle, ref }) => (
        <button
          ref={ref}
          type="button"
          className="btn btn-ghost btn-icon relative"
          aria-label={`알림${unread ? ` ${unread}건 안 읽음` : ""}`}
          aria-expanded={open}
          onClick={toggle}
        >
          <Bell className="size-[18px]" aria-hidden />
          <AnimatePresence>
            {unread > 0 && (
              <motion.span
                key={unread}
                initial={{ scale: 0.5, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                exit={{ scale: 0.5, opacity: 0 }}
                className="num absolute top-1 right-1 grid min-w-[18px] place-items-center rounded-full bg-accent-text px-1 text-[11px] leading-[18px] font-bold text-white"
              >
                {unread}
              </motion.span>
            )}
          </AnimatePresence>
        </button>
      )}
    >
      {(close) => (
        <div className="py-2">
          <div className="flex items-center justify-between px-4 pt-1 pb-2">
            <span className="text-[15px] font-bold">알림</span>
            <span className="rounded bg-surface-3 px-1.5 text-[11px] font-semibold text-faint">예시</span>
          </div>
          {items.length === 0 ? (
            <p className="px-4 py-8 text-center text-[14px] text-faint">새 알림이 없습니다</p>
          ) : (
            <div className="thin-scroll max-h-[60vh] overflow-y-auto px-1">
              {missed.length > 0 && (
                <>
                  <p className="flex items-center gap-1.5 px-3 pt-1 pb-1 text-[12px] font-bold text-warn-text">
                    <TriangleAlert className="size-3.5" aria-hidden />
                    놓친 알림 {missed.length} <span className="font-medium text-faint">· PC 가 꺼져 있던 동안</span>
                  </p>
                  <ul>{missed.map((n) => <Row key={n.id} n={n} close={close} />)}</ul>
                </>
              )}
              <p className="px-3 pt-2 pb-1 text-[12px] font-bold text-faint">오늘</p>
              <ul>{today.map((n) => <Row key={n.id} n={n} close={close} />)}</ul>
            </div>
          )}
          <div className="mt-1 flex items-center justify-between border-t border-border px-3 pt-2">
            <button type="button" className="btn btn-ghost btn-sm" onClick={markAll} disabled={unread === 0}>
              모두 읽음
            </button>
            <Link href="/settings/notifications" className="btn btn-ghost btn-sm" onClick={close}>
              알림 설정
              <ChevronRight aria-hidden />
            </Link>
          </div>
        </div>
      )}
    </Popover>
  );
}

function SettingsMenu() {
  return (
    <Popover
      label="설정"
      width={220}
      trigger={({ open, toggle, ref }) => (
        <button ref={ref} type="button" className="btn btn-ghost btn-icon" aria-label="설정" aria-expanded={open} onClick={toggle}>
          <Settings className="size-[18px]" aria-hidden />
        </button>
      )}
    >
      {(close) => (
        <nav aria-label="설정" className="p-1.5">
          {SETTINGS.map((s) => (
            <Link
              key={s.href}
              href={s.href}
              onClick={close}
              className="flex h-10 items-center rounded-lg px-3 text-[14px] font-medium text-text transition-colors hover:bg-surface-2"
            >
              {s.label}
            </Link>
          ))}
        </nav>
      )}
    </Popover>
  );
}
