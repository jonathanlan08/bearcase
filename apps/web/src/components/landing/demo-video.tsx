"use client";

import { useEffect, useRef, useState } from "react";
import { useMediaQuery } from "@/lib/hooks";

/** A 25-second recording of the live demo, for visitors who never click "Explore the demo". The file is fetched
 *  only when the frame scrolls into view, plays muted and looped while visible, and pauses off screen. With
 *  reduced motion it stays on the poster and offers controls instead of autoplaying. */
export function DemoVideo() {
  const ref = useRef<HTMLVideoElement>(null);
  const [visible, setVisible] = useState(false);
  const [load, setLoad] = useState(false);
  const reduced = useMediaQuery("(prefers-reduced-motion: reduce)");

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(([entry]) => {
      setVisible(entry.isIntersecting);
      if (entry.isIntersecting) setLoad(true);
    }, { threshold: 0.35 });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    const el = ref.current;
    if (!el || !load) return;
    if (visible && !reduced) el.play().catch(() => {});
    else el.pause();
  }, [visible, load, reduced]);

  return (
    <figure className="overflow-hidden rounded-[var(--radius-2)] border border-hairline bg-bg-raised">
      <video
        ref={ref}
        className="block aspect-[8/5] w-full"
        poster="/demo/bearcase-demo-poster.jpg"
        muted
        loop
        playsInline
        preload="none"
        controls={reduced}
        src={load ? "/demo/bearcase-demo.webm" : undefined}
        aria-label="Recording of the demo: a revenue claim of 18% growth that the statements put at 11.6%, the statement it came from, and the seller questions it produces"
      />
      <figcaption className="border-t border-hairline px-4 py-2.5 text-xs text-fg-muted">
        The fictional Northstar deal, recorded on the live site.
      </figcaption>
    </figure>
  );
}
