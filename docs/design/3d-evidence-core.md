# The Evidence Core — 3D Hero Specification

Purpose: tell the product's story in three readable states — **the seller says 18% growth → the statements show 11.6% → open the evidence** — with a scene that reads as a diagram, not a toy. The scene dramatizes *documents → claims → evidence → verification → model → downside → report*; the three captions say what the reader is looking at.

Implementation: `apps/web/src/components/landing/hero.tsx` (layout, captions, pause control, scroll store), `apps/web/src/components/scene/storyboard.ts` (stages, chapters, scroll → progress mapping, claim data), `apps/web/src/components/scene/evidence-core.tsx` (the R3F scene), `apps/web/src/components/scene/static.tsx` (the SVG composition). `apps/web/scripts/scene-check.mjs` screenshots the three chapters and exercises the pause control against a running dev server.

## Story chapters (what the reader sees)

The sticky hero is 200svh tall (180svh below `md`), so the storyboard progresses over one viewport of scroll and each chapter is one scroll. The scroll fraction `s ∈ [0,1]` maps onto storyboard progress `p ∈ [0,1]` piecewise-linearly (`storyProgress` in `storyboard.ts`), so the ten fine-grained stages below keep their ramps while each chapter gets exactly one third of the scroll.

| Chapter | Scroll `s` | Storyboard `p` | Caption (HTML) | What the scene does |
|---|---|---|---|---|
| 1 Claim | 0–⅓ | 0–0.50 | **Seller says 18% growth** — The memo claims 18% annual growth. BearCase quotes the claim and links it to the page it came from. | Documents enter, values lift off the pages, flow into the core, and claim nodes connect to their sources. Every node is a warm neutral: a claim is a claim until it is checked. The growth claim renders 35% larger and its evidence line brighter. |
| 2 Evidence | ⅓–⅔ | 0.50–0.68 | **The statements show 11.6%** — Recomputed from the income statement, growth is 11.6% a year. The claim is marked contradicted. | Verdicts are revealed in place: supported nodes and lines turn signal blue (p 0.50–0.56), contradicted ones turn red and pulse (0.52–0.60), unsupported claims lose their line and fall (0.60–0.66), review items turn amber (0.60–0.68). |
| 3 Open | ⅔–1 | 0.68–1.00 | **Open the evidence** — Every figure links to the cell it came from, then feeds the model, the downside case, and the report. | The core recedes, verified nodes migrate into the 6×6 model, the DSCR row sinks below the covenant rule, and everything assembles into the report stack. The primary action, *Explore the demo*, is the "open". |

Captions are an `<ol>` in the DOM, never inside the canvas. Below `lg` (1024px) the list sits at the top of the hero under the nav, in compact form (titles only); at `lg` and above it sits bottom-left, and the active step also shows its one-line explanation in a fixed two-line slot so the copy above never shifts. The active step carries `aria-current="step"`, a 2px left rule, and heavier type — state is not colour alone. A visually hidden `aria-live="polite"` region announces "Step n of 3: title. detail" when the chapter changes (three announcements per read-through at most, because the hero re-renders only on chapter changes).

The headline and actions never sit over the core: the copy is bottom-anchored below `lg` and vertically centred on the left at `lg`+, and the scene is framed so the core sits away from it (see *Camera framing*). A scrim (bottom-up below `lg`, left-to-right at `lg`+) keeps text readable over particles.

## Scene hierarchy

```
<Canvas dpr={[1, tier dpr]} gl={{ antialias: tier>=2, powerPreference: 'high-performance' }} frameloop={visible ? 'always' : 'demand'}>
  <color attach="background" args={['#07080A']} />
  <PerspectiveCamera fov=32 />           // framed per viewport by <CameraDolly/>
  <FrameCounter/>                        // first frame → hero crossfades the static image out; 8th frame → post-processing on
  <ProgressDriver/>                      // eases p toward storyProgress(scroll) every frame; reads the scroll store, no React re-render
  <Lights>  ambient 0.25 (paper tint) · key directional 1.4 at [4, 6, 5] (shadows at tier 3) · rim point 1.2 signal at [-5, 2, -3] · amber fill 0.5
  <Environment/> + <ContactShadows/>     // tiers 2 and 3, one frame each
  <Rig>     // pointer parallax + constrained drag, smooth recentering, late-stage fit scale, quality watchdog
    <Documents/>       // InstancedMesh boxes ×6 (×4 at tier 1) with a procedural paper texture
    <Fragments/>       // InstancedMesh quads ×48 (values that separate from documents), tiers 2 and 3
    <Core/>            // icosphere r=1.15: transmission glass (tier 3), physical transmission (tier 2), fresnel shell (tier 1); emissive inner body; wireframe at tiers 2–3
    <Links/>           // LineSegments claim→evidence, colour = neutral → status via statusReveal
    <ClaimNodes/>      // InstancedMesh spheres ×10, per-instance colour = neutral → status via statusReveal; hero node ×1.35
    <ModelGrid/>       // InstancedMesh cells ×36 (6×6 model) + covenant rule + warning marker
    <ReportStack/>     // 4 stacked planes that receive nodes at the end
    <Particles/>       // Points, 600–2400 by tier, additive soft sprites, pointer displacement
    <NodeAnchor><Html/></NodeAnchor>   // DOM tooltip for the selected claim
  </Rig>
  <EffectComposer/>   // Bloom + Vignette, tiers 2 and 3, mounted only after the 8th visible frame
</Canvas>
```

## Storyboard stages (`p ∈ [0,1]`; the ramps every entity animates against)

| Stage | p | Documents | Fragments | Core | Links | Nodes | Model | Report |
|---|---|---|---|---|---|---|---|---|
| 1 Enter | 0.00–0.10 | fly in from −z, settle in an arc | hidden | dim | — | — | — | — |
| 2 Separate | 0.10–0.20 | hold | lift off document faces (+y, +z) | dim | — | fade in, neutral | — | — |
| 3 Flow | 0.20–0.30 | recede 20% | curve toward core along bezier, shrink | rim brightens | — | travel to the core surface | — | — |
| 4 Connect | 0.30–0.40 | hold | absorbed | pulse once | draw from nodes to document points, neutral | on core surface | — | — |
| 5 Stabilize | 0.40–0.50 | — | — | steady | steady | steady | — | — |
| 6 Verdict | 0.50–0.60 | — | — | — | supported → signal (0.50–0.56); contradicted → red, pulse 1.2s (0.52–0.60) | same colours; contradicted scale ±8% | — | — |
| 7 Dissolve | 0.60–0.68 | — | — | — | unsupported lines fade to 0; review → amber, dashed | unsupported nodes fall −y and fade; review → amber | — | — |
| 8 Model | 0.68–0.80 | recede fully | — | shrinks 40%, drifts left | supported links retarget to model cells | verified nodes migrate into grid cells | grid assembles from cells (stagger) | — |
| 9 Downside | 0.80–0.90 | — | — | — | — | — | DSCR row sinks; covenant rule amber then red; warning marker | — |
| 10 Report | 0.90–1.00 | fade | — | fades | converge to stack | stack into report | grid compresses | stack assembles |

Idle (`p` static): slow orbit ±3° over 12s, particles drift, core rim breathes ±5% over 6s.

## Camera framing

The hero measures the **free region** of the sticky box (fractions of its width and height) once on mount, again after the copy's entrance animation, and on every resize, and writes it to the shared store (`SceneStore.region`):

- side by side (`lg`+, viewport ≥ 1024px): everything right of the copy block plus a 24px margin — `{ left: (copy.right + 24) / width, right: 1, top: 0, bottom: 1 }`;
- stacked (below `lg`): the band between the caption row and the copy block — `{ left: 0, right: 1, top: (captions.bottom + 8) / height, bottom: (copy.top − 8) / height }`.

The store never lets the region collapse below 20% in either direction. `Framing` in `evidence-core.tsx` (a `useFrame` at priority −1, so it runs before every entity) then places the camera so the story happens inside that region. With `halfH = z · tan(16°)` and `halfW = halfH · aspect`, a world point X appears at viewport fraction f when the camera axis is at `X − (f − 0.5) · 2 · halfW`:

| Quantity | Rule |
|---|---|
| Base distance | `z = 9.8 + clamp((1.2 − aspect) × 4, 0, 3) + clamp((aspect − 1) × 3, 0, 0.6)` → 10.4 on wide screens, 11.6 on a portrait tablet, about 12.8 on a phone; the dolly then subtracts 0.8 over the first six stages and adds 0.6 for the model and report |
| Core position, chapters 1–2 | horizontally at the region's centre, but no further from the middle of the viewport than it takes to clear the region's left edge by the core's radius plus 3% (`cx = min(centre, max(0.5, left + 1.15 / (2 · halfW) + 0.03))`); vertically at the region's centre |
| Cluster position, chapter 3 | the late-stage cluster (core drifting to x −1.6 … report stack at x 3.2; centre (0.45, −0.1); about 5.5 units wide) is centred in the region; the camera axis lerps from the chapter 1–2 target to this one over p 0.68–1 |
| Cluster scale `fit` | `clamp(regionWidthUnits × 0.9 / 5.5, 0.55, 0.85)` applied to the rig over p 0.68–0.80, so the model and report never spill over the headline; 0.55 on phones, about 0.8 at 1440×900 |
| Document arc `spread` | `1 − clamp((aspect − 1.15) × 0.5, 0, 0.25)` narrows the arc to 75% on wide aspects so the far documents stay in frame beside the copy |
| Elevation | camera sits 0.4 above the axis and looks at it, lifting −0.35 after p 0.68 as before |

Axis and distance targets are damped (λ 2.5), so resizing and chapter changes glide; the first frame snaps so there is no glide during the crossfade. Below 1024px on a very short landscape viewport (for example 800×480) the band between captions and copy is too small for the core and the scrim does the work; that is the accepted limit.

## Materials and shaders

- **Documents:** thin boxes (1 × 1.3 × 0.012) with a procedural canvas "paper with text lines" texture, `MeshPhysicalMaterial` roughness 0.82, sheen 0.4; they cast shadows at tier 3.
- **Core:** tier 3 `MeshTransmissionMaterial` (real refraction, ior 1.35, slight chromatic aberration); tier 2 `MeshPhysicalMaterial` transmission 0.9; tier 1 the fresnel shell only. Inside: a small emissive signal-blue icosahedron that brightens on the connect pulse. Inner wireframe `#2C333C` at tiers 2 and 3.
- **Links:** `LineBasicMaterial` vertex colours; draw by lerping the far endpoint; colour lerps from the neutral (`paper × 0.72`) to the status colour by `statusReveal`; review links dashed in the static composition.
- **Nodes/cells:** `MeshPhysicalMaterial` with `instanceColor` written every frame (neutral → status); roughness 0.35, clearcoat 0.6.
- **Particles:** `PointsMaterial` with a procedural radial sprite, additive blending, size 0.045, opacity 0.55.
- **Lighting:** key directional (shadow-casting at tier 3), signal-blue rim point light, faint amber fill, fog to `#07080A`, and at tiers 2 and 3 a procedural `Environment` built from three `Lightformer`s (no HDR download) plus `ContactShadows` under the composition.
- **Post-processing (tiers 2 and 3 only):** `Bloom` (threshold 0.72, intensity 0.4 to 0.55) and `Vignette`. Mounted only after the scene has drawn eight frames on screen, so the first paint of the hero never pays for it. Tier 1 and the static composition have none.
- **Tone mapping:** ACES filmic, exposure 1.05.

## Interaction

- **Pointer parallax:** rig rotates toward pointer, max ±6° yaw / ±4° pitch, damped (`damp` λ=4). The copy layer is `pointer-events: none` with the text and controls opting back in, so the canvas receives pointer events between them; the static layer is `pointer-events: none` while the scene is showing.
- **Particle displacement:** particles within 0.8 units of the pointer ray push outward and relax (`damp`).
- **Drag rotation:** pointer down + move rotates the rig ±25° yaw / ±12° pitch, clamped; release recenters over 1.2s. Touch: single-finger drag; vertical page scroll remains native (`touch-action: pan-y`).
- **Tap/click a claim node:** shows its evidence line at full brightness and a DOM tooltip (claim text, status, source) anchored via `Html` from drei; `Esc`/tap-away closes. Nodes are exposed to keyboard via a visually hidden list of buttons that select the same node.
- **Scroll:** `s = clamp((scrollY − heroTop) / (heroHeight − viewport), 0, 1)` written to a small external store by a passive listener (one rAF per scroll event); the scene eases `p` toward `storyProgress(s)` with damp λ=6; the captions subscribe to the chapter index only. No scroll capture.
- **Pause 3D / Resume 3D:** a hairline `secondary` button (`--radius-1`, glyph + label) next to the captions with `aria-pressed` reflecting the paused state. Pausing unmounts the canvas (the render loop stops and the GPU context is released) and shows the static composition; resuming remounts it and crossfades on the first drawn frame. The preference persists in `localStorage` under `bc.scene.paused` via `useLocalFlag`, so a visitor who paused once never downloads the scene chunk again until they resume. The control is rendered only when the scene could run (WebGL present, no reduced-motion preference, no context loss).

## Quality tiers

| Tier | Trigger | DPR cap | Particles | Docs | Edges | Antialias | Core shader |
|---|---|---|---|---|---|---|---|
| 3 | desktop, ≥8 cores | 1.75 | 2400 | 6 | yes | yes | transmission glass, shadows, environment, bloom |
| 2 | default desktop/tablet | 1.5 | 1200 | 6 | yes | yes | physical transmission, environment, bloom |
| 1 | `max-width: 767px` or `deviceMemory ≤ 4` | 1.25 | 600 | 4 | no | no | fresnel shell, no environment, no post |
| 0 | WebGL unavailable / context lost / reduced motion / paused | — | — | — | — | — | static SVG |

Runtime degradation: average frame time over 90 frames (deltas above 100ms are ignored so a hidden tab does not count as a slow GPU); if the average exceeds 22ms, drop one tier (never rises again within the session).

## Rendering only when it matters

- An `IntersectionObserver` on the canvas wrapper switches `frameloop` between `always` (on screen) and `demand` (off screen); once the reader scrolls past the hero no frames run.
- The canvas starts in `demand` until the observer reports it visible, so the first frames (and the crossfade) happen on screen.
- Post-processing mounts after the eighth visible frame (`FrameCounter`).
- Paused or reduced-motion visitors and browsers without WebGL never load the scene chunk (`next/dynamic` is not rendered).

## Loading and fallback

- Canvas is `dynamic(() => import(...), { ssr: false })`. The static SVG is server-rendered in the same box and crossfades out on the first drawn frame, so layout is stable and LCP is the SVG.
- WebGL failure (`webglcontextlost` without restore) → keep the SVG, show nothing else. No error text.
- The static composition (`static.tsx`) shows the three states in one frame: the memo labelled "CIM: 18% growth claimed", a red evidence line through the hero claim to the statements labelled "Statements: 11.6% a year", supported links in blue, an unsupported claim with a broken line, the model grid with the DSCR row below the rule, and the report stack. `align="right"` (used at `lg`+) shifts the viewBox so the core sits right of centre next to the copy; `center` is used below `lg` where the copy is at the bottom.
- Reduced motion, no WebGL, and paused all show the same SVG with the same three HTML captions; the captions still follow scroll, so the story is readable without the scene.

## Accessibility

- Canvas `role="img"` with an `aria-label` that tells the story in one sentence; the caption list and the keyboard node list provide the same information in DOM.
- The static SVG carries `<title>` and `<desc>`; only the layer that is showing is exposed (`aria-hidden` swaps with the crossfade).
- Chapter changes announce once each via a polite live region.
- `prefers-reduced-motion` → tier 0, no reveal animations on the copy.
- The pause control is a real `<button>` with `aria-pressed`; its label states the action ("Pause 3D" / "Resume 3D") and it shows a glyph as well as text.

## Asset list

Procedural only: no textures, no GLTF. The static composition is a React SVG component (`static.tsx`); the social preview is `apps/web/public/og.png`.
