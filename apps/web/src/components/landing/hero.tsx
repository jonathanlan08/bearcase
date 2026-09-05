"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { motion, useReducedMotion } from "motion/react";
import { buttonClass } from "@/components/ui/button";
import { EvidenceCoreStatic } from "@/components/scene/static";
import { useMediaQuery } from "@/lib/hooks";
import { STAGES } from "@/components/scene/storyboard";

const EvidenceCoreScene = dynamic(() => import("@/components/scene/evidence-core").then((m) => m.EvidenceCoreScene), { ssr: false });

let webglProbe: boolean | null = null;
function probeWebGL(): boolean {
  if (webglProbe === null) {
    try {
      const c = document.createElement("canvas");
      webglProbe = !!(c.getContext("webgl2") ?? c.getContext("webgl"));
    } catch {
      webglProbe = false;
    }
  }
  return webglProbe;
}
const noop = () => () => {};
function useWebGL(): boolean | null {
  return useSyncExternalStore(noop, probeWebGL, () => null);
}

export function Hero() {
  const reduced = useReducedMotion();
  const webgl = useWebGL();
  const ref = useRef<HTMLDivElement>(null);
  const [progress, setProgress] = useState(0);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const mobile = useMediaQuery("(max-width: 767px)");
  useEffect(() => {
    let raf = 0;
    const on = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const el = ref.current;
        if (!el) return;
        const rect = el.getBoundingClientRect();
        const total = el.offsetHeight - window.innerHeight;
        setProgress(Math.max(0, Math.min(1, -rect.top / Math.max(1, total))));
      });
    };
    on();
    window.addEventListener("scroll", on, { passive: true });
    window.addEventListener("resize", on);
    return () => { window.removeEventListener("scroll", on); window.removeEventListener("resize", on); cancelAnimationFrame(raf); };
  }, []);
  const interactive = !reduced && webgl === true && !failed;
  const stage = Math.min(STAGES.length - 1, Math.floor(progress * STAGES.length));
  const lines = [{ initial: { y: "110%" }, animate: { y: 0 } }];
  return (
    <div ref={ref} className={mobile ? "min-h-[180svh]" : "min-h-[240svh]"}>
      <div className="sticky top-0 h-svh overflow-hidden">
        <div className="absolute inset-0" aria-hidden={!interactive}>
          <div className={`absolute inset-0 transition-opacity duration-700 ${interactive && ready ? "opacity-100" : "opacity-0"}`}>
            {interactive && <EvidenceCoreScene progress={progress} mobile={mobile} onReady={() => setReady(true)} onFail={() => setFailed(true)} />}
          </div>
          <div className={`absolute inset-0 transition-opacity duration-700 ${interactive && ready ? "opacity-0" : "opacity-100"}`}>
            <EvidenceCoreStatic />
          </div>
        </div>
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(60%_60%_at_20%_50%,rgba(7,8,10,0.85),rgba(7,8,10,0.2)_60%,transparent)] md:bg-[linear-gradient(90deg,rgba(7,8,10,0.92)_0%,rgba(7,8,10,0.75)_38%,rgba(7,8,10,0.05)_62%,transparent)]" aria-hidden />
        <div className="relative mx-auto flex h-full max-w-[1200px] flex-col justify-end px-6 pb-16 pt-24 md:justify-center md:pb-0 lg:px-10">
          <div className="max-w-[640px]">
            <motion.p className="micro" initial={reduced ? false : { opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3 }}>AI-assisted acquisition diligence</motion.p>
            <h1 className="mt-4 text-[clamp(44px,7.5vw,104px)] leading-[0.98] tracking-[-0.015em]">
              {["Stress-test every claim", "before capital moves."].map((t, i) => (
                <span key={t} className="block overflow-hidden">
                  <motion.span className={`block ${i === 1 ? "font-display italic text-signal-300" : ""}`} initial={reduced ? false : lines[0].initial} animate={lines[0].animate} transition={{ duration: 0.7, delay: 0.15 + i * 0.08, ease: [0.32, 0.72, 0, 1] }}>{t}</motion.span>
                </span>
              ))}
            </h1>
            <motion.p className="mt-6 max-w-[520px] text-[17px] leading-relaxed text-fg-muted" initial={reduced ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: 0.5 }}>BearCase audits deal documents, verifies financial assumptions, and exposes the downside with source-linked evidence.</motion.p>
            <motion.div className="mt-8 flex flex-wrap gap-3" initial={reduced ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: 0.62 }}>
              <Link href="/demo" className={buttonClass("primary", "md", "h-11 px-5")}>Explore the demo</Link>
              <a href={process.env.NEXT_PUBLIC_GITHUB_URL ?? "/github"} className={buttonClass("secondary", "md", "h-11 px-5")} target="_blank" rel="noreferrer">View on GitHub</a>
            </motion.div>
            <div className="mt-10 flex items-center gap-3 font-mono text-[11px] text-fg-muted" aria-live="polite" aria-atomic>
              <span className="num">{String(stage + 1).padStart(2, "0")}</span>
              <span className="h-px w-8 bg-hairline" aria-hidden />
              <span>{interactive ? STAGES[stage].caption : "Documents → claims → evidence → verified model → downside → report"}</span>
            </div>
          </div>
        </div>
        {interactive && (
          <ol className="absolute left-3 top-1/2 hidden -translate-y-1/2 flex-col gap-2 md:flex" aria-label="Scene progress">
            {STAGES.map((s, i) => <li key={s.key} className={`h-3 w-px ${i <= stage ? "bg-signal-400" : "bg-ink-600"}`} title={s.caption} />)}
          </ol>
        )}
      </div>
    </div>
  );
}
