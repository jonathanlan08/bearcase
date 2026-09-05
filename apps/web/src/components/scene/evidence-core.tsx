"use client";
/* eslint-disable react-hooks/immutability -- imperative render loop: one shared mutable SceneState
   object is written by useFrame callbacks (never during render) and read by every entity each frame. This is the
   standard React Three Fiber pattern and avoids re-rendering React on every frame. */

import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { DOC_LABELS, NODES, ramp, type Status } from "@/components/scene/storyboard";

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

/* ---------- shared, mutable scene state (one object, updated per frame) ---------- */
interface SceneState { p: number; pointer: THREE.Vector2; drag: THREE.Vector2; selected: number | null; hover: number | null; degrade: () => void }

const tmp = new THREE.Object3D();
const v3 = new THREE.Vector3();

/* Document anchor positions (arc in front of the core), and their target "recede" positions. */
function docPose(i: number, n: number, p: number): { pos: THREE.Vector3; rot: THREE.Euler; scale: number } {
  const t = n === 1 ? 0.5 : i / (n - 1);
  const angle = (t - 0.5) * Math.PI * 0.9;
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
    const cell = new THREE.Vector3(1.9 + (gi % 3) * 0.55, 0.8 - Math.floor(gi / 3) * 0.5, 0.3);
    pos.lerp(cell, ramp(p, 0.68, 0.8));
    const report = new THREE.Vector3(2.55, -0.85 + gi * 0.12, 0.62);
    pos.lerp(report, ramp(p, 0.9, 1));
  } else if (status === "contradicted") {
    const jitter = Math.sin(p * 80 + i) * 0.03 * ramp(p, 0.5, 0.6) * (1 - ramp(p, 0.68, 0.72));
    pos.add(new THREE.Vector3(jitter, -jitter, 0));
    const risk = new THREE.Vector3(2.45, -0.3 + (i % 4) * 0.14, 0.62);
    pos.lerp(risk, ramp(p, 0.9, 1));
  } else if (status === "unsupported") {
    pos.y -= ramp(p, 0.6, 0.68) * 2.2;
  } else {
    const rev = new THREE.Vector3(2.5, -0.6, 0.62);
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
      const { pos, rot, scale } = docPose(i, count, state.p);
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
      const { pos, rot } = docPose(0, count, state.p);
      edgeRef.current.position.copy(pos);
      edgeRef.current.rotation.copy(rot);
      (edgeRef.current.material as THREE.LineBasicMaterial).opacity = 0.6 * fade;
    }
  });
  return (
    <group>
      <instancedMesh ref={mesh} args={[undefined, undefined, count]} frustumCulled={false}>
        <planeGeometry args={[1, 1.3]} />
        <meshStandardMaterial map={getPaperTexture() ?? undefined} color={C.paper} roughness={0.9} metalness={0} transparent opacity={0.94} side={THREE.DoubleSide} emissive={C.core} emissiveIntensity={0.15} />
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
      const { pos } = docPose(s.doc, count, p);
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

function Core({ state, simplified }: { state: SceneState; simplified: boolean }) {
  const mat = useMemo(() => fresnelMaterial(), []);
  const group = useRef<THREE.Group>(null);
  const wire = useRef<THREE.Mesh>(null);
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
    }
    if (wire.current) wire.current.rotation.y += dt * 0.08;
  });
  return (
    <group ref={group}>
      <mesh material={mat}><icosahedronGeometry args={[1.15, 3]} /></mesh>
      {!simplified && (<mesh ref={wire}><icosahedronGeometry args={[0.95, 1]} /><meshBasicMaterial color={C.inkEdge} wireframe transparent opacity={0.5} /></mesh>)}
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
      const doc = docPose(NODES[i].doc % docCount, docCount, p).pos;
      const pos = nodePose(i, p, doc);
      const a = nodeAlpha(i, p);
      let s = 0.09 * a;
      if (NODES[i].status === "contradicted") s *= 1 + Math.sin(t * 5) * 0.08 * ramp(p, 0.5, 0.6) * (1 - ramp(p, 0.68, 0.72));
      if (state.selected === i || state.hover === i) s *= 1.5;
      tmp.position.copy(pos);
      tmp.rotation.set(0, 0, 0);
      tmp.scale.setScalar(Math.max(0.0001, s));
      tmp.updateMatrix();
      mesh.current.setMatrixAt(i, tmp.matrix);
    }
    mesh.current.instanceMatrix.needsUpdate = true;
  });
  return (
    <instancedMesh ref={mesh} args={[undefined, undefined, NODES.length]} frustumCulled={false} onClick={(e) => { e.stopPropagation(); onSelect(e.instanceId ?? null); }} onPointerOver={(e) => { state.hover = e.instanceId ?? null; document.body.style.cursor = "pointer"; }} onPointerOut={() => { state.hover = null; document.body.style.cursor = ""; }}>
      <sphereGeometry args={[1, 16, 16]} />
      <meshStandardMaterial roughness={0.6} metalness={0.1} />
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
      const doc = docPose(n.doc % docCount, docCount, p).pos;
      const a = nodePose(i, p, doc);
      const target = doc.clone().add(new THREE.Vector3(0.1, 0.25, 0.05));
      let vis = draw;
      if (n.status === "unsupported") vis *= 1 - ramp(p, 0.6, 0.66);
      if (n.status === "supported" && p > 0.68) target.lerp(new THREE.Vector3(-1.6 - ramp(p, 0.68, 0.8) * 0, 0.2, 0.4), ramp(p, 0.68, 0.8));
      vis *= 1 - ramp(p, 0.92, 1) * 0.8;
      const b = a.clone().lerp(target, vis);
      pos.setXYZ(i * 2, a.x, a.y, a.z);
      pos.setXYZ(i * 2 + 1, b.x, b.y, b.z);
      const base = STATUS_COLOR[n.status].clone();
      const active = state.selected === i || state.hover === i;
      let k = active ? 1 : 0.55;
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
      tmp.position.set(1.6 + c * 0.42 * (1 - compress * 0.6) + compress * 0.9, 1.0 - r * 0.36 + (1 - k) * 0.6 - sink - compress * 0.5, 0.3 - (1 - k) * 1.5);
      tmp.rotation.set(0, 0, 0);
      tmp.scale.set(0.36 * k, 0.28 * k, 0.05 * k);
      tmp.updateMatrix();
      mesh.current.setMatrixAt(i, tmp.matrix);
      const target = r === 4 && down > 0 ? C.amber.clone().lerp(C.red, ramp(p, 0.86, 0.9)) : C.paper.clone().multiplyScalar(0.85 - r * 0.06);
      target.toArray(colors, i * 3);
    }
    mesh.current.instanceMatrix.needsUpdate = true;
    if (mesh.current.instanceColor) mesh.current.instanceColor.needsUpdate = true;
    if (rule.current) {
      rule.current.visible = down > 0.01 && compress < 0.99;
      rule.current.position.set(2.65 + compress * 0.9, 1.0 - 4 * 0.36 + 0.14 - down * 0.28 - compress * 0.5, 0.36);
      (rule.current.material as THREE.MeshBasicMaterial).color.copy(C.amber).lerp(C.red, ramp(p, 0.86, 0.9));
      (rule.current.material as THREE.MeshBasicMaterial).opacity = 0.9 * down * (1 - compress);
    }
    if (marker.current) {
      marker.current.visible = down > 0.5 && compress < 0.99;
      marker.current.position.set(1.25, 1.0 - 4 * 0.36 - down * 0.28, 0.4);
      marker.current.scale.setScalar(ramp(p, 0.85, 0.9) * 0.16);
    }
  });
  return (
    <group>
      <instancedMesh ref={mesh} args={[undefined, undefined, 36]} frustumCulled={false}><boxGeometry args={[1, 1, 1]} /><meshStandardMaterial roughness={0.7} /></instancedMesh>
      <mesh ref={rule}><planeGeometry args={[2.6, 0.02]} /><meshBasicMaterial color={C.amber} transparent opacity={0} /></mesh>
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
      tmp.position.set(2.5 + i * 0.03, -0.9 + i * 0.05 + (1 - d) * 0.5, 0.5 - i * 0.02);
      tmp.rotation.set(-0.08, -0.25, 0);
      tmp.scale.setScalar(d);
      tmp.updateMatrix();
      mesh.current.setMatrixAt(i, tmp.matrix);
    }
    mesh.current.instanceMatrix.needsUpdate = true;
  });
  return (
    <instancedMesh ref={mesh} args={[undefined, undefined, 4]} frustumCulled={false}><planeGeometry args={[1.1, 1.4]} /><meshStandardMaterial map={getPaperTexture() ?? undefined} color={C.paper} roughness={0.9} transparent opacity={0.95} side={THREE.DoubleSide} /></instancedMesh>
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
  return (<points ref={ref} geometry={geo} frustumCulled={false}><pointsMaterial color={C.paper} size={0.02} sizeAttenuation transparent opacity={0.5} depthWrite={false} /></points>);
}

/* ---------- Rig: parallax, drag, recenter, quality watchdog ---------- */
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
    state.drag.x = THREE.MathUtils.damp(state.drag.x, 0, 1.2, dt);
    state.drag.y = THREE.MathUtils.damp(state.drag.y, 0, 1.2, dt);
    frames.current.push(dt);
    if (frames.current.length >= 90) {
      const avg = frames.current.reduce((a, b) => a + b, 0) / frames.current.length;
      frames.current = [];
      if (avg > 0.022) state.degrade();
    }
  });
  return <group ref={group}>{children}</group>;
}

function Scene({ state, tier, onSelect, selected }: { state: SceneState; tier: Tier; onSelect: (i: number | null) => void; selected: number | null }) {
  const q = TIERS[tier];
  const node = selected !== null ? NODES[selected] : null;
  const docCount = q.docs;
  return (
    <>
      <color attach="background" args={["#07080A"]} />
      <ambientLight intensity={0.35} color={C.paper} />
      <directionalLight position={[4, 6, 5]} intensity={1.1} />
      <pointLight position={[-5, 2, -3]} intensity={0.6} color={C.signal} />
      <Rig state={state}>
        <Documents state={state} count={docCount} edges={q.edges} />
        {tier > 1 && <Fragments state={state} count={docCount} />}
        <Core state={state} simplified={tier === 1} />
        <Links state={state} docCount={docCount} />
        <ClaimNodes state={state} docCount={docCount} onSelect={onSelect} />
        <ModelGrid state={state} />
        <ReportStack state={state} />
        <Particles state={state} count={q.particles} />
        {node && selected !== null && (
          <NodeAnchor state={state} index={selected} docCount={docCount}>
          <Html center distanceFactor={8} zIndexRange={[30, 0]} style={{ pointerEvents: "auto" }}>
            <div role="dialog" aria-label={node.label} className="w-56 rounded-[6px] border border-ink-600 bg-ink-900/95 p-3 text-paper-50 shadow-lg" style={{ fontFamily: "var(--font-sans)" }}>
              <p className="micro" style={{ color: STATUS_COLOR[node.status].getStyle() }}>{node.status === "review" ? "review required" : node.status}</p>
              <p className="mt-1 text-sm leading-snug">{node.label}</p>
              <p className="mt-1 text-xs text-graphite-400">{node.value} · {DOC_LABELS[node.doc]}</p>
              <button type="button" className="mt-2 text-xs text-signal-400 underline-offset-2 hover:underline" onClick={() => onSelect(null)}>Close</button>
            </div>
          </Html>
          </NodeAnchor>
        )}
      </Rig>
    </>
  );
}

export function EvidenceCoreScene({ progress, mobile, onReady, onFail }: { progress: number; mobile: boolean; onReady: () => void; onFail: () => void }) {
  const [tier, setTier] = useState<Tier>(() => detectTier(mobile));
  const [selected, setSelected] = useState<number | null>(null);
  const [visible, setVisible] = useState(true);
  const wrap = useRef<HTMLDivElement>(null);
  const [state] = useState<SceneState>(() => ({ p: 0, pointer: new THREE.Vector2(0, 0), drag: new THREE.Vector2(0, 0), selected: null, hover: null, degrade: () => setTier((t) => (t > 1 ? ((t - 1) as Tier) : t)) }));
  const target = useRef(0);
  useEffect(() => { target.current = progress; }, [progress]);
  useEffect(() => { state.selected = selected; }, [selected, state]);
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
      <Canvas dpr={[1, q.dpr]} frameloop={visible ? "always" : "demand"} gl={{ antialias: q.aa, powerPreference: "high-performance", alpha: false }} camera={{ fov: 32, position: [0, 0.4, 9], near: 0.1, far: 60 }} onCreated={({ gl }) => { gl.domElement.addEventListener("webglcontextlost", (ev) => { ev.preventDefault(); onFail(); }); onReady(); }} onPointerMissed={() => setSelected(null)} aria-label="The Evidence Core: deal documents become sourced claims, contradictions, a verified financial model, a downside scenario, and a report" role="img">
        <ProgressDriver state={state} target={target} />
        <Scene state={state} tier={tier} onSelect={setSelected} selected={selected} />
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
    const doc = docPose(NODES[index].doc % docCount, docCount, state.p).pos;
    g.current.position.copy(nodePose(index, state.p, doc));
  });
  return <group ref={g}>{children}</group>;
}

function ProgressDriver({ state, target }: { state: SceneState; target: React.MutableRefObject<number> }) {
  useFrame((_, dt) => { state.p = THREE.MathUtils.damp(state.p, target.current, 6, dt); });
  return null;
}
