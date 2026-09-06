"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { motion } from "motion/react";
import { buttonClass } from "@/components/ui/button";
import { EvidenceCoreStatic } from "@/components/scene/static";
import { STAGES } from "@/components/scene/storyboard";
import { useMediaQuery } from "@/lib/hooks";

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
  const reduced = useMediaQuery("(prefers-reduced-motion: reduce)");
  const webgl = useWebGL();
  const mobile = useMediaQuery("(max-width: 767px)");
  const ref = useRef<HTMLDivElement>(null);
  const [progress, setProgress] = useState(0);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
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
  const enter = (delay: number) => ({ initial: reduced ? false : { opacity: 0, y: 10 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.5, delay, ease: [0.16, 1, 0.3, 1] as const } });
  return (
    <div ref={ref} className={mobile ? "min-h-[180svh]" : "min-h-[220svh]"}>
      <div className="sticky top-0 h-svh overflow-hidden">
        <div className="absolute inset-0" aria-hidden={!interactive}>
          <div className={`absolute inset-0 transition-opacity duration-700 ${interactive && ready ? "opacity-100" : "opacity-0"}`}>
            {interactive && <EvidenceCoreScene progress={progress} mobile={mobile} onReady={() => setReady(true)} onFail={() => setFailed(true)} />}
          </div>
          <div className={`absolute inset-0 transition-opacity duration-700 ${interactive && ready ? "opacity-0" : "opacity-100"}`}>
            <EvidenceCoreStatic />
          </div>
        </div>
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(60%_60%_at_20%_50%,rgba(7,8,10,0.9),rgba(7,8,10,0.25)_60%,transparent)] md:bg-[linear-gradient(90deg,rgba(7,8,10,0.94)_0%,rgba(7,8,10,0.78)_36%,rgba(7,8,10,0.05)_60%,transparent)]" aria-hidden />
        <div className="relative mx-auto flex h-full max-w-[1200px] flex-col justify-end px-6 pb-16 pt-24 md:justify-center md:pb-0 lg:px-10">
          <div className="max-w-[600px]">
            <motion.h1 {...enter(0.05)} className="text-[40px] leading-[1.02] tracking-[-0.035em] md:text-[64px] lg:text-[76px]">
              Stress-test every claim before capital moves.
            </motion.h1>
            <motion.p {...enter(0.18)} className="mt-6 max-w-[480px] text-[17px] leading-relaxed text-fg-muted md:text-lg">
              BearCase reads the deal room, ties every claim to its source, recomputes the numbers, and shows you where the story breaks.
            </motion.p>
            <motion.div {...enter(0.3)} className="mt-8 flex flex-wrap gap-3">
              <Link href="/demo" className={buttonClass("primary", "md", "h-11 px-5")}>Explore the demo</Link>
              <a href={process.env.NEXT_PUBLIC_GITHUB_URL ?? "/github"} className={buttonClass("secondary", "md", "h-11 px-5")} target="_blank" rel="noreferrer">View on GitHub</a>
            </motion.div>
            <p className="sr-only" aria-live="polite" aria-atomic>{interactive ? `Scene stage ${stage + 1} of ${STAGES.length}: ${STAGES[stage].caption}` : "Static illustration of the evidence workflow."}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
