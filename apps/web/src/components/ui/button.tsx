import { forwardRef } from "react";
import { Loader2 } from "lucide-react";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";
export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> { variant?: Variant; size?: Size; loading?: boolean; icon?: React.ReactNode }

const base = "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-[var(--radius-1)] font-medium transition-colors duration-[120ms] disabled:opacity-50 select-none";
const variants: Record<Variant, string> = {
  primary: "bg-accent text-on-accent hover:bg-accent-strong",
  secondary: "border border-hairline bg-transparent text-fg hover:bg-bg-muted",
  ghost: "bg-transparent text-fg hover:bg-bg-muted",
  danger: "border border-red text-red hover:bg-red/10",
};
const sizes: Record<Size, string> = { sm: "h-8 px-3 text-sm", md: "h-10 px-4 text-sm" };

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button({ variant = "primary", size = "md", loading, icon, className = "", children, disabled, ...rest }, ref) {
  return (
    <button ref={ref} className={`${base} ${variants[variant]} ${sizes[size]} ${className}`} disabled={disabled || loading} aria-busy={loading || undefined} {...rest}>
      {loading ? <Loader2 size={16} className="animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
});

export function buttonClass(variant: Variant = "primary", size: Size = "md", extra = ""): string {
  return `${base} ${variants[variant]} ${sizes[size]} ${extra}`;
}
