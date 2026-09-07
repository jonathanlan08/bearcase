/** Server-rendered static composition: the story's three states in one frame. The memo's growth claim is linked in red to the
 *  income statement that contradicts it; supported claims connect in blue; verified figures form a grid model with the covenant
 *  warning; the report assembles at the right. Used as the LCP element, the reduced-motion version, the WebGL fallback, and the
 *  paused view. `align="right"` shifts the composition right of centre for the side-by-side layout (copy on the left).
 *  The three HTML captions live in the hero, not here, so every path shows the same words. */
export function EvidenceCoreStatic({ align = "center" }: { align?: "center" | "right" }) {
  const nodes = [[540, 150, "s"], [600, 200, "s"], [520, 250, "c"], [640, 260, "c"], [560, 320, "c"], [610, 360, "c"], [480, 200, "s"], [500, 330, "s"], [660, 150, "u"], [470, 280, "r"]] as const;
  const color = (k: string) => (k === "s" ? "#7FB2FF" : k === "c" ? "#EF7360" : k === "r" ? "#E7AA40" : "#8A94A0");
  const mono = "ui-monospace, monospace";
  return (
    <svg viewBox={align === "right" ? "-200 0 1200 700" : "0 0 1200 700"} className="h-full w-full" preserveAspectRatio="xMidYMid slice" role="img" aria-labelledby="ec-title ec-desc">
      <title id="ec-title">The Evidence Core</title>
      <desc id="ec-desc">Six deal documents send claims into an analysis core. The memo&apos;s claim of 18% annual growth is linked in red to the income statement, which shows 11.6%. Supported claims connect in blue, an unsupported claim has lost its connection, and the verified figures form a grid model whose covenant row is marked in amber next to an assembled report.</desc>
      <rect x="-400" width="2000" height="700" fill="#07080A" />
      <g opacity="0.55">{Array.from({ length: 170 }).map((_, i) => { const x = ((i * 97) % 1500) - 300, y = (i * 61) % 700; return <circle key={i} cx={x} cy={y} r={i % 5 === 0 ? 1.6 : 1} fill="#F5F2EC" opacity={0.25 + (i % 4) * 0.12} />; })}</g>
      {[[300, 120, 0], [330, 250, -4], [290, 390, 3], [340, 520, -2], [860, 130, 2], [900, 420, -3]].map(([x, y, r], i) => (
        <g key={i} transform={`translate(${x} ${y}) rotate(${r})`}><rect width="120" height="150" fill="#F5F2EC" fillOpacity="0.92" stroke="#2C333C" /><g stroke="#2C333C" strokeWidth="2">{[24, 40, 56, 72, 88, 104].map((yy) => <line key={yy} x1="14" x2={yy % 32 === 8 ? 70 : 100} y1={yy} y2={yy} />)}</g></g>
      ))}
      {/* Story labels: the claim on the memo, the recomputed figure on the statements. */}
      <text x="300" y="106" fill="#8A94A0" fontFamily={mono} fontSize="11">CIM: 18% growth claimed</text>
      <text x="860" y="116" fill="#8A94A0" fontFamily={mono} fontSize="11">Statements: 11.6% a year</text>
      <circle cx="580" cy="260" r="115" fill="#15181D" fillOpacity="0.35" stroke="#7FB2FF" strokeOpacity="0.55" strokeWidth="1.5" />
      <circle cx="580" cy="260" r="115" fill="none" stroke="#7FB2FF" strokeOpacity="0.15" strokeWidth="24" />
      <g stroke="#2C333C" fill="none"><polygon points="580,175 655,215 655,305 580,345 505,305 505,215" /><path d="M580,175 L580,345 M505,215 L655,305 M655,215 L505,305" /></g>
      {nodes.map(([x, y, k], i) => { const dx = i % 2 ? 420 : 900, dy = 200 + (i * 53) % 300; return <g key={i}>{k !== "u" && <line x1={x} y1={y} x2={dx} y2={dy} stroke={color(k)} strokeOpacity="0.7" strokeWidth="1" strokeDasharray={k === "r" ? "4 3" : undefined} />}{k === "u" && <line x1={x} y1={y} x2={x + 20} y2={y + 30} stroke={color(k)} strokeOpacity="0.4" strokeWidth="1" strokeDasharray="2 4" />}{k === "c" ? <polygon points={`${x},${y - 7} ${x + 7},${y} ${x},${y + 7} ${x - 7},${y}`} fill={color(k)} /> : k === "r" ? <rect x={x - 5} y={y - 5} width="10" height="10" fill="none" stroke={color(k)} strokeWidth="1.5" /> : <circle cx={x} cy={y} r="5" fill={color(k)} />}</g>; })}
      {/* The hero claim: a larger contradicted node whose evidence line runs from the memo to the statements. */}
      <line x1="420" y1="195" x2="520" y2="250" stroke="#EF7360" strokeOpacity="0.9" strokeWidth="1.5" />
      <line x1="520" y1="250" x2="900" y2="205" stroke="#EF7360" strokeOpacity="0.9" strokeWidth="1.5" />
      <polygon points="520,240 530,250 520,260 510,250" fill="#EF7360" />
      <g transform="translate(700 380)">{Array.from({ length: 36 }).map((_, i) => { const r = Math.floor(i / 6), c = i % 6; const warn = r === 4; return <rect key={i} x={c * 34} y={r * 26 + (warn ? 6 : 0)} width="28" height="20" fill={warn ? "#E7AA40" : "#F5F2EC"} fillOpacity={warn ? 0.75 : 0.85 - r * 0.06} stroke="#2C333C" />; })}<polygon points="-16,124 -6,106 4,124" fill="none" stroke="#EF7360" strokeWidth="1.5" /><text x="-30" y="150" fill="#8A94A0" fontFamily={mono} fontSize="11">DSCR 0.99x below 1.25x</text></g>
      <g transform="translate(980 520)">{[0, 1, 2, 3].map((i) => <rect key={i} x={i * 4} y={-i * 6} width="110" height="70" fill="#F5F2EC" fillOpacity={0.9} stroke="#2C333C" />)}<text x="16" y="12" fill="#0D0F12" fontFamily={mono} fontSize="9">RED-TEAM REPORT</text></g>
    </svg>
  );
}
