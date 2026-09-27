"use client";

import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Check, OctagonAlert, X } from "lucide-react";

// 토스트 — 아래 가운데, 5초. `되돌리기` 같은 행동 버튼은 Tab 으로 닿아야 한다(Frontend-Route 6-12).

type ToastTone = "default" | "success" | "error";
interface ToastItem {
  id: number;
  message: ReactNode;
  tone: ToastTone;
  action?: { label: string; onClick: () => void };
}
type ToastFn = (message: ReactNode, opts?: { tone?: ToastTone; action?: ToastItem["action"]; duration?: number }) => void;

const Ctx = createContext<ToastFn>(() => {});

export const useToast = () => useContext(Ctx);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const seq = useRef(0);

  const dismiss = useCallback((id: number) => setItems((xs) => xs.filter((x) => x.id !== id)), []);

  const toast = useCallback<ToastFn>(
    (message, opts) => {
      const id = ++seq.current;
      setItems((xs) => [...xs.slice(-2), { id, message, tone: opts?.tone ?? "default", action: opts?.action }]);
      window.setTimeout(() => dismiss(id), opts?.duration ?? 5000);
    },
    [dismiss],
  );

  const value = useMemo(() => toast, [toast]);

  return (
    <Ctx.Provider value={value}>
      {children}
      <div
        role="status"
        aria-live="polite"
        className="pointer-events-none fixed inset-x-0 bottom-4 z-[70] flex flex-col items-center gap-2 px-4 max-md:bottom-24"
      >
        <AnimatePresence initial={false}>
          {items.map((t) => (
            <motion.div
              key={t.id}
              layout
              initial={{ opacity: 0, y: 16, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, scale: 0.98, transition: { duration: 0.12 } }}
              transition={{ type: "spring", bounce: 0, visualDuration: 0.25 }}
              className="pointer-events-auto flex max-w-[min(560px,100%)] items-center gap-3 rounded-xl bg-[#0f2724] py-2.5 pr-2 pl-4 text-[14px] font-semibold text-white"
              style={{ boxShadow: "var(--shadow-pop)" }}
            >
              {t.tone === "success" && <Check className="size-4 flex-none text-[#5eead4]" aria-hidden />}
              {t.tone === "error" && <OctagonAlert className="size-4 flex-none text-[#fca5a5]" aria-hidden />}
              <span className="min-w-0">{t.message}</span>
              {t.action && (
                <button
                  type="button"
                  className="flex-none rounded-md px-2 py-1 text-[#5eead4] underline-offset-2 hover:bg-white/10 hover:underline"
                  onClick={() => {
                    t.action?.onClick();
                    dismiss(t.id);
                  }}
                >
                  {t.action.label}
                </button>
              )}
              <button
                type="button"
                className="grid size-7 flex-none place-items-center rounded-md text-white/70 hover:bg-white/10 hover:text-white"
                onClick={() => dismiss(t.id)}
                aria-label="알림 닫기"
              >
                <X className="size-4" aria-hidden />
              </button>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </Ctx.Provider>
  );
}
