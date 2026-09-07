/** Server-rendered static composition: the Evidence Sculpture in one frame, drawn in isometric SVG. The seller's memo sits
 *  above a glass inspection plane and the income statement; one red line runs from the memo's 18% growth claim to the
 *  statement cell that recomputes it as 11.6%; a small bear sits on the graphite base. Used as the LCP element, the
 *  reduced-motion version, the WebGL fallback, and the paused view. `align="right"` shifts the composition right of centre
 *  for the side-by-side layout (copy on the left). The three HTML captions live in the hero, not here, so every path
 *  shows the same words. */
export function EvidenceSculptureStatic({ align = "center" }: { align?: "center" | "right" }) {
  const mono = "ui-monospace, monospace";
  // Isometric helpers: a flat rectangle w×d at height h becomes a parallelogram. Origin is the base's back corner.
  const iso = (x: number, z: number, y: number): [number, number] => [600 + (x - z) * 0.866, 420 + (x + z) * 0.5 - y];
  const slab = (x0: number, z0: number, w: number, d: number, y: number) => {
    const a = iso(x0, z0, y), b = iso(x0 + w, z0, y), c = iso(x0 + w, z0 + d, y), e = iso(x0, z0 + d, y);
    return `${a.join(",")} ${b.join(",")} ${c.join(",")} ${e.join(",")}`;
  };
  const grid = (x0: number, z0: number, w: number, d: number, y: number, rows: number, cols: number, stroke: string) => {
    const lines: string[] = [];
    for (let r = 1; r < rows; r++) { const z = z0 + (d * r) / rows; const a = iso(x0 + 14, z, y), b = iso(x0 + w - 14, z, y); lines.push(`M${a[0]},${a[1]} L${b[0]},${b[1]}`); }
    for (let c = 1; c < cols; c++) { const x = x0 + (w * c) / cols; const a = iso(x, z0 + 30, y), b = iso(x, z0 + d - 14, y); lines.push(`M${a[0]},${a[1]} L${b[0]},${b[1]}`); }
    return <path d={lines.join(" ")} stroke={stroke} strokeWidth="1" fill="none" opacity="0.7" />;
  };
  const cell = (x: number, z: number, w: number, d: number, y: number) => <polygon points={slab(x, z, w, d, y)} fill="#E4533C" fillOpacity="0.75" />;
  const claim = iso(264, 146, 300), source = iso(308, 223, 54);
  const bear = iso(392, 270, 0);
  return (
    <svg viewBox={align === "right" ? "-160 0 1200 760" : "0 0 1200 760"} className="h-full w-full" preserveAspectRatio="xMidYMid slice" role="img" aria-labelledby="es-title es-desc">
      <title id="es-title">The Evidence Sculpture</title>
      <desc id="es-desc">The seller&apos;s memo lies above a glass inspection plane and the income statement on a graphite base. One red line runs from the memo&apos;s claim of 18% growth to the statement cell that recomputes it as 11.6%. A small bear sits on the base.</desc>
      <rect x="-400" width="2000" height="760" fill="#07080A" />
      {/* base slab: top face and two visible sides */}
      <polygon points={slab(0, 0, 440, 320, 0)} fill="#1C2026" />
      <polygon points={`${iso(0, 320, 0).join(",")} ${iso(440, 320, 0).join(",")} ${iso(440, 320, -34).join(",")} ${iso(0, 320, -34).join(",")}`} fill="#14171C" />
      <polygon points={`${iso(440, 0, 0).join(",")} ${iso(440, 320, 0).join(",")} ${iso(440, 320, -34).join(",")} ${iso(440, 0, -34).join(",")}`} fill="#0F1216" />
      {/* income statement */}
      <polygon points={slab(60, 40, 300, 220, 54)} fill="#F1EDE4" stroke="#B9B3A7" />
      {grid(60, 40, 300, 220, 54, 8, 4, "#B9B3A7")}
      <polygon points={slab(74, 52, 272, 22, 54)} fill="#2C333C" fillOpacity="0.1" />
      {cell(276, 214, 64, 18, 54)}
      {/* glass plane */}
      <polygon points={slab(40, 24, 340, 252, 170)} fill="#8FB0C8" fillOpacity="0.28" stroke="#BFD6E6" strokeOpacity="0.6" />
      <polygon points={`${iso(40, 276, 170).join(",")} ${iso(380, 276, 170).join(",")} ${iso(380, 276, 164).join(",")} ${iso(40, 276, 164).join(",")}`} fill="#BFD6E6" fillOpacity="0.35" />
      {/* memo */}
      <polygon points={slab(60, 40, 300, 220, 300)} fill="#F1EDE4" stroke="#B9B3A7" />
      <polygon points={slab(74, 50, 150, 10, 300)} fill="#2C333C" fillOpacity="0.8" />
      <polygon points={slab(74, 66, 240, 6, 300)} fill="#6F7780" fillOpacity="0.6" />
      {grid(60, 100, 300, 160, 300, 6, 3, "#B9B3A7")}
      {cell(232, 136, 64, 20, 300)}
      {/* the one red line, memo claim to statement cell, through the glass */}
      <line x1={claim[0]} y1={claim[1]} x2={source[0]} y2={source[1]} stroke="#E4533C" strokeWidth="2" />
      <circle cx={claim[0]} cy={claim[1]} r="3.5" fill="#E4533C" />
      <circle cx={source[0]} cy={source[1]} r="3.5" fill="#E4533C" />
      <text x={claim[0] + 14} y={claim[1] - 8} fill="#8A94A0" fontFamily={mono} fontSize="12">memo: 18% growth</text>
      <text x={source[0] + 14} y={source[1] + 16} fill="#8A94A0" fontFamily={mono} fontSize="12">statements: 11.6%</text>
      {/* low-poly bear silhouette, front-right corner */}
      <g transform={`translate(${bear[0]} ${bear[1]})`}>
        <polygon points="-22,0 22,0 26,-30 18,-58 6,-66 -8,-66 -20,-56 -26,-30" fill="#262B32" />
        <polygon points="-10,-60 12,-60 18,-78 10,-92 -8,-92 -16,-78" fill="#2E343C" />
        <polygon points="-16,-88 -8,-100 -2,-90" fill="#262B32" />
        <polygon points="4,-90 10,-100 18,-88" fill="#262B32" />
        <polygon points="-2,-78 12,-76 8,-68 -2,-70" fill="#1B1F25" />
      </g>
    </svg>
  );
}
