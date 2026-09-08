"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { motion } from "motion/react";
import { Pause, Play } from "lucide-react";
import { buttonClass } from "@/components/ui/button";
import { EvidenceSculptureStatic } from "@/components/scene/static";
import { CHAPTERS, chapterIndex, createSceneStore } from "@/components/scene/storyboard";
import { useLocalFlag, useMediaQuery } from "@/lib/hooks";

const EvidenceSculptureScene = dynamic(() => import("@/components/scene/evidence-sculpture").then((m) => m.EvidenceSculptureScene), { ssr: false });

/** localStorage key for the visitor's "Pause 3D" preference (`"1"` = paused). Read through `useLocalFlag`. */
export const SCENE_PAUSED_KEY = "bc.scene.paused";

let webglProbe: boolean | null = null;
function probeWebGL(): boolean {
  if (webglProbe === null) {
    try {
      const c = document.createElement("canvas");
      const gl = c.getContext("webgl2") ?? c.getContext("webgl");
      webglProbe = !!gl;
      gl?.getExtension("WEBGL_lose_context")?.loseContext(); // the probe context is not the one the scene uses; release it
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

/** The three captions. Rendered as HTML at the top of the hero on narrow screens and at the bottom left on wide ones, both
 *  outside the busy centre of the scene. The active step carries `aria-current`, a left rule, and heavier type, so the state
 *  is never colour alone; on wide screens the active step also shows its one-line explanation in a fixed-height slot so the
 *  copy above never shifts. */
function StoryCaptions({ chapter }: { chapter: number }) {
  return (
    <ol className="flex flex-col gap-1.5 lg:gap-2" aria-label="How BearCase reviews a claim">
      {CHAPTERS.map((c, i) => {
        const active = i === chapter;
        return (
          <li key={c.key} aria-current={active ? "step" : undefined} className={`flex gap-3 border-l-2 pl-3 ${active ? "border-accent" : "border-transparent"}`}>
            <span className={`num w-3 shrink-0 text-xs leading-5 ${active ? "text-accent" : "text-fg-muted"}`} aria-hidden>{i + 1}</span>
            <span className="min-w-0">
              <span className={`block text-sm leading-5 lg:text-[15px] ${active ? "font-medium text-fg" : "text-fg-muted"}`}>{c.title}</span>
              {active && <span className="mt-0.5 hidden h-10 max-w-[440px] text-[13px] leading-5 text-fg-muted lg:line-clamp-2 lg:block">{c.detail}</span>}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

export function Hero() {
  const reduced = useMediaQuery("(prefers-reduced-motion: reduce)");
  const wide = useMediaQuery("(min-width: 1024px)");
  const mobile = useMediaQuery("(max-width: 767px)");
  const webgl = useWebGL();
  const [paused, setPaused] = useLocalFlag(SCENE_PAUSED_KEY);
  const [store] = useState(createSceneStore);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const stickyRef = useRef<HTMLDivElement>(null);
  const copyRef = useRef<HTMLDivElement>(null);
  const barRef = useRef<HTMLDivElement>(null);
  // Re-renders only when the chapter changes; the scene reads the raw fraction from the store every frame.
  const chapter = useSyncExternalStore(store.subscribe, () => chapterIndex(store.get()), () => 0);
  useEffect(() => {
    let raf = 0;
    const onScroll = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const el = ref.current;
        if (!el) return;
        const rect = el.getBoundingClientRect();
        const total = el.offsetHeight - window.innerHeight;
        store.set(-rect.top / Math.max(1, total));
      });
    };
    // The free region for the composition, measured against the sticky box so it does not depend on scroll position:
    // right of the copy when the layout is side by side (lg+), the band between the captions and the copy when stacked.
    const measure = () => {
      const box = stickyRef.current, copy = copyRef.current, bar = barRef.current;
      if (!box || !copy || !bar) return;
      const b = box.getBoundingClientRect(), c = copy.getBoundingClientRect(), k = bar.getBoundingClientRect();
      if (b.width < 1 || b.height < 1) return;
      const sideBySide = window.innerWidth >= 1024;
      store.setRegion(sideBySide
        ? { left: (c.right - b.left + 24) / b.width, right: 1, top: 0, bottom: 1 }
        : { left: 0, right: 1, top: (k.bottom - b.top + 8) / b.height, bottom: (c.top - b.top - 8) / b.height });
    };
    const onResize = () => { onScroll(); measure(); };
    onResize();
    const settle = window.setTimeout(measure, 1200); // once the copy's entrance animation and fonts have settled
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onResize);
    return () => { window.removeEventListener("scroll", onScroll); window.removeEventListener("resize", onResize); cancelAnimationFrame(raf); window.clearTimeout(settle); };
  }, [store]);

  const canAnimate = !reduced && webgl === true && !failed;
  const interactive = canAnimate && !paused;
  const showScene = interactive && ready;
  const togglePaused = () => { setReady(false); setPaused(!paused); };
  const current = CHAPTERS[chapter];
  const enter = (delay: number) => ({ initial: reduced ? false : { opacity: 0, y: 10 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.5, delay, ease: [0.16, 1, 0.3, 1] as const } });
  return (
    <div ref={ref} className="min-h-[180svh] md:min-h-[200svh]">
      <div ref={stickyRef} className="sticky top-0 h-svh overflow-hidden">
        {/* Scene layer: mounted only when the visitor can and wants to run it; unmounting stops the render loop and frees the GPU context. */}
        <div className={`absolute inset-0 transition-opacity duration-700 ${showScene ? "opacity-100" : "opacity-0"}`} aria-hidden={!showScene}>
          {interactive && <EvidenceSculptureScene story={store} mobile={mobile} onReady={() => setReady(true)} onFail={() => setFailed(true)} />}
        </div>
        {/* Static layer: the LCP image, the reduced-motion and no-WebGL version, and the paused view. Pointer events pass through to the scene when it is showing. */}
        <div className={`absolute inset-0 transition-opacity duration-700 ${showScene ? "pointer-events-none opacity-0" : "opacity-100"}`} aria-hidden={showScene}>
          <EvidenceSculptureStatic align={wide ? "right" : "center"} />
        </div>
        <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(180deg,rgba(7,8,10,0.6)_0%,rgba(7,8,10,0)_22%,rgba(7,8,10,0)_44%,rgba(7,8,10,0.72)_62%,rgba(7,8,10,0.96)_82%)] lg:bg-[linear-gradient(90deg,rgba(7,8,10,0.94)_0%,rgba(7,8,10,0.8)_34%,rgba(7,8,10,0.06)_56%,transparent)]" aria-hidden />
        {/* Copy layer. `pointer-events-none` so parallax, drag, and node hover reach the canvas; the text and controls opt back in. */}
        <div className="pointer-events-none relative mx-auto flex h-full max-w-[1200px] flex-col px-6 pb-8 pt-20 lg:px-10 lg:pb-10 lg:pt-24">
          <div className="flex flex-1 flex-col justify-end lg:justify-center">
            <div ref={copyRef} className="pointer-events-auto max-w-[600px]">
              <motion.h1 {...enter(0.05)} className="text-[40px] leading-[1.02] tracking-[-0.035em] md:text-[64px] lg:text-[76px]">
                Check the seller&apos;s numbers before you buy the business.
              </motion.h1>
              <motion.p {...enter(0.18)} className="mt-6 max-w-[480px] text-[17px] leading-relaxed text-fg-muted md:text-lg">
                Upload the seller&apos;s package. BearCase finds the claims the documents contradict and hands you the questions to ask, each with its source.
              </motion.p>
              <motion.div {...enter(0.3)} className="mt-8 flex flex-wrap gap-3">
                <Link href="/demo" className={buttonClass("primary", "md", "h-11 px-5")}>Explore the demo</Link>
                <Link href="/app" className={buttonClass("secondary", "md", "h-11 px-5")}>Sign in or create an account</Link>
              </motion.div>
              <motion.p {...enter(0.38)} className="mt-4 text-sm text-fg-muted">Fictional deal, no account needed. Or try <Link href="/demo?deal=messy" className="underline underline-offset-2 hover:text-fg">the messy one</Link>.</motion.p>
            </div>
          </div>
          <div ref={barRef} className="order-first flex items-start justify-between gap-4 lg:order-last lg:mt-8 lg:items-end lg:justify-start lg:gap-8">
            <div className="pointer-events-auto min-w-0"><StoryCaptions chapter={chapter} /></div>
            {canAnimate && (
              <button type="button" aria-pressed={paused} onClick={togglePaused} className={buttonClass("secondary", "sm", "pointer-events-auto shrink-0 text-fg-muted hover:text-fg")}>
                {paused ? <Play size={14} aria-hidden /> : <Pause size={14} aria-hidden />}
                {paused ? "Resume 3D" : "Pause 3D"}
              </button>
            )}
          </div>
          <p className="sr-only" aria-live="polite" aria-atomic>{`Step ${chapter + 1} of ${CHAPTERS.length}: ${current.title}. ${current.detail}`}</p>
        </div>
      </div>
    </div>
  );
}
