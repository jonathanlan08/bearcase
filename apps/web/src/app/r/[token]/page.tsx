import type { Metadata } from "next";
import { SharedReportView } from "@/components/domain/shared-report";

/** A shared report is for the people its link was sent to: never indexed, and the token never leaves in a Referer. */
export const metadata: Metadata = {
  title: "Shared report",
  description: "A read-only BearCase red-team review shared by link.",
  robots: { index: false, follow: false, nocache: true },
  referrer: "no-referrer",
};

export default async function SharedReportPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return <SharedReportView token={token} />;
}
