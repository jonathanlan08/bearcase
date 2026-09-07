import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/app/providers";

const geist = Geist({ subsets: ["latin"], variable: "--font-geist-sans", display: "swap" });
const geistMono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono", display: "swap" });

/** The one-sentence promise; the hero subhead says the same words. */
const PROMISE = "BearCase checks a seller's documents for financial inconsistencies and shows you what to investigate before buying the business.";

export const metadata: Metadata = {
  title: { default: "BearCase AI", template: "%s · BearCase AI" },
  description: PROMISE,
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000"),
  openGraph: { title: "BearCase AI", description: PROMISE, images: ["/og.png"] },
};

export const viewport: Viewport = { themeColor: "#07080A", width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${geist.variable} ${geistMono.variable}`} suppressHydrationWarning>
      <body>
        <a href="#main" className="skip-link">Skip to main content</a>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
