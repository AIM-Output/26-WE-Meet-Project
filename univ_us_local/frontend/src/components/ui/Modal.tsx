"use client";

import { useEffect, useId, useRef, useSyncExternalStore, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "motion/react";
import { X } from "lucide-react";

// 모달 — PC 는 가운데(최대 폭 540), 768px 미만은 바텀 시트(Frontend-Route 6-11).
// 열리면 제목에 포커스·포커스 트랩·ESC·배경 스크롤 잠금·role=dialog (6-12). 닫힌 뒤 트리거로 포커스를 돌려준다.

const noop = () => () => {};
const isClient = () => true;
const isServer = () => false;

const FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

export function Modal({
  open,
  onClose,
  title,
  children,
  footer,
  size = "md",
  hideClose,
}: {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  size?: "sm" | "md" | "lg" | "xl" | "full";
  hideClose?: boolean;
}) {
  const mounted = useSyncExternalStore(noop, isClient, isServer);
  if (!mounted) return null;
  return createPortal(
    <AnimatePresence>
      {open && (
        <ModalBody key="modal" onClose={onClose} title={title} footer={footer} size={size} hideClose={hideClose}>
          {children}
        </ModalBody>
      )}
    </AnimatePresence>,
    document.body,
  );
}

const WIDTH = { sm: "md:max-w-[420px]", md: "md:max-w-[540px]", lg: "md:max-w-[720px]", xl: "md:max-w-[960px]", full: "md:max-w-none" };

function ModalBody({
  onClose,
  title,
  children,
  footer,
  size,
  hideClose,
}: {
  onClose: () => void;
  title?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  size: "sm" | "md" | "lg" | "xl" | "full";
  hideClose?: boolean;
}) {
  const panel = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    const trigger = document.activeElement as HTMLElement | null;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const heading = panel.current?.querySelector<HTMLElement>("[data-autofocus]") ?? panel.current?.querySelector<HTMLElement>("h2");
    (heading ?? panel.current)?.focus();

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        // 모달 위의 모달(확인창)이 떠 있으면 가장 위의 것만 닫힌다
        const all = document.querySelectorAll("[data-modal-panel]");
        if (all[all.length - 1] === panel.current) {
          e.stopPropagation();
          onCloseRef.current();
        }
        return;
      }
      if (e.key !== "Tab" || !panel.current) return;
      const nodes = Array.from(panel.current.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((n) => n.offsetParent !== null);
      if (nodes.length === 0) return;
      const first = nodes[0];
      const last = nodes[nodes.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
      trigger?.focus?.();
    };
  }, []);

  const full = size === "full";

  return (
    <div className={`fixed inset-0 z-50 flex ${full ? "items-stretch" : "items-end md:items-center"} justify-center md:p-6`}>
      <motion.div
        className="absolute inset-0 bg-[var(--scrim)]"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0, transition: { duration: 0.12 } }}
        transition={{ duration: 0.18 }}
        onMouseDown={onClose}
        aria-hidden
      />
      <motion.div
        ref={panel}
        data-modal-panel
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        tabIndex={-1}
        className={`relative flex w-full flex-col bg-surface outline-none ${
          full ? "h-full md:rounded-none" : `max-h-[92dvh] rounded-t-2xl md:max-h-[calc(100dvh-48px)] md:rounded-2xl ${WIDTH[size]}`
        }`}
        style={{ boxShadow: "var(--shadow-overlay)" }}
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 16, transition: { duration: 0.12 } }}
        transition={{ type: "spring", bounce: 0, visualDuration: 0.24 }}
      >
        {!full && <div className="mx-auto mt-2 h-1 w-10 flex-none rounded-full bg-border md:hidden" aria-hidden />}
        {(title || !hideClose) && (
          <div className="flex flex-none items-start gap-3 px-5 pt-4 pb-2 md:px-6 md:pt-5">
            {title && (
              <h2 id={titleId} tabIndex={-1} className="min-w-0 flex-1 text-[19px] font-bold leading-snug tracking-tight outline-none">
                {title}
              </h2>
            )}
            {!hideClose && (
              <button type="button" className="btn btn-ghost btn-icon btn-sm -mr-2 ml-auto" onClick={onClose} aria-label="닫기">
                <X aria-hidden />
              </button>
            )}
          </div>
        )}
        <div className="thin-scroll min-h-0 flex-1 overflow-y-auto px-5 pb-5 md:px-6">{children}</div>
        {footer && (
          <div className="flex flex-none flex-wrap items-center justify-end gap-2 border-t border-border px-5 py-3 md:px-6">{footer}</div>
        )}
      </motion.div>
    </div>
  );
}
