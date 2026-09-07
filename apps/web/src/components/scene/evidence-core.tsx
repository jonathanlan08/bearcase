"use client";
/* eslint-disable react-hooks/immutability -- imperative render loop: one shared mutable SceneState
   object is written by useFrame callbacks (never during render) and read by every entity each frame. This is the
   standard React Three Fiber pattern and avoids re-rendering React on every frame. */

import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { ContactShadows, Environment, Html, Lightformer, MeshTransmissionMaterial } from "@react-three/drei";
import { Bloom, EffectComposer, Vignette } from "@react-three/postprocessing";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { DOC_LABELS, NODES, ramp, statusReveal, storyProgress, type SceneStore, type Status } from "@/components/scene/storyboard";

/* ---------- quality tiers ---------- */
type Tier = 1 | 2 | 3;
const TIERS: Record<Tier, { dpr: number; particles: number; edges: boolean; aa: boolean; docs: number }> = {
  3: { dpr: 1.75, particles: 2400, edges: true, aa: true, docs: 6 },
  2: { dpr: 1.5, particles: 1200, edges: true, aa: true, docs: 6 },
  1: { dpr: 1.25, particles: 600, edges: false, aa: false, docs: 4 },
};
function detectTier(mobile: boolean): Tier {
  if (typeof navigator === "undefined") return 2;
  const nav = navigator as Navigator & { deviceMemory?: number };
  if (mobile || (nav.deviceMemory ?? 8) <= 4) return 1;
  if ((nav.hardwareConcurrency ?? 4) >= 8) return 3;
  return 2;
}

/* ---------- palette (Ink) ---------- */
const C = {
  paper: new THREE.Color("#F5F2EC"),
  inkEdge: new THREE.Color("#2C333C"),
  core: new THREE.Color("#15181D"),
  signal: new THREE.Color("#7FB2FF"),
  red: new THREE.Color("#EF7360"),
  amber: new THREE.Color("#E7AA40"),
  graphite: new THREE.Color("#8A94A0"),
};
const STATUS_COLOR: Record<Status, THREE.Color> = { supported: C.signal, contradicted: C.red, unsupported: C.graphite, review: C.amber };
/** Claims start as claims (warm neutral) and take their status colour only when chapter 2 reveals the verdict. */
const NEUTRAL = C.paper.clone().multiplyScalar(0.72);

/* ---------- viewport framing ----------
   The hero measures the part of the viewport that is free for the composition (right of the copy on wide screens, the band
   between captions and copy on stacked layouts) and the camera frames the story inside it: the core sits in that region for
   chapters 1–2, and the late-stage cluster (core drifting to x −1.6 … report stack at x 3.2, about 5.5 units wide) is centred
   and scaled by `fit` so it never spills over the headline. Portrait viewports also dolly out so the core fits the band.
   `spread` narrows the document arc slightly on wide aspects so the far documents stay in frame beside the copy. */
const TAN_HALF_FOV = Math.tan((32 / 2) * (Math.PI / 180));
const CLUSTER_WIDTH = 5.5;
const CLUSTER_CENTER = new THREE.Vector2(0.45, -0.1);
interface Frame { spread: number; fit: number; axisX: number; axisY: number; z: number; settled: boolean }

/* ---------- procedural "paper with text lines" texture (no image assets) ---------- */
let paperTexture: THREE.CanvasTexture | null = null;
function getPaperTexture(): THREE.CanvasTexture | null {
  if (paperTexture) return paperTexture;
  if (typeof document === "undefined") return null;
  const c = document.createElement("canvas");
  c.width = 256; c.height = 332;
  const g = c.getContext("2d");
  if (!g) return null;
  g.fillStyle = "#F5F2EC"; g.fillRect(0, 0, c.width, c.height);
  g.fillStyle = "#2C333C";
  g.fillRect(28, 30, 120, 8); // title
  let y = 62;
  let seed = 7;
  const rnd = () => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648; };
  while (y < 300) { const w = 90 + rnd() * 120; g.globalAlpha = 0.55 + rnd() * 0.3; g.fillRect(28, y, w, 4); y += 14 + (rnd() < 0.18 ? 12 : 0); }
  g.globalAlpha = 0.9; g.fillStyle = "#7FB2FF"; g.fillRect(150, 118, 60, 4); g.fillRect(96, 174, 40, 4); // highlighted figures
  paperTexture = new THREE.CanvasTexture(c);
  paperTexture.colorSpace = THREE.SRGBColorSpace;
  paperTexture.anisotropy = 4;
  return paperTexture;
}

/* ---------- soft round particle sprite (procedural) ---------- */
let spriteTexture: THREE.CanvasTexture | null = null;
function getSprite(): THREE.CanvasTexture | null {
  if (spriteTexture) return spriteTexture;
  if (typeof document === "undefined") return null;
  const c = document.createElement("canvas");
  c.width = c.height = 64;
  const g = c.getContext("2d");
  if (!g) return null;
  const grad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  grad.addColorStop(0, "rgba(255,255,255,1)");
  grad.addColorStop(0.35, "rgba(255,255,255,0.6)");
  grad.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, 64, 64);
  spriteTexture = new THREE.CanvasTexture(c);
  return spriteTexture;
}

/* ---------- shared, mutable scene state (one object, updated per frame) ---------- */
interface SceneState { p: number; pointer: THREE.Vector2; drag: THREE.Vector2; selected: number | null; hover: number | null; frame: Frame; degrade: () => void }

const tmp = new THREE.Object3D();
const v3 = new THREE.Vector3();
const tmpColor = new THREE.Color();

/* Document anchor positions (arc in front of the core), and their target "recede" positions. `spread` (0.75–1) narrows the arc on wide aspects. */
function docPose(i: number, n: number, p: number, spread: number): { pos: THREE.Vector3; rot: THREE.Euler; scale: number } {
  const t = n === 1 ? 0.5 : i / (n - 1);
  const angle = (t - 0.5) * Math.PI * 0.9 * spread;
  const enter = ramp(p, 0, 0.1);
  const recede = ramp(p, 0.68, 0.8);
  const r = 3.4 + recede * 1.8;
  const z = -6 + enter * 6 - recede * 4 + Math.cos(angle) * 0.6 - 1.2;
  const x = Math.sin(angle) * r;
  const y = (i % 2 ? 0.55 : -0.45) + Math.sin(p * 6 + i) * 0.03;
  return { pos: new THREE.Vector3(x, y, z), rot: new THREE.Euler(0, -angle * 0.55, (i % 2 ? 1 : -1) * 0.04), scale: 1 - ramp(p, 0.2, 0.3) * 0.2 };
}

/* Node positions per stage. */
function nodePose(i: number, p: number, docPos: THREE.Vector3): THREE.Vector3 {
  const status = NODES[i].status;
  const phi = (i / NODES.length) * Math.PI * 2;
  const onCore = new THREE.Vector3(Math.cos(phi) * 1.25, Math.sin(phi * 1.7) * 0.9, Math.sin(phi) * 1.25 + 0.4);
  const start = docPos.clone().add(new THREE.Vector3(0, 0.2 + (i % 3) * 0.15, 0.2));
  const flow = ramp(p, 0.2, 0.4);
  const pos = start.clone().lerp(onCore, flow);
  if (status === "supported") {
    const gi = i % 6;
    const cell = new THREE.Vector3(1.25 + (gi % 3) * 0.5, 0.85 - Math.floor(gi / 3) * 0.48, 0.32);
    pos.lerp(cell, ramp(p, 0.68, 0.8));
    const report = new THREE.Vector3(2.15, -0.7 + gi * 0.12, 0.72);
    pos.lerp(report, ramp(p, 0.9, 1));
  } else if (status === "contradicted") {
    const jitter = Math.sin(p * 80 + i) * 0.03 * ramp(p, 0.5, 0.6) * (1 - ramp(p, 0.68, 0.72));
    pos.add(new THREE.Vector3(jitter, -jitter, 0));
    const risk = new THREE.Vector3(2.05, -0.15 + (i % 4) * 0.14, 0.72);
    pos.lerp(risk, ramp(p, 0.9, 1));
  } else if (status === "unsupported") {
    pos.y -= ramp(p, 0.6, 0.68) * 2.2;
  } else {
    const rev = new THREE.Vector3(2.1, -0.45, 0.72);
    pos.lerp(rev, ramp(p, 0.9, 1));
  }
  return pos;
}

function nodeAlpha(i: number, p: number): number {
  const status = NODES[i].status;
  const a = ramp(p, 0.1, 0.2);
  if (status === "unsupported") return a * (1 - ramp(p, 0.6, 0.68) * 0.85);
  return a;
}

/* ---------- Documents ---------- */
function Documents({ state, count, edges }: { state: SceneState; count: number; edges: boolean }) {
  const mesh = useRef<THREE.InstancedMesh>(null);
  const edgeRef = useRef<THREE.LineSegments>(null);
  const edgeGeo = useMemo(() => new THREE.EdgesGeometry(new THREE.PlaneGeometry(1, 1.3)), []);
  useFrame(() => {
    if (!mesh.current) return;
    for (let i = 0; i < count; i++) {
      const { pos, rot, scale } = docPose(i, count, state.p, state.frame.spread);
      tmp.position.copy(pos);
      tmp.rotation.copy(rot);
      tmp.scale.setScalar(scale);
      tmp.updateMatrix();
      mesh.current.setMatrixAt(i, tmp.matrix);
    }
    mesh.current.instanceMatrix.needsUpdate = true;
    const fade = 1 - ramp(state.p, 0.9, 1) * 0.9;
    (mesh.current.material as THREE.MeshStandardMaterial).opacity = 0.92 * fade;
    if (edgeRef.current) {
      const { pos, rot } = docPose(0, count, state.p, state.frame.spread);
      edgeRef.current.position.copy(pos);
      edgeRef.current.rotation.copy(rot);
      (edgeRef.current.material as THREE.LineBasicMaterial).opacity = 0.6 * fade;
    }
  });
  return (
    <group>
      <instancedMesh ref={mesh} args={[undefined, undefined, count]} frustumCulled={false} castShadow>
        <boxGeometry args={[1, 1.3, 0.012]} />
        <meshPhysicalMaterial map={getPaperTexture() ?? undefined} color={C.paper} roughness={0.82} metalness={0} sheen={0.4} sheenRoughness={0.9} clearcoat={0.05} />
      </instancedMesh>
      {edges && <lineSegments ref={edgeRef} geometry={edgeGeo}><lineBasicMaterial color={C.inkEdge} transparent opacity={0.6} /></lineSegments>}
    </group>
  );
}

/* ---------- Fragments (values lifting off pages and flowing into the core) ---------- */
function Fragments({ state, count }: { state: SceneState; count: number }) {
  const N = 48;
  const mesh = useRef<THREE.InstancedMesh>(null);
  const seeds = useMemo(() => Array.from({ length: N }, (_, i) => ({ doc: i % count, ox: ((i * 37) % 10) / 12 - 0.4, oy: ((i * 53) % 12) / 10 - 0.6, s: 0.5 + ((i * 7) % 5) / 8, ph: (i * 1.7) % 6.28 })), [count]);
  useFrame(() => {
    if (!mesh.current) return;
    const p = state.p;
    const lift = ramp(p, 0.1, 0.2);
    const flow = ramp(p, 0.2, 0.32);
    const gone = ramp(p, 0.3, 0.4);
    for (let i = 0; i < N; i++) {
      const s = seeds[i];
      const { pos } = docPose(s.doc, count, p, state.frame.spread);
      const start = pos.clone().add(new THREE.Vector3(s.ox, s.oy, 0.02));
      const lifted = start.clone().add(new THREE.Vector3(0, 0.35 * lift, 0.5 * lift));
      const ctrl = lifted.clone().lerp(new THREE.Vector3(0, 0.6, 1.4), 0.5).add(new THREE.Vector3(0, 0.6, 0));
      const target = new THREE.Vector3(Math.cos(s.ph) * 0.4, Math.sin(s.ph) * 0.4, 0.2);
      const a = lifted.clone().lerp(ctrl, flow), b = ctrl.clone().lerp(target, flow);
      const cur = a.lerp(b, flow);
      tmp.position.copy(cur);
      tmp.rotation.set(0, 0, s.ph * flow);
      tmp.scale.setScalar(0.12 * s.s * (1 - gone) * (0.2 + 0.8 * Math.min(1, lift * 3)));
      tmp.updateMatrix();
      mesh.current.setMatrixAt(i, tmp.matrix);
    }
    mesh.current.instanceMatrix.needsUpdate = true;
  });
  return (
    <instancedMesh ref={mesh} args={[undefined, undefined, N]} frustumCulled={false}>
      <planeGeometry args={[1, 0.45]} />
      <meshBasicMaterial color={C.signal} transparent opacity={0.85} side={THREE.DoubleSide} />
    </instancedMesh>
  );
}

/* ---------- Core: fresnel shell + inner wireframe ---------- */
const fresnelMaterial = () =>
  new THREE.ShaderMaterial({
    uniforms: { uColor: { value: C.signal.clone() }, uBody: { value: C.core.clone() }, uIntensity: { value: 0.4 }, uAlpha: { value: 0.35 } },
    vertexShader: `varying vec3 vN; varying vec3 vV; void main(){ vec4 wp = modelMatrix * vec4(position,1.0); vN = normalize(normalMatrix * normal); vV = normalize(cameraPosition - wp.xyz); gl_Position = projectionMatrix * viewMatrix * wp; }`,
    fragmentShader: `uniform vec3 uColor; uniform vec3 uBody; uniform float uIntensity; uniform float uAlpha; varying vec3 vN; varying vec3 vV; void main(){ float rim = pow(1.0 - max(dot(normalize(vN), normalize(vV)), 0.0), 2.4); vec3 c = mix(uBody, uColor, rim * uIntensity); gl_FragColor = vec4(c, uAlpha + 0.45 * rim); }`,
    transparent: true,
    depthWrite: false,
    side: THREE.FrontSide,
  });

function Core({ state, tier }: { state: SceneState; tier: Tier }) {
  const mat = useMemo(() => fresnelMaterial(), []);
  const group = useRef<THREE.Group>(null);
  const wire = useRef<THREE.Mesh>(null);
  const inner = useRef<THREE.Mesh>(null);
  const glass = useRef<THREE.Mesh>(null);
  useFrame((_, dt) => {
    const p = state.p;
    const t = performance.now() / 1000;
    const bright = 0.3 + ramp(p, 0.2, 0.32) * 0.9 - ramp(p, 0.9, 1) * 0.9;
    const pulse = ramp(p, 0.3, 0.34) * (1 - ramp(p, 0.34, 0.4));
    mat.uniforms.uIntensity.value = bright + pulse * 0.8 + Math.sin(t / 3) * 0.05;
    mat.uniforms.uAlpha.value = 0.35 * (1 - ramp(p, 0.9, 1));
    if (group.current) {
      const s = 1 - ramp(p, 0.68, 0.8) * 0.4;
      group.current.scale.setScalar(s * (1 + Math.sin(t / 6) * 0.02));
      group.current.position.x = -ramp(p, 0.68, 0.8) * 1.6;
      group.current.visible = p < 0.985;
    }
    if (wire.current) wire.current.rotation.y += dt * 0.08;
    if (inner.current) { inner.current.rotation.x -= dt * 0.05; inner.current.rotation.z += dt * 0.03; const m = inner.current.material as THREE.MeshStandardMaterial; m.emissiveIntensity = 0.6 + pulse * 2 + Math.sin(t * 1.3) * 0.15; }
    if (glass.current) { const m = glass.current.material as THREE.MeshPhysicalMaterial; m.opacity = 1 - ramp(p, 0.9, 1) * 0.9; }
  });
  return (
    <group ref={group}>
      {tier === 3 && (
        <mesh ref={glass}>
          <icosahedronGeometry args={[1.15, 4]} />
          <MeshTransmissionMaterial samples={6} resolution={512} thickness={0.6} roughness={0.12} ior={1.35} chromaticAberration={0.05} anisotropicBlur={0.2} distortion={0.15} distortionScale={0.4} temporalDistortion={0.1} color={C.paper} attenuationColor={C.signal} attenuationDistance={3} transparent />
        </mesh>
      )}
      {tier === 2 && (
        <mesh ref={glass}>
          <icosahedronGeometry args={[1.15, 4]} />
          <meshPhysicalMaterial transmission={0.9} thickness={0.5} roughness={0.15} ior={1.3} color={C.paper} attenuationColor={C.signal} attenuationDistance={2.5} transparent opacity={1} envMapIntensity={1.2} />
        </mesh>
      )}
      <mesh material={mat} scale={tier === 1 ? 1 : 1.02}><icosahedronGeometry args={[1.15, 3]} /></mesh>
      <mesh ref={inner}><icosahedronGeometry args={[0.42, 2]} /><meshStandardMaterial color={C.signal} emissive={C.signal} emissiveIntensity={0.8} roughness={0.4} /></mesh>
      {tier > 1 && (<mesh ref={wire}><icosahedronGeometry args={[0.95, 1]} /><meshBasicMaterial color={C.inkEdge} wireframe transparent opacity={0.45} /></mesh>)}
    </group>
  );
}

/* ---------- Claim nodes ---------- */
function ClaimNodes({ state, docCount, onSelect }: { state: SceneState; docCount: number; onSelect: (i: number | null) => void }) {
  const mesh = useRef<THREE.InstancedMesh>(null);
  const colorAttr = useMemo(() => new Float32Array(NODES.length * 3), []);
  useEffect(() => {
    if (!mesh.current) return;
    NODES.forEach((n, i) => STATUS_COLOR[n.status].toArray(colorAttr, i * 3));
    mesh.current.instanceColor = new THREE.InstancedBufferAttribute(colorAttr, 3);
  }, [colorAttr]);
  useFrame(() => {
    if (!mesh.current) return;
    const p = state.p;
    const t = performance.now() / 1000;
    for (let i = 0; i < NODES.length; i++) {
      const n = NODES[i];
      const doc = docPose(n.doc % docCount, docCount, p, state.frame.spread).pos;
      const pos = nodePose(i, p, doc);
      const a = nodeAlpha(i, p);
      let s = 0.09 * a;
      if (n.hero) s *= 1.35;
      if (n.status === "contradicted") s *= 1 + Math.sin(t * 5) * 0.08 * ramp(p, 0.5, 0.6) * (1 - ramp(p, 0.68, 0.72));
      if (state.selected === i || state.hover === i) s *= 1.5;
      tmp.position.copy(pos);
      tmp.rotation.set(0, 0, 0);
      tmp.scale.setScalar(Math.max(0.0001, s));
      tmp.updateMatrix();
      mesh.current.setMatrixAt(i, tmp.matrix);
      tmpColor.copy(NEUTRAL).lerp(STATUS_COLOR[n.status], statusReveal(n.status, p)).toArray(colorAttr, i * 3);
    }
    mesh.current.instanceMatrix.needsUpdate = true;
    if (mesh.current.instanceColor) mesh.current.instanceColor.needsUpdate = true;
  });
  return (
    <instancedMesh ref={mesh} args={[undefined, undefined, NODES.length]} frustumCulled={false} onClick={(e) => { e.stopPropagation(); onSelect(e.instanceId ?? null); }} onPointerOver={(e) => { state.hover = e.instanceId ?? null; document.body.style.cursor = "pointer"; }} onPointerOut={() => { state.hover = null; document.body.style.cursor = ""; }}>
      <sphereGeometry args={[1, 20, 20]} />
      <meshPhysicalMaterial roughness={0.35} metalness={0.05} clearcoat={0.6} clearcoatRoughness={0.3} />
    </instancedMesh>
  );
}

/* ---------- Links: hairlines from nodes to their document points ---------- */
function Links({ state, docCount }: { state: SceneState; docCount: number }) {
  const geo = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(NODES.length * 6), 3));
    g.setAttribute("color", new THREE.BufferAttribute(new Float32Array(NODES.length * 6), 3));
    return g;
  }, []);
  useFrame(() => {
    const p = state.p;
    const pos = geo.attributes.position as THREE.BufferAttribute;
    const col = geo.attributes.color as THREE.BufferAttribute;
    const draw = ramp(p, 0.3, 0.42);
    const t = performance.now() / 1000;
    for (let i = 0; i < NODES.length; i++) {
      const n = NODES[i];
      const doc = docPose(n.doc % docCount, docCount, p, state.frame.spread).pos;
      const a = nodePose(i, p, doc);
      const target = doc.clone().add(new THREE.Vector3(0.1, 0.25, 0.05));
      let vis = draw;
      if (n.status === "unsupported") vis *= 1 - ramp(p, 0.6, 0.66);
      if (n.status === "supported" && p > 0.68) target.lerp(new THREE.Vector3(-1.6, 0.2, 0.4), ramp(p, 0.68, 0.8));
      vis *= 1 - ramp(p, 0.92, 1) * 0.8;
      const b = a.clone().lerp(target, vis);
      pos.setXYZ(i * 2, a.x, a.y, a.z);
      pos.setXYZ(i * 2 + 1, b.x, b.y, b.z);
      const base = tmpColor.copy(NEUTRAL).lerp(STATUS_COLOR[n.status], statusReveal(n.status, p));
      const active = state.selected === i || state.hover === i;
      let k = active ? 1 : n.hero ? 0.8 : 0.55;
      if (n.status === "contradicted") k *= 0.7 + 0.3 * Math.abs(Math.sin(t * 2.5)) * ramp(p, 0.5, 0.6) + (active ? 0.3 : 0);
      base.multiplyScalar(k);
      col.setXYZ(i * 2, base.r, base.g, base.b);
      col.setXYZ(i * 2 + 1, base.r, base.g, base.b);
    }
    pos.needsUpdate = true;
    col.needsUpdate = true;
  });
  return (<lineSegments geometry={geo}><lineBasicMaterial vertexColors transparent opacity={0.9} /></lineSegments>);
}

/* ---------- Model grid + covenant rule ---------- */
function ModelGrid({ state }: { state: SceneState }) {
  const mesh = useRef<THREE.InstancedMesh>(null);
  const rule = useRef<THREE.Mesh>(null);
  const marker = useRef<THREE.Mesh>(null);
  const colors = useMemo(() => new Float32Array(36 * 3), []);
  useEffect(() => {
    if (!mesh.current) return;
    for (let i = 0; i < 36; i++) C.paper.clone().multiplyScalar(0.85 - Math.floor(i / 6) * 0.06).toArray(colors, i * 3);
    mesh.current.instanceColor = new THREE.InstancedBufferAttribute(colors, 3);
  }, [colors]);
  useFrame(() => {
    if (!mesh.current) return;
    const p = state.p;
    const assemble = ramp(p, 0.68, 0.82);
    const down = ramp(p, 0.8, 0.9);
    const compress = ramp(p, 0.9, 1);
    for (let i = 0; i < 36; i++) {
      const r = Math.floor(i / 6), c = i % 6;
      const delay = (r * 6 + c) / 36;
      const k = Math.max(0, Math.min(1, (assemble - delay * 0.5) / 0.5));
      const sink = r === 4 ? down * 0.28 : 0;
      tmp.position.set(1.05 + c * 0.38 * (1 - compress * 0.5) + compress * 1.3, 1.05 - r * 0.34 + (1 - k) * 0.6 - sink + compress * 0.3, 0.3 - (1 - k) * 1.5 - compress * 2.2);
      tmp.rotation.set(0, 0, 0);
      tmp.scale.set(0.32 * k, 0.26 * k, 0.05 * k);
      tmp.updateMatrix();
      mesh.current.setMatrixAt(i, tmp.matrix);
      const target = r === 4 && down > 0 ? C.amber.clone().lerp(C.red, ramp(p, 0.86, 0.9)) : C.paper.clone().multiplyScalar(0.85 - r * 0.06);
      target.toArray(colors, i * 3);
    }
    mesh.current.instanceMatrix.needsUpdate = true;
    if (mesh.current.instanceColor) mesh.current.instanceColor.needsUpdate = true;
    if (rule.current) {
      rule.current.visible = down > 0.01 && compress < 0.99;
      rule.current.position.set(2.0 + compress * 1.3, 1.05 - 4 * 0.34 + 0.13 - down * 0.28 + compress * 0.3, 0.36 - compress * 2.2);
      (rule.current.material as THREE.MeshBasicMaterial).color.copy(C.amber).lerp(C.red, ramp(p, 0.86, 0.9));
      (rule.current.material as THREE.MeshBasicMaterial).opacity = 0.9 * down * (1 - compress);
    }
    if (marker.current) {
      marker.current.visible = down > 0.5 && compress < 0.99;
      marker.current.position.set(0.75, 1.05 - 4 * 0.34 - down * 0.28, 0.4);
      marker.current.scale.setScalar(ramp(p, 0.85, 0.9) * 0.16);
    }
  });
  return (
    <group>
      <instancedMesh ref={mesh} args={[undefined, undefined, 36]} frustumCulled={false} castShadow><boxGeometry args={[1, 1, 1]} /><meshPhysicalMaterial roughness={0.55} clearcoat={0.2} /></instancedMesh>
      <mesh ref={rule}><planeGeometry args={[2.3, 0.02]} /><meshBasicMaterial color={C.amber} transparent opacity={0} /></mesh>
      <mesh ref={marker} rotation={[0, 0, 0]}><coneGeometry args={[1, 1.6, 3]} /><meshBasicMaterial color={C.red} /></mesh>
    </group>
  );
}

/* ---------- Report stack ---------- */
function ReportStack({ state }: { state: SceneState }) {
  const mesh = useRef<THREE.InstancedMesh>(null);
  useFrame(() => {
    if (!mesh.current) return;
    const k = ramp(state.p, 0.9, 1);
    for (let i = 0; i < 4; i++) {
      const d = Math.max(0, Math.min(1, (k - i * 0.15) / 0.55));
      tmp.position.set(2.1 + i * 0.03, -0.75 + i * 0.05 + (1 - d) * 0.5, 0.6 - i * 0.02);
      tmp.rotation.set(-0.08, -0.25, 0);
      tmp.scale.setScalar(d);
      tmp.updateMatrix();
      mesh.current.setMatrixAt(i, tmp.matrix);
    }
    mesh.current.instanceMatrix.needsUpdate = true;
  });
  return (
    <instancedMesh ref={mesh} args={[undefined, undefined, 4]} frustumCulled={false} castShadow><boxGeometry args={[1.1, 1.4, 0.012]} /><meshPhysicalMaterial map={getPaperTexture() ?? undefined} color={C.paper} roughness={0.82} sheen={0.4} sheenRoughness={0.9} /></instancedMesh>
  );
}

/* ---------- Particles with pointer displacement ---------- */
function Particles({ state, count }: { state: SceneState; count: number }) {
  const ref = useRef<THREE.Points>(null);
  const { base, geo } = useMemo(() => {
    const base = new Float32Array(count * 3);
    let seed = 1234567;
    const rnd = () => { seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296; }; // deterministic LCG
    for (let i = 0; i < count; i++) { base[i * 3] = (rnd() - 0.5) * 14; base[i * 3 + 1] = (rnd() - 0.5) * 8; base[i * 3 + 2] = (rnd() - 0.5) * 8 - 1; }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(base.slice(), 3));
    return { base, geo };
  }, [count]);
  const { camera } = useThree();
  const ray = useMemo(() => new THREE.Raycaster(), []);
  useFrame((_, dt) => {
    const attr = geo.attributes.position as THREE.BufferAttribute;
    const arr = attr.array as Float32Array;
    ray.setFromCamera(state.pointer, camera);
    const t = performance.now() / 1000;
    for (let i = 0; i < count; i++) {
      v3.set(base[i * 3], base[i * 3 + 1], base[i * 3 + 2]);
      const drift = Math.sin(t * 0.2 + i) * 0.05;
      const d = ray.ray.distanceToPoint(v3);
      let px = v3.x + drift, py = v3.y + Math.cos(t * 0.15 + i) * 0.05, pz = v3.z;
      if (d < 0.8) {
        const push = (0.8 - d) * 0.25;
        const closest = ray.ray.closestPointToPoint(v3, new THREE.Vector3());
        const dir = v3.clone().sub(closest).normalize();
        px += dir.x * push; py += dir.y * push; pz += dir.z * push;
      }
      const k = 1 - Math.exp(-dt * 6);
      arr[i * 3] += (px - arr[i * 3]) * k;
      arr[i * 3 + 1] += (py - arr[i * 3 + 1]) * k;
      arr[i * 3 + 2] += (pz - arr[i * 3 + 2]) * k;
    }
    attr.needsUpdate = true;
  });
  return (<points ref={ref} geometry={geo} frustumCulled={false}><pointsMaterial color={C.paper} size={0.045} sizeAttenuation transparent opacity={0.55} depthWrite={false} map={getSprite() ?? undefined} alphaMap={getSprite() ?? undefined} blending={THREE.AdditiveBlending} /></points>);
}

/* ---------- Rig: parallax, drag, recenter, late-stage fit, quality watchdog ---------- */
function Rig({ state, children }: { state: SceneState; children: React.ReactNode }) {
  const group = useRef<THREE.Group>(null);
  const yaw = useRef(0), pitch = useRef(0);
  const frames = useRef<number[]>([]);
  useFrame((_, dt) => {
    if (!group.current) return;
    const t = performance.now() / 1000;
    const idleYaw = Math.sin(t / 12) * 0.05;
    const targetYaw = state.pointer.x * 0.1 + state.drag.x + idleYaw;
    const targetPitch = -state.pointer.y * 0.07 + state.drag.y;
    yaw.current = THREE.MathUtils.damp(yaw.current, THREE.MathUtils.clamp(targetYaw, -0.45, 0.45), 4, dt);
    pitch.current = THREE.MathUtils.damp(pitch.current, THREE.MathUtils.clamp(targetPitch, -0.22, 0.22), 4, dt);
    group.current.rotation.set(pitch.current, yaw.current, 0);
    group.current.scale.setScalar(1 - ramp(state.p, 0.68, 0.8) * (1 - state.frame.fit));
    state.drag.x = THREE.MathUtils.damp(state.drag.x, 0, 1.2, dt);
    state.drag.y = THREE.MathUtils.damp(state.drag.y, 0, 1.2, dt);
    // Quality watchdog: average frame time over ~90 frames; a hidden tab or a debugger pause produces one huge delta, which is not a slow GPU.
    if (dt < 0.1) frames.current.push(dt);
    if (frames.current.length >= 90) {
      const avg = frames.current.reduce((a, b) => a + b, 0) / frames.current.length;
      frames.current = [];
      if (avg > 0.022) state.degrade();
    }
  });
  return <group ref={group}>{children}</group>;
}

function Scene({ state, story, tier, post, onSelect, selected }: { state: SceneState; story: SceneStore; tier: Tier; post: boolean; onSelect: (i: number | null) => void; selected: number | null }) {
  const q = TIERS[tier];
  const node = selected !== null ? NODES[selected] : null;
  const docCount = q.docs;
  return (
    <>
      <color attach="background" args={["#07080A"]} />
      <fog attach="fog" args={["#07080A", 9, 22]} />
      <ambientLight intensity={0.25} color={C.paper} />
      <directionalLight position={[4, 6, 5]} intensity={1.4} castShadow={tier === 3} shadow-mapSize={[1024, 1024]} shadow-bias={-0.0005} />
      <pointLight position={[-5, 2, -3]} intensity={1.2} color={C.signal} distance={14} decay={2} />
      <pointLight position={[3, -2, 4]} intensity={0.5} color={C.amber} distance={10} decay={2} />
      {tier > 1 && (
        <Environment resolution={256} frames={1}>
          <Lightformer intensity={1.6} form="rect" scale={[6, 3, 1]} position={[0, 5, -4]} color="#F5F2EC" />
          <Lightformer intensity={0.8} form="circle" scale={[3, 3, 1]} position={[-6, 2, 3]} color="#7FB2FF" />
          <Lightformer intensity={0.5} form="rect" scale={[4, 1, 1]} position={[6, -1, 2]} color="#F5F2EC" />
        </Environment>
      )}
      {tier > 1 && <ContactShadows position={[0, -2.6, 0]} opacity={0.55} scale={22} blur={2.4} far={6} color="#000" frames={1} />}
      <Framing state={state} story={story} />
      <Rig state={state}>
        <Documents state={state} count={docCount} edges={q.edges} />
        {tier > 1 && <Fragments state={state} count={docCount} />}
        <Core state={state} tier={tier} />
        <Links state={state} docCount={docCount} />
        <ClaimNodes state={state} docCount={docCount} onSelect={onSelect} />
        <ModelGrid state={state} />
        <ReportStack state={state} />
        <Particles state={state} count={q.particles} />
        {node && selected !== null && (
          <NodeAnchor state={state} index={selected} docCount={docCount}>
          <Html center distanceFactor={8} zIndexRange={[30, 0]} style={{ pointerEvents: "auto" }}>
            <div role="dialog" aria-label={node.label} className="w-56 rounded-[var(--radius-2)] border border-ink-600 bg-ink-900/95 p-3 text-paper-50 shadow-lg" style={{ fontFamily: "var(--font-sans)" }}>
              <p className="micro" style={{ color: STATUS_COLOR[node.status].getStyle() }}>{node.status === "review" ? "review required" : node.status}</p>
              <p className="mt-1 text-sm leading-snug">{node.label}</p>
              <p className="mt-1 text-xs text-graphite-400">{node.value} · {DOC_LABELS[node.doc]}</p>
              <button type="button" className="mt-2 text-xs text-signal-400 underline-offset-2 hover:underline" onClick={() => onSelect(null)}>Close</button>
            </div>
          </Html>
          </NodeAnchor>
        )}
      </Rig>
      {post && (
        <EffectComposer multisampling={0} enableNormalPass={false}>
          <Bloom intensity={tier === 3 ? 0.55 : 0.4} luminanceThreshold={0.72} luminanceSmoothing={0.25} mipmapBlur />
          <Vignette eskil={false} offset={0.2} darkness={0.55} />
        </EffectComposer>
      )}
    </>
  );
}

/** Frames the composition inside the free region every frame (runs before the entities, priority −1), then the slow dolly-in
 *  and gentle lift as the story progresses. Writes `state.frame` for the rig and the document arc and drives the camera.
 *  A world point X appears at viewport fraction f when the camera axis is at X − (f − 0.5) · 2 · halfWidth. */
function Framing({ state, story }: { state: SceneState; story: SceneStore }) {
  const { camera } = useThree();
  useFrame(({ size }, dt) => {
    const p = state.p;
    const f = state.frame;
    const r = story.region;
    const aspect = size.width / Math.max(1, size.height);
    const late = ramp(p, 0.68, 1);
    const zBase = 9.8 + THREE.MathUtils.clamp((1.2 - aspect) * 4, 0, 3) + THREE.MathUtils.clamp((aspect - 1) * 3, 0, 0.6);
    const z = zBase - ramp(p, 0, 0.6) * 0.8 + ramp(p, 0.68, 0.9) * 0.6;
    const halfH = z * TAN_HALF_FOV, halfW = halfH * aspect;
    const spread = 1 - THREE.MathUtils.clamp((aspect - 1.15) * 0.5, 0, 0.25);
    const fit = THREE.MathUtils.clamp(((r.right - r.left) * 2 * halfW * 0.9) / CLUSTER_WIDTH, 0.55, 0.85);
    // Chapters 1–2: the core in the free region, no further from the middle than it takes to clear the copy by its radius.
    const coreFrac = 1.15 / (2 * halfW);
    const cx12 = Math.min((r.left + r.right) / 2, Math.max(0.5, r.left + coreFrac + 0.03));
    const cx3 = (r.left + r.right) / 2;
    const cy = (r.top + r.bottom) / 2;
    const axisX = THREE.MathUtils.lerp(-(cx12 - 0.5) * 2 * halfW, CLUSTER_CENTER.x * fit - (cx3 - 0.5) * 2 * halfW, late);
    const axisY = THREE.MathUtils.lerp(0, CLUSTER_CENTER.y * fit, late) + (cy - 0.5) * 2 * halfH;
    if (!f.settled) { f.axisX = axisX; f.axisY = axisY; f.z = z; f.settled = true; }
    f.axisX = THREE.MathUtils.damp(f.axisX, axisX, 2.5, dt);
    f.axisY = THREE.MathUtils.damp(f.axisY, axisY, 2.5, dt);
    f.z = THREE.MathUtils.damp(f.z, z, 2.5, dt);
    f.spread = spread;
    f.fit = fit;
    camera.position.set(f.axisX, f.axisY + 0.4 - late * 0.35, f.z);
    camera.lookAt(f.axisX, f.axisY, 0);
  }, -1);
  return null;
}

/** Counts rendered frames: the first one tells the hero the canvas is drawn (crossfade the static image out); the `warmAfter`th
 *  turns post-processing on, so bloom and vignette are paid for only after the scene has been visible and stable. Frames only
 *  run while the canvas is on screen (`frameloop="demand"` offscreen), so both callbacks imply visibility. */
function FrameCounter({ onFirst, onWarm, warmAfter }: { onFirst: () => void; onWarm: () => void; warmAfter: number }) {
  const n = useRef(0);
  useFrame(() => {
    n.current += 1;
    if (n.current === 1) onFirst();
    else if (n.current === warmAfter) onWarm();
  });
  return null;
}

export function EvidenceCoreScene({ story, mobile, onReady, onFail }: { story: SceneStore; mobile: boolean; onReady: () => void; onFail: () => void }) {
  const [tier, setTier] = useState<Tier>(() => detectTier(mobile));
  const [selected, setSelected] = useState<number | null>(null);
  const [visible, setVisible] = useState(false);
  const [warm, setWarm] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const alive = useRef(true);
  const [state] = useState<SceneState>(() => ({ p: 0, pointer: new THREE.Vector2(0, 0), drag: new THREE.Vector2(0, 0), selected: null, hover: null, frame: { spread: 1, fit: 1, axisX: 0, axisY: 0, z: 9.8, settled: false }, degrade: () => setTier((t) => (t > 1 ? ((t - 1) as Tier) : t)) }));
  useEffect(() => { state.selected = selected; }, [selected, state]);
  // Unmounting the canvas (Pause 3D) makes R3F force a context loss; that is not a failure, so the handler below ignores loss on a canvas that is no longer live.
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
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setSelected(null); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const q = TIERS[tier];
  return (
    <div ref={wrap} className="h-full w-full" style={{ touchAction: "pan-y" }} onPointerMove={onPointerMove} onPointerDown={(e) => { if (e.pointerType === "mouse" && e.button !== 0) return; dragging.current = { x: e.clientX, y: e.clientY }; }} onPointerUp={() => { dragging.current = null; }} onPointerLeave={() => { dragging.current = null; state.pointer.set(0, 0); }}>
      <Canvas dpr={[1, q.dpr]} frameloop={visible ? "always" : "demand"} shadows={tier === 3 ? { type: THREE.PCFShadowMap } : false} gl={{ antialias: q.aa, powerPreference: "high-performance", alpha: false, toneMapping: THREE.ACESFilmicToneMapping, toneMappingExposure: 1.05 }} camera={{ fov: 32, position: [0, 0.4, 9], near: 0.1, far: 60 }} onCreated={({ gl }) => { gl.domElement.addEventListener("webglcontextlost", (ev) => { ev.preventDefault(); if (alive.current && gl.domElement.isConnected) onFail(); }); }} onPointerMissed={() => setSelected(null)} aria-label="The Evidence Core: a seller's claim of 18% growth leaves the memo, the income statement shows 11.6% and the claim turns contradicted, then the verified figures assemble into a financial model, a downside case, and a report" role="img">
        <FrameCounter onFirst={onReady} onWarm={() => setWarm(true)} warmAfter={8} />
        <ProgressDriver state={state} story={story} />
        <Scene state={state} story={story} tier={tier} post={warm && tier > 1} onSelect={setSelected} selected={selected} />
      </Canvas>
      <ul className="sr-only" aria-label="Claims in the scene">
        {NODES.map((n, i) => <li key={n.id}><button type="button" onClick={() => setSelected(i)}>{n.label}: {n.status === "review" ? "review required" : n.status}</button></li>)}
      </ul>
    </div>
  );
}

/** Follows a claim node each frame so the DOM tooltip stays attached without re-rendering React. */
function NodeAnchor({ state, index, docCount, children }: { state: SceneState; index: number; docCount: number; children: React.ReactNode }) {
  const g = useRef<THREE.Group>(null);
  useFrame(() => {
    if (!g.current) return;
    const doc = docPose(NODES[index].doc % docCount, docCount, state.p, state.frame.spread).pos;
    g.current.position.copy(nodePose(index, state.p, doc));
  });
  return <group ref={g}>{children}</group>;
}

/** Eases storyboard progress toward the scroll-driven target each frame; reads the store directly, so scrolling never re-renders React here. */
function ProgressDriver({ state, story }: { state: SceneState; story: SceneStore }) {
  useFrame((_, dt) => { state.p = THREE.MathUtils.damp(state.p, storyProgress(story.get()), 6, dt); });
  return null;
}
