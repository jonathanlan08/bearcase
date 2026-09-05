# The Evidence Core — 3D Hero Specification

Purpose: dramatize the workflow *documents → claims → evidence → verification → model → downside → report* in a single scene that reads as a diagram, not a toy.

## Scene hierarchy

```
<Canvas dpr={[1, 1.75]} gl={{ antialias: tier>=2, powerPreference: 'high-performance' }} frameloop="always|demand">
  <color attach="background" args={['#07080A']} />
  <PerspectiveCamera fov=32 position=[0, 0.4, 9] />
  <Lights>  ambient 0.35 (paper tint) · key directional 1.1 at [4, 6, 5] · rim point 0.6 signal at [-5, 2, -3]
  <Rig>     // pointer parallax + constrained drag, smooth recentering
    <Documents/>       // InstancedMesh planes ×6 (CIM, statements, model, CSV, term sheet, contracts)
    <Fragments/>       // InstancedMesh small quads ×N (claims/values that separate from documents)
    <Core/>            // icosphere r=1.15, fresnel shader, inner wireframe icosahedron slowly rotating
    <Links/>           // LineSegments (claim→evidence), color per status, dash for review
    <ClaimNodes/>      // InstancedMesh spheres ×10 with per-instance color
    <ModelGrid/>       // InstancedMesh cells ×36 forming a 6×6 financial model plane
    <CovenantRule/>    // thin plane at DSCR threshold + warning marker
    <ReportStack/>     // 4 stacked planes that receive nodes at the end
    <Particles/>       // Points, 600–2400 depending on tier
  </Rig>
</Canvas>
```

## Storyboard (progress `p ∈ [0,1]` from scroll; each stage ~0.1)

| Stage | p | Documents | Fragments | Core | Links | Nodes | Model | Report |
|---|---|---|---|---|---|---|---|---|
| 1 Enter | 0.00–0.10 | fly in from −z, settle in an arc | hidden | dim | — | — | — | — |
| 2 Separate | 0.10–0.20 | hold | lift off document faces (+y, +z) | dim | — | — | — | — |
| 3 Flow | 0.20–0.30 | recede 20% | curve toward core along bezier, shrink | rim brightens | — | — | — | — |
| 4 Connect | 0.30–0.40 | hold | absorbed | pulse once | draw from nodes to document points (hairline draw) | emerge on core surface | — | — |
| 5 Stabilize | 0.40–0.50 | — | — | steady | supported = signal, opacity 1 | supported nodes settle, stop jitter | — | — |
| 6 Contradict | 0.50–0.60 | — | — | — | contradicted = red pulse 1.2s, both endpoints flash | contradicted nodes diamond-scale ±8% | — | — |
| 7 Dissolve | 0.60–0.68 | — | — | — | unsupported lines fade to 0 | unsupported nodes fall −y slowly, fade | — | — |
| 8 Model | 0.68–0.80 | recede fully | — | shrinks 40%, drifts left | supported links retarget to model cells | verified nodes migrate into grid cells | grid assembles from cells (stagger) | — |
| 9 Downside | 0.80–0.90 | — | — | — | — | — | cells in the DSCR row sink; covenant rule turns amber then red; warning marker appears | — |
| 10 Report | 0.90–1.00 | — | — | fades | links converge to stack | nodes stack into report | grid compresses | stack assembles, title plane brightens |

Idle (`p` static): slow orbit ±3° over 12s, particles drift, core rim breathes ±5% over 6s.

## Materials and shaders

- **Documents:** `MeshStandardMaterial` paper `#F5F2EC` roughness 0.9, opacity 0.92, emissive `#15181D`·0.2; edge `LineSegments` `#2C333C`.
- **Core:** custom `ShaderMaterial` fresnel: `rim = pow(1 - dot(normal, viewDir), 2.4)`; color mix(`#15181D`, `#7FB2FF`, rim), alpha 0.35 + 0.45·rim; additive off; depthWrite off. Inner wireframe `#2C333C`.
- **Links:** `LineBasicMaterial` vertex colors; draw via `drawRange` progression per link; dashed review links via `LineDashedMaterial` (needs `computeLineDistances`).
- **Nodes/cells:** `MeshStandardMaterial` with `instanceColor`; roughness 0.6.
- **Particles:** `PointsMaterial` size 0.02, sizeAttenuation, opacity 0.5, additive off.
- No post-processing. No shadows.

## Interaction

- **Pointer parallax:** rig rotates toward pointer, max ±6° yaw / ±4° pitch, damped (`damp` λ=4).
- **Particle displacement:** particles within 0.8 units of the pointer ray push outward 0.15 units and relax (`damp`).
- **Drag rotation:** pointer down + move rotates the rig ±25° yaw / ±12° pitch, clamped; release recenters over 1.2s (`ease-std`). Touch: single-finger drag; vertical page scroll remains native unless the gesture starts on the canvas and is mostly horizontal (`touch-action: pan-y`).
- **Tap/click a claim node:** shows its evidence line at full brightness and a DOM tooltip (claim text, status, source) anchored via `Html` from drei; `Esc`/tap-away closes. Nodes are exposed to keyboard via a hidden list of buttons (`role="list"`) that select the same node.
- **Hover a contradiction:** both endpoints (node and document point) flash red; the corresponding DOM caption highlights the two sources.
- **Scroll:** `p` = clamp((scrollY − heroTop) / (heroHeight − viewport), 0, 1), smoothed with damp λ=6. No scroll capture.

## Quality tiers

| Tier | Trigger | DPR cap | Particles | Docs edges | Antialias | Core shader |
|---|---|---|---|---|---|---|
| 3 | desktop, ≥8 cores or discrete GPU hint | 1.75 | 2400 | yes | yes | full |
| 2 | default desktop/tablet | 1.5 | 1200 | yes | yes | full |
| 1 | mobile or `deviceMemory ≤ 4` | 1.25 | 600 | no | no | simplified (no inner wireframe) |
| 0 | WebGL unavailable / context lost / reduced motion | — | — | — | — | static SVG |

Runtime degradation: measure frame time over 2s windows; if average > 22ms, drop one tier (never rises again within the session). `frameloop="demand"` while offscreen (IntersectionObserver).

## Loading and fallback

- Canvas is `dynamic(() => import(...), { ssr: false })`. A static SVG (the stage-8 composition) is server-rendered in the same box and crossfades out when the first frame is drawn, so layout is stable and LCP is the SVG.
- WebGL failure (`webglcontextcreationerror`, `webglcontextlost` without restore) → keep the SVG, show nothing else. No error text.
- Mobile tier 1: fewer documents (4), no fragments stage (skips 2→4 by morphing), shorter hero (180vh).

## Accessibility

- Canvas `role="img"` `aria-label` describes the scene; the scene caption and the keyboard node list provide the same information in DOM.
- Stage captions announce once per stage via a throttled `aria-live="polite"` region.
- `prefers-reduced-motion` → tier 0.

## Asset list

Procedural only: no textures, no GLTF. The static fallback SVG is committed at `apps/web/public/evidence-core-static.svg`; the social preview at `apps/web/public/og.png`.
