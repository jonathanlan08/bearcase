import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono, Instrument_Serif } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/app/providers";

const geist = Geist({ subsets: ["latin"], variable: "--font-geist-sans", display: "swap" });
const geistMono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono", display: "swap" });
const instrument = Instrument_Serif({ subsets: ["latin"], weight: "400", style: ["normal", "italic"], variable: "--font-instrument-serif", display: "swap" });

export const metadata: Metadata = {
  title: { default: "BearCase AI", template: "%s · BearCase AI" },
  description: "Stress-test every claim before capital moves. BearCase audits deal documents, verifies financial assumptions, and exposes the downside with source-linked evidence.",
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000"),
  openGraph: { title: "BearCase AI", description: "Stress-test every claim before capital moves.", images: ["/og.png"] },
};

export const viewport: Viewport = { themeColor: "#07080A", width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${geist.variable} ${geistMono.variable} ${instrument.variable}`} suppressHydrationWarning>
      <body>
        <a href="#main" className="skip-link">Skip to main content</a>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
