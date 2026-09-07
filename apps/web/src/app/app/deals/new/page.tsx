"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { z } from "zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, type Deal } from "@/lib/api";
import { Button, buttonClass } from "@/components/ui/button";
import { Field, inputClass } from "@/components/ui/field";
import { Wordmark } from "@/components/ui/primitives";
import { StatusGlyph } from "@/components/domain/status";
import { fmtMoney, fmtPct, toNumber } from "@/lib/format";

/** A required number typed into a text field: blank is an error, never silently 0. */
const required = (label: string, min: number, max?: number, maxMessage?: string) =>
  z.string().trim().min(1, `Enter the ${label}`).pipe(z.coerce.number<string>({ error: "Enter a number" }).min(min, `Must be at least ${min}`).max(max ?? Number.MAX_SAFE_INTEGER, maxMessage ?? `Must be ${max} or less`));
/** An optional number: blank means "not provided". */
const optional = (min: number, max: number) =>
  z.preprocess((v) => (typeof v === "string" && v.trim() === "" ? undefined : v), z.coerce.number({ error: "Enter a number" }).min(min, `Must be at least ${min}`).max(max, `Must be ${max} or less`).optional());

const schema = z.object({
  company_name: z.string().trim().min(1, "Enter the company name").max(200, "Keep the company name under 200 characters"),
  industry: z.string().trim().min(1, "Enter the industry").max(120, "Keep the industry under 120 characters"),
  purchase_price: required("purchase price", 1),
  purchase_price_basis: z.enum(["enterprise_value", "equity_price"]),
  purchase_date: z.string().optional(),
  debt_amount: required("debt amount", 0),
  equity_amount: required("equity amount", 0),
  debt_assumed: optional(0, Number.MAX_SAFE_INTEGER),
  cash_acquired: optional(0, Number.MAX_SAFE_INTEGER),
  interest_rate_pct: required("interest rate", 0, 40, "Rate must be 40% or less"),
  amortization_years: required("amortization period", 1, 40, "Must be 40 years or less"),
  covenant_dscr_threshold: optional(0, 10),
}).superRefine((d, ctx) => {
  // Only when all three parsed: a blank field already carries its own error, and the raw string must never be added.
  const nums = [d.purchase_price, d.debt_amount, d.equity_amount];
  if (nums.every((n) => typeof n === "number" && Number.isFinite(n)) && Math.abs(d.debt_amount + d.equity_amount - d.purchase_price) > 0.5) ctx.addIssue({ code: "custom", path: ["equity_amount"], message: "Debt plus equity must equal the purchase price." });
});
type Form = { [K in keyof z.infer<typeof schema>]: string };

const initial: Form = { company_name: "", industry: "", purchase_price: "", purchase_price_basis: "enterprise_value", purchase_date: "", debt_amount: "", equity_amount: "", debt_assumed: "", cash_acquired: "", interest_rate_pct: "8.0", amortization_years: "10", covenant_dscr_threshold: "1.25" };

/** FastAPI validation errors arrive as [{loc, msg}]; show the field and message instead of raw JSON. */
function describeServerError(detail: unknown): string {
  if (Array.isArray(detail)) return detail.map((x) => (x && typeof x === "object" && "msg" in x ? `${String((x as { loc?: unknown[] }).loc?.slice(-1)[0] ?? "field").replace(/_/g, " ")}: ${String((x as { msg: unknown }).msg)}` : String(x))).join("; ");
  if (typeof detail === "string") return detail;
  return "Could not create the deal.";
}

export default function NewDealPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const [form, setForm] = useState<Form>(initial);
  const [errors, setErrors] = useState<Partial<Record<keyof Form, string>>>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: (body: z.infer<typeof schema>) => api.post<Deal>("/api/deals", { ...body, purchase_date: body.purchase_date || null, covenant_dscr_threshold: body.covenant_dscr_threshold ?? null, debt_assumed: body.purchase_price_basis === "equity_price" ? body.debt_assumed ?? 0 : 0, cash_acquired: body.purchase_price_basis === "equity_price" ? body.cash_acquired ?? 0 : 0 }),
    onSuccess: (d) => { qc.invalidateQueries(); router.push(`/app/deals/${d.id}/documents`); },
    onError: (e) => setServerError(e instanceof ApiError ? describeServerError(e.detail) : "Could not create the deal."),
  });
  const set = (k: keyof Form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setForm({ ...form, [k]: e.target.value });
  const validateField = (k: keyof Form) => {
    const r = schema.shape[k].safeParse(form[k]);
    setErrors((er) => ({ ...er, [k]: r.success ? undefined : r.error.issues[0]?.message }));
  };
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const r = schema.safeParse(form);
    if (!r.success) {
      const er: Partial<Record<keyof Form, string>> = {};
      for (const i of r.error.issues) { const k = i.path[0] as keyof Form; if (!er[k]) er[k] = i.message; }
      setErrors(er);
      document.getElementById("form-errors")?.focus();
      return;
    }
    setErrors({});
    setServerError(null);
    create.mutate(r.data);
  };
  const equityBasis = form.purchase_price_basis === "equity_price";
  const price = toNumber(form.purchase_price), debt = toNumber(form.debt_amount), eq = toNumber(form.equity_amount);
  const sum = debt !== null && eq !== null ? debt + eq : null;
  const gap = sum !== null && price !== null ? price - sum : null;
  const leverage = sum !== null && sum > 0 && debt !== null ? (debt / sum) * 100 : null;
  const canFill = price !== null && debt !== null && price - debt >= 0;
  const errorList = Object.entries(errors).filter(([, v]) => v);
  const F = (k: keyof Form, label: string, props: Partial<React.InputHTMLAttributes<HTMLInputElement>> & { help?: string; suffix?: string; optional?: boolean } = {}) => (
    <Field label={label} error={errors[k]} help={props.help} suffix={props.suffix} required={!props.optional}>
      {(p) => <input id={p.id} aria-describedby={p.describedBy} aria-invalid={p.invalid} name={k} className={inputClass(p.invalid, props.suffix ? "pr-14" : "")} value={form[k]} onChange={set(k)} onBlur={() => validateField(k)} type={props.type ?? "text"} inputMode={props.inputMode} step={props.step} min={props.min} placeholder={props.placeholder} />}
    </Field>
  );
  return (
    <div>
      <header className="flex h-14 items-center justify-between border-b border-hairline bg-bg-raised px-4 md:px-6"><Link href="/app"><Wordmark /></Link><Link href="/app" className="text-sm text-fg-muted hover:text-fg">All deals</Link></header>
      <main id="main" className="mx-auto max-w-xl px-4 py-8 md:px-6">
        <h1 className="text-[30px]">Create a deal</h1>
        <p className="mt-2 text-sm text-fg-muted">Enter the terms of the transaction as you understand them today. You will upload the seller’s documents next, and every figure here can be changed in the Scenario Lab.</p>
        {errorList.length > 0 && (
          <div id="form-errors" tabIndex={-1} role="alert" className="mt-6 rounded-[var(--radius-2)] border border-red/40 p-3 text-sm">
            <p className="font-medium text-red">Fix {errorList.length} field{errorList.length > 1 ? "s" : ""}:</p>
            <ul className="mt-1 list-disc pl-5">{errorList.map(([k, v]) => <li key={k}><a href={`#${k}`} className="underline" onClick={(e) => { e.preventDefault(); (document.querySelector(`[name="${k}"]`) as HTMLElement | null)?.focus(); }}>{v}</a></li>)}</ul>
          </div>
        )}
        <form className="mt-6 flex flex-col gap-4" onSubmit={submit} noValidate>
          {F("company_name", "Company name")}
          {F("industry", "Industry", { placeholder: "e.g. Commercial HVAC services" })}
          {F("purchase_price", "Purchase price", { type: "number", inputMode: "decimal", step: "1000", min: 0, suffix: "USD", help: "Whole dollars. The debt and equity below must add up to this amount." })}
          <Field label="What the purchase price covers" help={equityBasis ? "Equity price: the price of the shares only. Add any debt you take over and cash that comes with the business so the engine can work out the enterprise value." : "Enterprise value: the price for the whole business, debt included. Nothing else is added."}>
            {(p) => (
              <div role="radiogroup" aria-labelledby={p.id} className="flex flex-wrap gap-4 text-sm">
                {(["enterprise_value", "equity_price"] as const).map((v) => (
                  <label key={v} className="flex items-center gap-2"><input type="radio" name="purchase_price_basis" value={v} checked={form.purchase_price_basis === v} onChange={set("purchase_price_basis")} />{v === "enterprise_value" ? "Enterprise value" : "Equity price"}</label>
                ))}
              </div>
            )}
          </Field>
          {equityBasis && (
            <div className="grid grid-cols-2 gap-4">
              {F("debt_assumed", "Debt assumed", { type: "number", inputMode: "decimal", step: "1000", min: 0, suffix: "USD", optional: true, help: "Existing loans you take over. Leave blank for none." })}
              {F("cash_acquired", "Cash acquired", { type: "number", inputMode: "decimal", step: "1000", min: 0, suffix: "USD", optional: true, help: "Cash left in the business at closing. Leave blank for none." })}
            </div>
          )}
          {F("purchase_date", "Purchase date", { type: "date", optional: true, help: "Optional. Expected closing date." })}
          <fieldset className="flex flex-col gap-4">
            <legend className="text-sm font-medium">How the price is funded</legend>
            <div className="grid grid-cols-2 gap-4">
              {F("debt_amount", "Debt amount", { type: "number", inputMode: "decimal", step: "1000", min: 0, suffix: "USD", help: "Acquisition loan." })}
              {F("equity_amount", "Equity amount", { type: "number", inputMode: "decimal", step: "1000", min: 0, suffix: "USD", help: "Cash you and your investors put in." })}
            </div>
            <FundingHint price={price} sum={sum} gap={gap} leverage={leverage} onFill={canFill ? () => { setForm({ ...form, equity_amount: String(price! - debt!) }); setErrors((er) => ({ ...er, equity_amount: undefined })); } : undefined} />
          </fieldset>
          <div className="grid grid-cols-2 gap-4">
            {F("interest_rate_pct", "Interest rate", { type: "number", inputMode: "decimal", step: "0.05", min: 0, suffix: "% p.a." })}
            {F("amortization_years", "Amortization", { type: "number", inputMode: "numeric", step: "1", min: 1, suffix: "years", help: "Years to repay the loan in full." })}
          </div>
          {F("covenant_dscr_threshold", "Covenant DSCR threshold", { type: "number", inputMode: "decimal", step: "0.05", min: 0, suffix: "x", optional: true, help: "Optional. The minimum debt coverage your lender requires; scenarios warn when year-1 coverage falls below it. Leave blank if there is no covenant." })}
          {serverError && <p role="alert" className="text-sm text-red">{serverError}</p>}
          <div className="mt-2 flex gap-2"><Button type="submit" loading={create.isPending}>Create deal</Button><Link href="/app" className={buttonClass("secondary")}>Cancel</Link></div>
        </form>
      </main>
    </div>
  );
}

/** Live arithmetic on the three typed amounts: presentation only, so the user sees the gap before submitting. */
function FundingHint({ price, sum, gap, leverage, onFill }: { price: number | null; sum: number | null; gap: number | null; leverage: number | null; onFill?: () => void }) {
  if (sum === null || price === null) return <p className="text-xs text-fg-muted" aria-live="polite">Debt + equity must add up to the purchase price.</p>;
  const matches = gap !== null && Math.abs(gap) <= 0.5;
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs" aria-live="polite">
      <span className="inline-flex items-center gap-1.5"><StatusGlyph status={matches ? "supported" : "review_required"} size={12} /><span className="num">{fmtMoney(sum)}</span>{matches ? <span>matches the purchase price</span> : <span>funded of <span className="num">{fmtMoney(price)}</span>; <span className="num">{fmtMoney(Math.abs(gap ?? 0))}</span> {(gap ?? 0) > 0 ? "still to fund" : "over the price"}</span>}</span>
      {leverage !== null && <span className="num text-fg-muted">Debt share {fmtPct(leverage)}</span>}
      {!matches && onFill && <button type="button" className="text-accent underline-offset-2 hover:underline" onClick={onFill}>Set equity to the remainder</button>}
    </div>
  );
}
