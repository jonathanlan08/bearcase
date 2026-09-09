"use client";
/* eslint-disable react-hooks/immutability -- imperative render loop: one shared mutable SceneState object is written by
   useFrame callbacks (never during render) and read by every entity each frame. */
/** The Evidence Sculpture: the landing hero as a real-time 3D object.
 *
 *  Three sheets sit on a graphite base: the seller's memo on top, a smoke-blue glass inspection plane, and the income
 *  statement underneath. Scroll drives the story (see storyboard.ts): chapter 1 shows the memo's growth claim; chapter 2
 *  lifts the layers apart and draws one red line from the claim to the statement cell that contradicts it; chapter 3
 *  moves the camera down to that cell and names its source. A small low-poly bear sits on the base as the brand mark.
 *
 *  Everything on the sheets is drawn on canvas textures from real Northstar figures, so the numbers a visitor can just
 *  about read in the scene are the numbers the demo shows. The readable version of the same story is the HTML caption
 *  list in the hero; nothing here is the only place a fact appears. No image assets, no model files. */

import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { ContactShadows, Environment, Html, Lightformer, MeshTransmissionMaterial, RoundedBox, useGLTF } from "@react-three/drei";
import { Bloom, EffectComposer, Vignette } from "@react-three/postprocessing";
import { Component, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { ramp, storyProgress, type SceneStore } from "@/components/scene/storyboard";

/* ---------- quality tiers ---------- */
type Tier = 1 | 2 | 3;
const TIERS: Record<Tier, { dpr: number; aa: boolean; glass: boolean; samples: number; shadows: boolean }> = {
  3: { dpr: 1.75, aa: true, glass: true, samples: 8, shadows: true },
  2: { dpr: 1.5, aa: true, glass: true, samples: 4, shadows: false },
  1: { dpr: 1.25, aa: false, glass: false, samples: 0, shadows: false },
};
function detectTier(mobile: boolean): Tier {
  if (typeof navigator === "undefined") return 2;
  const nav = navigator as Navigator & { deviceMemory?: number };
  if (mobile || (nav.deviceMemory ?? 8) <= 4) return 1;
  if ((nav.hardwareConcurrency ?? 4) >= 8) return 3;
  return 2;
}

/* ---------- palette (Ink) ---------- */
const INK = "#07080A";
const PAPER = "#F1EDE4";
const RULE = "#B9B3A7";
const TEXT = "#2C333C";
const MUTED = "#6F7780";
const RED = "#E4533C";
const GLASS = "#8FB0C8";

/* ---------- the two sheets and where their cells are ----------
   Sheets are 3.6 wide and 2.6 deep. Cell positions are texture fractions (u from the left, v from the top); the sheet lies
   flat, so a cell's world offset from the sheet centre is x = (u − ½)·W and z = (v − ½)·D. */
const W = 3.6, D = 2.6, TEX_W = 1024, TEX_H = 740;
interface Cell { u: number; v: number; w: number; h: number }
const CLAIM_CELL: Cell = { u: 0.62, v: 0.455, w: 0.2, h: 0.078 }; // memo: "Annual revenue growth 18%"
const SOURCE_CELL: Cell = { u: 0.795, v: 0.735, w: 0.16, h: 0.07 }; // statement: FY2024 growth 11.6%

function cellWorld(c: Cell): THREE.Vector3 {
  return new THREE.Vector3((c.u + c.w / 2 - 0.5) * W, 0, (c.v + c.h / 2 - 0.5) * D);
}

function canvas(): [HTMLCanvasElement, CanvasRenderingContext2D] | null {
  if (typeof document === "undefined") return null;
  const c = document.createElement("canvas");
  c.width = TEX_W; c.height = TEX_H;
  const g = c.getContext("2d");
  return g ? [c, g] : null;
}
function texture(c: HTMLCanvasElement): THREE.CanvasTexture {
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 8;
  return t;
}
function paperGround(g: CanvasRenderingContext2D): void {
  g.fillStyle = PAPER; g.fillRect(0, 0, TEX_W, TEX_H);
  // faint fibre: deterministic speckle so the paper is not a flat colour up close
  let seed = 11;
  const rnd = () => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648; };
  g.fillStyle = "rgba(60,50,40,0.05)";
  for (let i = 0; i < 1400; i++) g.fillRect(rnd() * TEX_W, rnd() * TEX_H, 1 + rnd() * 2, 1);
}
function table(g: CanvasRenderingContext2D, x: number, y: number, cols: number[], rows: string[][], rowH: number, opts: { bold?: number[]; header?: boolean; muted?: number[] } = {}): void {
  const font = (b: boolean) => `${b ? "600" : "400"} 19px ui-monospace, SFMono-Regular, Menlo, monospace`;
  const total = cols.reduce((a, b) => a + b, 0);
  g.strokeStyle = RULE; g.lineWidth = 1.2;
  rows.forEach((r, ri) => {
    const yy = y + ri * rowH;
    if (opts.header && ri === 0) { g.fillStyle = "rgba(44,51,60,0.08)"; g.fillRect(x, yy, total, rowH); }
    g.beginPath(); g.moveTo(x, yy + rowH); g.lineTo(x + total, yy + rowH); g.stroke();
    let cx = x;
    r.forEach((cell, ci) => {
      g.fillStyle = opts.muted?.includes(ri) ? MUTED : TEXT;
      g.font = font(!!opts.bold?.includes(ri) || (!!opts.header && ri === 0));
      g.textAlign = ci === 0 ? "left" : "right";
      g.textBaseline = "middle";
      g.fillText(cell, ci === 0 ? cx + 12 : cx + cols[ci] - 12, yy + rowH / 2 + 1);
      cx += cols[ci];
    });
  });
  g.beginPath(); g.moveTo(x, y); g.lineTo(x + total, y); g.stroke();
}

let memoTex: THREE.CanvasTexture | null = null;
/** The seller's memo page: "Financial highlights" with the 18% growth claim. */
function getMemoTexture(): THREE.CanvasTexture | null {
  if (memoTex) return memoTex;
  const cv = canvas(); if (!cv) return null;
  const [c, g] = cv;
  paperGround(g);
  g.fillStyle = TEXT; g.font = "600 30px ui-sans-serif, system-ui, sans-serif"; g.textAlign = "left"; g.textBaseline = "alphabetic";
  g.fillText("Northstar HVAC Services", 72, 92);
  g.font = "400 21px ui-sans-serif, system-ui, sans-serif"; g.fillStyle = MUTED;
  g.fillText("Confidential Information Memorandum · Financial highlights", 72, 126);
  g.fillStyle = RULE; g.fillRect(72, 146, 880, 2);
  g.fillStyle = TEXT; g.font = "400 19px ui-sans-serif, system-ui, sans-serif";
  ["A leading commercial HVAC service provider with a 20-year operating history,", "long-standing maintenance agreements, and a diversified customer base.", "Management believes the business is positioned for continued growth."].forEach((l, i) => g.fillText(l, 72, 190 + i * 30));
  table(g, 72, 300, [420, 200, 240], [
    ["Highlight", "", "Seller figure"],
    ["FY2024 revenue", "", "$12.95M"],
    ["Annual revenue growth", "", "18%"],
    ["Adjusted EBITDA", "", "$2.10M"],
    ["Recurring revenue", "", "85%"],
    ["Largest customer", "", "< 10%"],
  ], 58, { header: true, bold: [2] });
  g.fillStyle = MUTED; g.font = "400 16px ui-sans-serif, system-ui, sans-serif";
  g.fillText("Page 4 of 31 · Prepared by the seller's adviser", 72, 700);
  memoTex = texture(c);
  return memoTex;
}

let statementTex: THREE.CanvasTexture | null = null;
/** The income statement sheet with the recomputed growth row. */
function getStatementTexture(): THREE.CanvasTexture | null {
  if (statementTex) return statementTex;
  const cv = canvas(); if (!cv) return null;
  const [c, g] = cv;
  paperGround(g);
  g.fillStyle = TEXT; g.font = "600 28px ui-sans-serif, system-ui, sans-serif"; g.textAlign = "left"; g.textBaseline = "alphabetic";
  g.fillText("Income statement (USD)", 72, 88);
  g.font = "400 19px ui-sans-serif, system-ui, sans-serif"; g.fillStyle = MUTED;
  g.fillText("Sheet: Income Statement · fiscal years ending 31 December", 72, 120);
  g.fillStyle = RULE; g.fillRect(72, 140, 880, 2);
  table(g, 72, 170, [340, 180, 180, 180], [
    ["Line item", "FY2022", "FY2023", "FY2024"],
    ["Revenue", "10,400,000", "11,600,000", "12,950,000"],
    ["Cost of goods sold", "(6,968,000)", "(7,656,000)", "(8,417,500)"],
    ["Gross profit", "3,432,000", "3,944,000", "4,532,500"],
    ["Operating expenses", "(2,282,000)", "(2,584,000)", "(2,892,500)"],
    ["EBITDA", "1,150,000", "1,360,000", "1,640,000"],
    ["Net income", "724,850", "916,750", "1,173,250"],
    ["", "", "", ""],
    ["Revenue growth (recomputed)", "—", "11.5%", "11.6%"],
  ], 52, { header: true, bold: [1, 3, 5], muted: [8] });
  g.fillStyle = MUTED; g.font = "400 16px ui-sans-serif, system-ui, sans-serif";
  g.fillText("BearCase recomputes every ratio from the cells above; the growth row is not in the seller's workbook.", 72, 700);
  statementTex = texture(c);
  return statementTex;
}

/* ---------- shared per-frame state ---------- */
interface SceneState { p: number; pointer: THREE.Vector2; drag: THREE.Vector2; degrade: () => void }

/* ---------- the story in numbers: layer heights and reveals at progress p ---------- */
const BASE_TOP = 0.25;
type Layout = ReturnType<typeof layout>;
function layout(p: number) {
  const explode = ramp(p, 0.5, 0.64);
  const open = ramp(p, 0.7, 0.96);
  return {
    explode,
    open,
    yStatement: BASE_TOP + 0.08,
    yGlass: BASE_TOP + 0.42 + explode * 0.85,
    yMemo: BASE_TOP + 0.72 + explode * 1.55 + open * 0.5,
    glassSlide: open * 2.9, // chapter 3 slides the glass aside so the source cell is unobstructed
    claimReveal: ramp(p, 0.1, 0.3),
    linkReveal: ramp(p, 0.54, 0.66),
    sourceReveal: ramp(p, 0.6, 0.7),
    labelReveal: ramp(p, 0.84, 0.95),
  };
}

/* ---------- paper sheet: a thin box whose top face carries the texture ---------- */
function Sheet({ map, yaw = 0, edges }: { map: THREE.CanvasTexture | null; yaw?: number; edges: boolean }) {
  const mats = useMemo(() => {
    const side = new THREE.MeshStandardMaterial({ color: "#DCD6C9", roughness: 0.95 });
    const top = new THREE.MeshStandardMaterial({ color: PAPER, map: map ?? undefined, roughness: 0.92, metalness: 0 });
    const bottom = new THREE.MeshStandardMaterial({ color: "#E6E1D6", roughness: 0.95 });
    return [side, side, top, bottom, side, side];
  }, [map]);
  const edgeGeo = useMemo(() => new THREE.EdgesGeometry(new THREE.BoxGeometry(W, 0.022, D)), []);
  return (
    <group rotation={[0, yaw, 0]}>
      <mesh material={mats} castShadow receiveShadow>
        <boxGeometry args={[W, 0.022, D]} />
      </mesh>
      {edges && <lineSegments geometry={edgeGeo}><lineBasicMaterial color="#9C9689" transparent opacity={0.5} /></lineSegments>}
    </group>
  );
}

/** A translucent red mark over one cell; opacity is written each frame from the story. */
function CellMark({ cell, state, reveal }: { cell: Cell; state: SceneState; reveal: (l: Layout) => number }) {
  const ref = useRef<THREE.Mesh>(null);
  const world = useMemo(() => cellWorld(cell), [cell]);
  useFrame(() => {
    const m = ref.current; if (!m) return;
    const r = reveal(layout(state.p));
    (m.material as THREE.MeshBasicMaterial).opacity = 0.55 * r;
    m.visible = r > 0.001;
  });
  return (
    <mesh ref={ref} position={[world.x, 0.016, world.z]} rotation={[-Math.PI / 2, 0, 0]}>
      <planeGeometry args={[cell.w * W, cell.h * D]} />
      <meshBasicMaterial color={RED} transparent opacity={0} depthWrite={false} toneMapped={false} />
    </mesh>
  );
}

/** The one red line: grows from the claim cell down to the source cell in chapter 2. */
function Link({ state }: { state: SceneState }) {
  const ref = useRef<THREE.Mesh>(null);
  const top = useMemo(() => cellWorld(CLAIM_CELL), []);
  const bottom = useMemo(() => cellWorld(SOURCE_CELL), []);
  const up = useMemo(() => new THREE.Vector3(0, 1, 0), []);
  const a = useMemo(() => new THREE.Vector3(), []);
  const b = useMemo(() => new THREE.Vector3(), []);
  const end = useMemo(() => new THREE.Vector3(), []);
  const dir = useMemo(() => new THREE.Vector3(), []);
  useFrame(() => {
    const m = ref.current; if (!m) return;
    const l = layout(state.p);
    a.set(top.x, l.yMemo - 0.011, top.z);
    b.set(bottom.x, l.yStatement + 0.02, bottom.z);
    end.copy(a).lerp(b, l.linkReveal);
    const len = a.distanceTo(end);
    m.visible = len > 0.01;
    m.position.copy(a).lerp(end, 0.5);
    m.scale.set(1, Math.max(0.001, len), 1);
    dir.copy(end).sub(a).normalize();
    if (len > 0.01) m.quaternion.setFromUnitVectors(up, dir);
  });
  return (
    <mesh ref={ref}>
      <cylinderGeometry args={[0.012, 0.012, 1, 6]} />
      <meshBasicMaterial color={RED} toneMapped={false} />
    </mesh>
  );
}

/** The inspection plane. Tier 1 uses a plain transparent material; higher tiers refract what is beneath them. */
function Glass({ state, tier }: { state: SceneState; tier: Tier }) {
  const g = useRef<THREE.Group>(null);
  const q = TIERS[tier];
  const edgeGeo = useMemo(() => new THREE.EdgesGeometry(new THREE.BoxGeometry(W + 0.5, 0.06, D + 0.4)), []);
  const bg = useMemo(() => new THREE.Color(INK), []);
  useFrame((_, dt) => {
    const grp = g.current; if (!grp) return;
    const l = layout(state.p);
    grp.position.x = THREE.MathUtils.damp(grp.position.x, l.glassSlide, 5, dt);
    grp.position.y = THREE.MathUtils.damp(grp.position.y, l.yGlass, 5, dt);
    grp.rotation.z = THREE.MathUtils.damp(grp.rotation.z, -l.open * 0.18, 5, dt);
  });
  return (
    <group ref={g} position={[0, BASE_TOP + 0.42, 0]}>
      <mesh castShadow={q.shadows}>
        <boxGeometry args={[W + 0.5, 0.06, D + 0.4]} />
        {q.glass
          ? <MeshTransmissionMaterial samples={q.samples} resolution={tier === 3 ? 512 : 256} thickness={0.35} roughness={0.12} transmission={1} ior={1.45} chromaticAberration={0.02} anisotropicBlur={0.1} color={GLASS} attenuationColor={GLASS} attenuationDistance={1.6} background={bg} />
          : <meshPhysicalMaterial color={GLASS} transparent opacity={0.28} roughness={0.15} metalness={0} />}
      </mesh>
      <lineSegments geometry={edgeGeo}><lineBasicMaterial color="#BFD6E6" transparent opacity={0.45} /></lineSegments>
    </group>
  );
}

/** The memo sheet moves with the story (it is the layer that lifts). */
function Memo({ state, edges }: { state: SceneState; edges: boolean }) {
  const g = useRef<THREE.Group>(null);
  const map = useMemo(() => getMemoTexture(), []);
  useFrame((_, dt) => {
    const grp = g.current; if (!grp) return;
    const l = layout(state.p);
    grp.position.y = THREE.MathUtils.damp(grp.position.y, l.yMemo, 5, dt);
    grp.rotation.x = THREE.MathUtils.damp(grp.rotation.x, -l.explode * 0.06 - l.open * 0.1, 5, dt);
    grp.rotation.y = THREE.MathUtils.damp(grp.rotation.y, 0.035 + l.open * 0.05, 5, dt);
  });
  return (
    <group ref={g} position={[0, BASE_TOP + 0.72, 0]}>
      <Sheet map={map} edges={edges} />
      <CellMark cell={CLAIM_CELL} state={state} reveal={(l) => l.claimReveal} />
    </group>
  );
}

/** The bear: a sculpted low-poly model (public/models/bear.glb, 2,600 triangles, 53 KB, built by
 *  scratch/bear.py from fused distance fields and simplified). While it downloads, and wherever the file cannot load,
 *  the same silhouette is stood in by flat-shaded primitives so the base is never empty. */
const BEAR_MATERIAL = new THREE.MeshStandardMaterial({ color: "#262B32", roughness: 0.55, metalness: 0.35, flatShading: true });

function BearModel({ position }: { position: [number, number, number] }) {
  const { scene } = useGLTF("/models/bear.glb");
  const model = useMemo(() => {
    const g = scene.clone(true);
    g.traverse((o) => {
      const mesh = o as THREE.Mesh;
      if (mesh.isMesh) { mesh.material = BEAR_MATERIAL; mesh.castShadow = true; mesh.receiveShadow = true; }
    });
    return g;
  }, [scene]);
  return <primitive object={model} position={position} scale={0.44} rotation={[0, -0.75, 0]} />;
}

function BearPrimitives({ position }: { position: [number, number, number] }) {
  const mat = BEAR_MATERIAL;
  return (
    <group position={position} scale={0.5} rotation={[0, -0.6, 0]}>
      <mesh material={mat} position={[0, 0.62, 0]} scale={[1, 1.25, 0.85]} castShadow><sphereGeometry args={[0.62, 7, 5]} /></mesh>
      <mesh material={mat} position={[0, 1.42, 0.12]} castShadow><sphereGeometry args={[0.36, 6, 5]} /></mesh>
      <mesh material={mat} position={[0, 1.34, 0.42]}><sphereGeometry args={[0.17, 5, 4]} /></mesh>
      <mesh material={mat} position={[-0.24, 1.7, 0.02]}><sphereGeometry args={[0.11, 4, 3]} /></mesh>
      <mesh material={mat} position={[0.24, 1.7, 0.02]}><sphereGeometry args={[0.11, 4, 3]} /></mesh>
      <mesh material={mat} position={[-0.34, 0.2, 0.42]} rotation={[0.5, 0, 0]}><cylinderGeometry args={[0.16, 0.2, 0.5, 5]} /></mesh>
      <mesh material={mat} position={[0.34, 0.2, 0.42]} rotation={[0.5, 0, 0]}><cylinderGeometry args={[0.16, 0.2, 0.5, 5]} /></mesh>
    </group>
  );
}

class BearBoundary extends Component<{ fallback: React.ReactNode; children: React.ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() { return this.state.failed ? this.props.fallback : this.props.children; }
}

function Bear({ position }: { position: [number, number, number] }) {
  return (
    <BearBoundary fallback={<BearPrimitives position={position} />}>
      <Suspense fallback={<BearPrimitives position={position} />}>
        <BearModel position={position} />
      </Suspense>
    </BearBoundary>
  );
}

/** The source label that appears in chapter 3 beside the statement cell. Hidden from assistive tech: the caption list says the same. */
function SourceLabel({ state }: { state: SceneState }) {
  const ref = useRef<HTMLDivElement>(null);
  const world = useMemo(() => cellWorld(SOURCE_CELL), []);
  useFrame(() => {
    const el = ref.current; if (!el) return;
    const l = layout(state.p);
    el.style.opacity = String(l.labelReveal);
    el.style.transform = `translateY(${(1 - l.labelReveal) * 6}px)`;
  });
  return (
    <group position={[world.x + 0.35, BASE_TOP + 0.08 + 0.05, world.z + 0.05]}>
      <Html distanceFactor={6} zIndexRange={[20, 0]} style={{ pointerEvents: "none" }} aria-hidden>
        <div ref={ref} className="whitespace-nowrap rounded-[var(--radius-1)] border border-ink-600 bg-ink-900/95 px-2.5 py-1.5 text-paper-50 shadow-lg" style={{ fontFamily: "var(--font-sans)", opacity: 0 }}>
          <p className="micro" style={{ color: RED }}>contradicted</p>
          <p className="mt-0.5 text-[13px] leading-snug">Income Statement · FY2024 growth <span className="num">11.6%</span></p>
          <p className="text-[11px] text-graphite-400">recomputed from the revenue cells</p>
        </div>
      </Html>
    </group>
  );
}

/* ---------- camera: a studio orbit that frames the sculpture inside the free region ----------
   The hero measures the part of the viewport that is free for the composition (right of the copy on wide screens, the band
   between captions and copy when stacked). The orbit target starts at the sculpture's centre and, in chapter 3, moves to the
   source cell while the distance shortens. Pointer and drag nudge the azimuth and elevation; an idle drift keeps it alive. */
const TAN_HALF_FOV = Math.tan((30 / 2) * (Math.PI / 180));
const SCULPTURE_WIDTH = 8.4;
function Camera({ state, story }: { state: SceneState; story: SceneStore }) {
  const { camera } = useThree();
  const cur = useRef({ az: -0.55, el: 0.62, dist: 11.5, tx: 0, ty: 1, tz: 0, settled: false });
  const source = useMemo(() => cellWorld(SOURCE_CELL), []);
  useFrame(({ size }, dt) => {
    const l = layout(state.p);
    const r = story.region;
    const aspect = size.width / Math.max(1, size.height);
    const t = performance.now() / 1000;
    // distance so the sculpture fits the free region's width, then the chapter-3 dolly toward the cell
    const regionW = Math.max(0.2, r.right - r.left);
    const fitDist = SCULPTURE_WIDTH / (2 * TAN_HALF_FOV * aspect * regionW * 0.92);
    const portrait = THREE.MathUtils.clamp((1.1 - aspect) * 3, 0, 2.5);
    const dist = THREE.MathUtils.clamp(fitDist, 8.5, 16) + portrait - l.explode * 0.6 - l.open * 4.2;
    const az = -0.55 + Math.sin(t / 14) * 0.04 + state.pointer.x * 0.08 + state.drag.x - l.open * 0.25;
    const el = 0.62 - state.pointer.y * 0.05 + state.drag.y - l.explode * 0.08 + l.open * 0.12;
    // target: the sculpture's centre placed at the region's centre, then the source cell
    const halfH = dist * TAN_HALF_FOV, halfW = halfH * aspect;
    const cx = (r.left + r.right) / 2, cy = (r.top + r.bottom) / 2;
    const tx = THREE.MathUtils.lerp(0, source.x, l.open) - (cx - 0.5) * 2 * halfW * Math.cos(az);
    const ty = THREE.MathUtils.lerp(1.0, BASE_TOP + 0.1, l.open) + (cy - 0.5) * 2 * halfH;
    const tz = THREE.MathUtils.lerp(0, source.z, l.open) + (cx - 0.5) * 2 * halfW * Math.sin(az);
    const c = cur.current;
    if (!c.settled) { Object.assign(c, { az, el, dist, tx, ty, tz, settled: true }); }
    c.az = THREE.MathUtils.damp(c.az, THREE.MathUtils.clamp(az, -1.3, 0.3), 3, dt);
    c.el = THREE.MathUtils.damp(c.el, THREE.MathUtils.clamp(el, 0.25, 1.1), 3, dt);
    c.dist = THREE.MathUtils.damp(c.dist, dist, 2.5, dt);
    c.tx = THREE.MathUtils.damp(c.tx, tx, 2.5, dt);
    c.ty = THREE.MathUtils.damp(c.ty, ty, 2.5, dt);
    c.tz = THREE.MathUtils.damp(c.tz, tz, 2.5, dt);
    camera.position.set(c.tx + c.dist * Math.cos(c.el) * Math.sin(c.az), c.ty + c.dist * Math.sin(c.el), c.tz + c.dist * Math.cos(c.el) * Math.cos(c.az));
    camera.lookAt(c.tx, c.ty, c.tz);
    state.drag.x = THREE.MathUtils.damp(state.drag.x, 0, 1.2, dt);
    state.drag.y = THREE.MathUtils.damp(state.drag.y, 0, 1.2, dt);
  }, -1);
  return null;
}

/** Quality watchdog: average frame time over ~90 frames; one huge delta (hidden tab, debugger) is not a slow GPU. */
function Watchdog({ state }: { state: SceneState }) {
  const frames = useRef<number[]>([]);
  useFrame((_, dt) => {
    if (dt < 0.1) frames.current.push(dt);
    if (frames.current.length >= 90) {
      const avg = frames.current.reduce((a, b) => a + b, 0) / frames.current.length;
      frames.current = [];
      if (avg > 0.022) state.degrade();
    }
  });
  return null;
}

function Scene({ state, story, tier, post }: { state: SceneState; story: SceneStore; tier: Tier; post: boolean }) {
  const q = TIERS[tier];
  const statement = useMemo(() => getStatementTexture(), []);
  return (
    <>
      <color attach="background" args={[INK]} />
      <fog attach="fog" args={[INK, 14, 30]} />
      <ambientLight intensity={0.35} color="#F5F2EC" />
      <directionalLight position={[5, 9, 4]} intensity={2.2} castShadow={q.shadows} shadow-mapSize={[2048, 2048]} shadow-bias={-0.0004} shadow-camera-left={-6} shadow-camera-right={6} shadow-camera-top={6} shadow-camera-bottom={-6} />
      <pointLight position={[-6, 4, -2]} intensity={1.4} color="#9FC3FF" distance={18} decay={2} />
      <pointLight position={[4, 2, 6]} intensity={0.6} color="#F5F2EC" distance={14} decay={2} />
      {tier > 1 && (
        <Environment resolution={256} frames={1}>
          <Lightformer intensity={2} form="rect" scale={[8, 4, 1]} position={[0, 7, -3]} color="#F5F2EC" />
          <Lightformer intensity={0.9} form="circle" scale={[4, 4, 1]} position={[-7, 3, 4]} color="#9FC3FF" />
          <Lightformer intensity={0.6} form="rect" scale={[5, 1.5, 1]} position={[7, 1, 3]} color="#F5F2EC" />
        </Environment>
      )}
      <Camera state={state} story={story} />
      <Watchdog state={state} />
      <group>
        <RoundedBox args={[7.6, 0.5, 5.4]} radius={0.05} smoothness={3} receiveShadow castShadow>
          <meshStandardMaterial color="#1A1E24" roughness={0.88} metalness={0.08} />
        </RoundedBox>
        {tier > 1 && <ContactShadows position={[0, -0.26, 0]} opacity={0.7} scale={18} blur={2.2} far={4} color="#000" frames={1} />}
        <group position={[0, BASE_TOP + 0.08, 0]}>
          <Sheet map={statement} yaw={-0.02} edges={tier > 1} />
          <CellMark cell={SOURCE_CELL} state={state} reveal={(l) => l.sourceReveal} />
        </group>
        <Glass state={state} tier={tier} />
        <Memo state={state} edges={tier > 1} />
        <Link state={state} />
        <SourceLabel state={state} />
        <Bear position={[2.15, BASE_TOP, 1.05]} />
      </group>
      {post && (
        <EffectComposer multisampling={0} enableNormalPass={false}>
          <Bloom intensity={0.25} luminanceThreshold={0.8} luminanceSmoothing={0.3} mipmapBlur />
          <Vignette eskil={false} offset={0.2} darkness={0.5} />
        </EffectComposer>
      )}
    </>
  );
}

/** Counts rendered frames: the first tells the hero the canvas is drawn; the `warmAfter`th turns post-processing on. */
function FrameCounter({ onFirst, onWarm, warmAfter }: { onFirst: () => void; onWarm: () => void; warmAfter: number }) {
  const n = useRef(0);
  useFrame(() => {
    n.current += 1;
    if (n.current === 1) onFirst();
    else if (n.current === warmAfter) onWarm();
  });
  return null;
}

/** Eases storyboard progress toward the scroll-driven target each frame; reads the store directly, no React re-render. */
function ProgressDriver({ state, story }: { state: SceneState; story: SceneStore }) {
  useFrame((_, dt) => { state.p = THREE.MathUtils.damp(state.p, storyProgress(story.get()), 6, dt); });
  return null;
}

export function EvidenceSculptureScene({ story, mobile, onReady, onFail }: { story: SceneStore; mobile: boolean; onReady: () => void; onFail: () => void }) {
  const [tier, setTier] = useState<Tier>(() => detectTier(mobile));
  const [visible, setVisible] = useState(false);
  const [warm, setWarm] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const alive = useRef(true);
  const [state] = useState<SceneState>(() => ({ p: 0, pointer: new THREE.Vector2(0, 0), drag: new THREE.Vector2(0, 0), degrade: () => setTier((t) => (t > 1 ? ((t - 1) as Tier) : t)) }));
  // Unmounting the canvas (Pause 3D) makes R3F force a context loss; that is not a failure, so the handler ignores loss on a canvas that is no longer live.
  useEffect(() => () => { alive.current = false; }, []);
  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => setVisible(e.isIntersecting), { threshold: 0.01 });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  const dragging = useRef<{ x: number; y: number } | null>(null);
  const onPointerMove = useCallback((e: React.PointerEvent) => {
    const r = wrap.current?.getBoundingClientRect();
    if (!r) return;
    state.pointer.set(((e.clientX - r.left) / r.width) * 2 - 1, -(((e.clientY - r.top) / r.height) * 2 - 1));
    if (dragging.current) {
      state.drag.x += (e.clientX - dragging.current.x) * 0.004;
      state.drag.y += (e.clientY - dragging.current.y) * 0.003;
      dragging.current = { x: e.clientX, y: e.clientY };
    }
  }, [state]);
  const q = TIERS[tier];
  return (
    <div ref={wrap} className="h-full w-full" style={{ touchAction: "pan-y" }} onPointerMove={onPointerMove} onPointerDown={(e) => { if (e.pointerType === "mouse" && e.button !== 0) return; dragging.current = { x: e.clientX, y: e.clientY }; }} onPointerUp={() => { dragging.current = null; }} onPointerLeave={() => { dragging.current = null; state.pointer.set(0, 0); }}>
      <Canvas dpr={[1, q.dpr]} frameloop={visible ? "always" : "demand"} shadows={q.shadows ? { type: THREE.PCFSoftShadowMap } : false} gl={{ antialias: q.aa, powerPreference: "high-performance", alpha: false, toneMapping: THREE.ACESFilmicToneMapping, toneMappingExposure: 1.0 }} camera={{ fov: 30, position: [-5, 7, 9], near: 0.1, far: 60 }} onCreated={({ gl }) => { gl.domElement.addEventListener("webglcontextlost", (ev) => { ev.preventDefault(); if (alive.current && gl.domElement.isConnected) onFail(); }); }} aria-label="The Evidence Sculpture: the seller's memo lies on top of a glass inspection plane and the income statement. The memo's claim of 18% growth is linked by one red line to the statement cell that recomputes it as 11.6%; the camera then moves to that cell and names its source. A small bear sits on the base." role="img">
        <FrameCounter onFirst={onReady} onWarm={() => setWarm(true)} warmAfter={8} />
        <ProgressDriver state={state} story={story} />
        <Scene state={state} story={story} tier={tier} post={warm && tier > 1} />
      </Canvas>
    </div>
  );
}

useGLTF.preload("/models/bear.glb");
