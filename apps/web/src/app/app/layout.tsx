import { AppGate } from "@/components/app/gate";

export const metadata = { title: "Deals" };

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div data-world="paper" className="min-h-svh bg-bg text-fg">
      <AppGate>{children}</AppGate>
    </div>
  );
}
