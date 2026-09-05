import { ImageResponse } from "next/og";

export const alt = "BearCase AI: stress-test every claim before capital moves.";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpenGraphImage() {
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", justifyContent: "space-between", padding: 72, background: "#07080A", color: "#F5F2EC", fontFamily: "Georgia, serif" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14, fontFamily: "ui-sans-serif, system-ui", fontSize: 26, letterSpacing: -0.5 }}>
          <svg width="30" height="30" viewBox="0 0 24 24" fill="none"><rect x="2" y="2" width="5" height="5" fill="#F5F2EC" /><rect x="17" y="17" width="5" height="5" fill="#F5F2EC" /><line x1="7" y1="7" x2="17" y2="17" stroke="#7FB2FF" strokeWidth="1.4" /><circle cx="12" cy="12" r="2.4" fill="#07080A" stroke="#7FB2FF" strokeWidth="1.4" /></svg>
          BearCase
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          <div style={{ fontSize: 84, lineHeight: 1, letterSpacing: -2, display: "flex", flexDirection: "column" }}>
            <span>Stress-test every claim</span>
            <span style={{ fontStyle: "italic", color: "#A9CCFF" }}>before capital moves.</span>
          </div>
          <div style={{ fontFamily: "ui-sans-serif, system-ui", fontSize: 28, color: "#8A94A0", maxWidth: 900 }}>AI-assisted acquisition diligence with source-linked evidence, deterministic financial verification, and downside scenarios.</div>
        </div>
        <div style={{ fontFamily: "ui-monospace, monospace", fontSize: 18, color: "#8A94A0", letterSpacing: 2 }}>OPEN SOURCE · MOCK OR ANTHROPIC MODE · FICTIONAL DEMO DEAL</div>
      </div>
    ),
    { ...size },
  );
}
