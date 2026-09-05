/** Server-rendered static composition (stage 8: verified model with the covenant warning).
 *  Used as LCP element, reduced-motion version, and WebGL fallback. */
export function EvidenceCoreStatic() {
  const nodes = [[540, 150, "s"], [600, 200, "s"], [520, 250, "c"], [640, 260, "c"], [560, 320, "c"], [610, 360, "c"], [480, 200, "s"], [500, 330, "s"], [660, 150, "u"], [470, 280, "r"]] as const;
  const color = (k: string) => (k === "s" ? "#7FB2FF" : k === "c" ? "#EF7360" : k === "r" ? "#E7AA40" : "#8A94A0");
  return (
    <svg viewBox="0 0 1200 700" className="h-full w-full" preserveAspectRatio="xMidYMid slice" role="img" aria-labelledby="ec-title ec-desc">
      <title id="ec-title">The Evidence Core</title>
      <desc id="ec-desc">Six deal documents send claims into a translucent analysis core. Supported claims connect in blue, contradicted claims in red, an unsupported claim has lost its connection, and verified metrics form a grid model whose covenant row is marked in amber.</desc>
      <rect width="1200" height="700" fill="#07080A" />
      <g opacity="0.55">{Array.from({ length: 140 }).map((_, i) => { const x = (i * 97) % 1200, y = (i * 61) % 700; return <circle key={i} cx={x} cy={y} r={i % 5 === 0 ? 1.6 : 1} fill="#F5F2EC" opacity={0.25 + (i % 4) * 0.12} />; })}</g>
      {[[300, 120, 0], [330, 250, -4], [290, 390, 3], [340, 520, -2], [860, 130, 2], [900, 420, -3]].map(([x, y, r], i) => (
        <g key={i} transform={`translate(${x} ${y}) rotate(${r})`}><rect width="120" height="150" fill="#F5F2EC" fillOpacity="0.92" stroke="#2C333C" /><g stroke="#2C333C" strokeWidth="2">{[24, 40, 56, 72, 88, 104].map((yy) => <line key={yy} x1="14" x2={yy % 32 === 8 ? 70 : 100} y1={yy} y2={yy} />)}</g></g>
      ))}
      <circle cx="580" cy="260" r="115" fill="#15181D" fillOpacity="0.35" stroke="#7FB2FF" strokeOpacity="0.55" strokeWidth="1.5" />
      <circle cx="580" cy="260" r="115" fill="none" stroke="#7FB2FF" strokeOpacity="0.15" strokeWidth="24" />
      <g stroke="#2C333C" fill="none"><polygon points="580,175 655,215 655,305 580,345 505,305 505,215" /><path d="M580,175 L580,345 M505,215 L655,305 M655,215 L505,305" /></g>
      {nodes.map(([x, y, k], i) => { const dx = i % 2 ? 420 : 900, dy = 200 + (i * 53) % 300; return <g key={i}>{k !== "u" && <line x1={x} y1={y} x2={dx} y2={dy} stroke={color(k)} strokeOpacity="0.7" strokeWidth="1" strokeDasharray={k === "r" ? "4 3" : undefined} />}{k === "u" && <line x1={x} y1={y} x2={x + 20} y2={y + 30} stroke={color(k)} strokeOpacity="0.4" strokeWidth="1" strokeDasharray="2 4" />}{k === "c" ? <polygon points={`${x},${y - 7} ${x + 7},${y} ${x},${y + 7} ${x - 7},${y}`} fill={color(k)} /> : k === "r" ? <rect x={x - 5} y={y - 5} width="10" height="10" fill="none" stroke={color(k)} strokeWidth="1.5" /> : <circle cx={x} cy={y} r="5" fill={color(k)} />}</g>; })}
      <g transform="translate(700 380)">{Array.from({ length: 36 }).map((_, i) => { const r = Math.floor(i / 6), c = i % 6; const warn = r === 4; return <rect key={i} x={c * 34} y={r * 26 + (warn ? 6 : 0)} width="28" height="20" fill={warn ? "#E7AA40" : "#F5F2EC"} fillOpacity={warn ? 0.75 : 0.85 - r * 0.06} stroke="#2C333C" />; })}<polygon points="-16,124 -6,106 4,124" fill="none" stroke="#EF7360" strokeWidth="1.5" /><text x="-30" y="150" fill="#8A94A0" fontFamily="ui-monospace, monospace" fontSize="11">DSCR 0.99x &lt; 1.25x</text></g>
      <g transform="translate(980 520)">{[0, 1, 2, 3].map((i) => <rect key={i} x={i * 4} y={-i * 6} width="110" height="70" fill="#F5F2EC" fillOpacity={0.9} stroke="#2C333C" />)}<text x="16" y="12" fill="#0D0F12" fontFamily="ui-monospace, monospace" fontSize="9">RED-TEAM REPORT</text></g>
    </svg>
  );
}
