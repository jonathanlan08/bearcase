"use client";

import { useId } from "react";

interface FieldProps { label: string; help?: string; error?: string; suffix?: string; required?: boolean; children: (props: { id: string; describedBy: string | undefined; invalid: boolean }) => React.ReactNode }

export function Field({ label, help, error, suffix, required, children }: FieldProps) {
  const id = useId();
  const helpId = help ? `${id}-help` : undefined;
  const errId = error ? `${id}-err` : undefined;
  const describedBy = [helpId, errId].filter(Boolean).join(" ") || undefined;
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
        {required && <span aria-hidden className="text-fg-muted"> *</span>}
      </label>
      <div className="relative">
        {children({ id, describedBy, invalid: !!error })}
        {suffix && <span aria-hidden className="pointer-events-none absolute inset-y-0 right-3 flex items-center font-mono text-xs text-fg-muted">{suffix}</span>}
      </div>
      {help && !error && <p id={helpId} className="text-xs text-fg-muted">{help}</p>}
      {error && (
        <p id={errId} role="alert" className="flex items-center gap-1 text-xs text-red">
          <span aria-hidden>▲</span> {error}
        </p>
      )}
    </div>
  );
}

export const inputClass = (invalid?: boolean, extra = "") => `h-10 w-full rounded-[var(--radius-1)] border bg-bg-raised px-3 text-sm text-fg placeholder:text-fg-muted/70 focus:border-accent ${invalid ? "border-red" : "border-hairline"} ${extra}`;
