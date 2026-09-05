"use client";

import { useSyncExternalStore } from "react";

/** Media query as an external store (no setState-in-effect, SSR-safe: server snapshot is false). */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (cb) => { const mq = window.matchMedia(query); mq.addEventListener("change", cb); return () => mq.removeEventListener("change", cb); },
    () => window.matchMedia(query).matches,
    () => false,
  );
}

const listeners = new Set<() => void>();
function emit() { listeners.forEach((l) => l()); }

/** localStorage-backed boolean flag as an external store. */
export function useLocalFlag(key: string): [boolean, (v: boolean) => void] {
  const value = useSyncExternalStore(
    (cb) => { listeners.add(cb); window.addEventListener("storage", cb); return () => { listeners.delete(cb); window.removeEventListener("storage", cb); }; },
    () => { try { return localStorage.getItem(key) === "1"; } catch { return false; } },
    () => false,
  );
  const set = (v: boolean) => { try { localStorage.setItem(key, v ? "1" : "0"); } catch { /* ignore */ } emit(); };
  return [value, set];
}
