"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";
import { X } from "lucide-react";

export interface ToastItem { id: number; title: string; description?: string; tone?: "neutral" | "success" | "error"; action?: { label: string; onClick: () => void } }
interface ToastApi { toast: (t: Omit<ToastItem, "id">) => void }

const Ctx = createContext<ToastApi>({ toast: () => {} });
export const useToast = () => useContext(Ctx);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const dismiss = useCallback((id: number) => setItems((xs) => xs.filter((x) => x.id !== id)), []);
  const toast = useCallback((t: Omit<ToastItem, "id">) => {
    const id = Date.now() + Math.random();
    setItems((xs) => [...xs.slice(-3), { ...t, id }]);
    window.setTimeout(() => dismiss(id), 6000);
  }, [dismiss]);
  const api = useMemo(() => ({ toast }), [toast]);
  return (
    <Ctx.Provider value={api}>
      {children}
      <div role="status" aria-live="polite" className="pointer-events-none fixed bottom-4 right-4 z-[90] flex w-[min(360px,calc(100vw-2rem))] flex-col gap-2">
        {items.map((t) => (
          <div key={t.id} className={`pointer-events-auto rounded-[var(--radius-3)] border bg-bg-raised p-3 shadow-[var(--shadow-2)] ${t.tone === "error" ? "border-red" : t.tone === "success" ? "border-accent" : ""}`}>
            <div className="flex items-start gap-2">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">{t.title}</p>
                {t.description && <p className="mt-0.5 text-sm text-fg-muted">{t.description}</p>}
                {t.action && (
                  <button type="button" className="mt-2 text-sm font-medium text-accent underline-offset-2 hover:underline" onClick={() => { t.action?.onClick(); dismiss(t.id); }}>{t.action.label}</button>
                )}
              </div>
              <button type="button" aria-label="Dismiss notification" className="rounded-[var(--radius-1)] p-1 text-fg-muted hover:bg-bg-muted" onClick={() => dismiss(t.id)}><X size={14} /></button>
            </div>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}
