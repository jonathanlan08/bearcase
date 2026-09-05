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
import { fmtPct } from "@/lib/format";

const num = (min = 0) => z.coerce.number({ message: "Enter a number" }).min(min, `Must be at least ${min}`);
const schema = z.object({
  company_name: z.string().trim().min(1, "Enter the company name").max(200),
  industry: z.string().trim().min(1, "Enter the industry").max(120),
  purchase_price: num(1),
  purchase_price_basis: z.enum(["enterprise_value", "equity_price"]),
  purchase_date: z.string().optional(),
  debt_amount: num(0),
  equity_amount: num(0),
  interest_rate_pct: num(0).max(40, "Rate must be 40% or less"),
  amortization_years: num(1).max(40),
  covenant_dscr_threshold: z.coerce.number().min(0).max(10).optional(),
});
type Form = { [K in keyof z.infer<typeof schema>]: string };

const initial: Form = { company_name: "", industry: "", purchase_price: "", purchase_price_basis: "enterprise_value", purchase_date: "", debt_amount: "", equity_amount: "", interest_rate_pct: "8.0", amortization_years: "10", covenant_dscr_threshold: "1.25" };

export default function NewDealPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const [form, setForm] = useState<Form>(initial);
  const [errors, setErrors] = useState<Partial<Record<keyof Form, string>>>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: (body: z.infer<typeof schema>) => api.post<Deal>("/api/deals", { ...body, purchase_date: body.purchase_date || null }),
    onSuccess: (d) => { qc.invalidateQueries(); router.push(`/app/deals/${d.id}/documents`); },
    onError: (e) => setServerError(e instanceof ApiError ? JSON.stringify(e.detail) : "Could not create the deal."),
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
      for (const i of r.error.issues) er[i.path[0] as keyof Form] = i.message;
      setErrors(er);
      document.getElementById("form-errors")?.focus();
      return;
    }
    setErrors({});
    create.mutate(r.data);
  };
  const debt = Number(form.debt_amount) || 0;
  const eq = Number(form.equity_amount) || 0;
  const leverage = debt + eq > 0 ? (debt / (debt + eq)) * 100 : null;
  const errorList = Object.entries(errors).filter(([, v]) => v);
  const F = (k: keyof Form, label: string, props: Partial<React.InputHTMLAttributes<HTMLInputElement>> & { help?: string; suffix?: string } = {}) => (
    <Field label={label} error={errors[k]} help={props.help} suffix={props.suffix} required={!props.placeholder?.includes("optional")}>
      {(p) => <input id={p.id} aria-describedby={p.describedBy} aria-invalid={p.invalid} name={k} className={inputClass(p.invalid, props.suffix ? "pr-12" : "")} value={form[k]} onChange={set(k)} onBlur={() => validateField(k)} type={props.type ?? "text"} inputMode={props.inputMode} step={props.step} placeholder={props.placeholder} />}
    </Field>
  );
  return (
    <div>
      <header className="flex h-14 items-center justify-between border-b border-hairline bg-bg-raised px-4 md:px-6"><Link href="/app"><Wordmark /></Link><Link href="/app" className="text-sm text-fg-muted hover:text-fg">All deals</Link></header>
      <main id="main" className="mx-auto max-w-xl px-4 py-8 md:px-6">
        <h1 className="text-[30px]">Create a deal</h1>
        <p className="mt-2 text-sm text-fg-muted">Enter the transaction terms. You will upload documents next.</p>
        {errorList.length > 0 && (
          <div id="form-errors" tabIndex={-1} role="alert" className="mt-6 rounded-[var(--radius-2)] border border-red/40 p-3 text-sm">
            <p className="font-medium text-red">Fix {errorList.length} field{errorList.length > 1 ? "s" : ""}:</p>
            <ul className="mt-1 list-disc pl-5">{errorList.map(([k, v]) => <li key={k}><a href={`#${k}`} className="underline" onClick={(e) => { e.preventDefault(); (document.querySelector(`[name="${k}"]`) as HTMLElement | null)?.focus(); }}>{v}</a></li>)}</ul>
          </div>
        )}
        <form className="mt-6 flex flex-col gap-4" onSubmit={submit} noValidate>
          {F("company_name", "Company name")}
          {F("industry", "Industry")}
          {F("purchase_price", "Purchase price", { type: "number", inputMode: "decimal", step: "1000", suffix: "USD" })}
          <Field label="Purchase-price basis" help="Enterprise value already includes debt; equity price will be grossed up with assumed debt and cash acquired.">
            {(p) => (
              <div role="radiogroup" aria-labelledby={p.id} className="flex gap-4 text-sm">
                {(["enterprise_value", "equity_price"] as const).map((v) => (
                  <label key={v} className="flex items-center gap-2"><input type="radio" name="purchase_price_basis" value={v} checked={form.purchase_price_basis === v} onChange={set("purchase_price_basis")} />{v === "enterprise_value" ? "Enterprise value" : "Equity price"}</label>
                ))}
              </div>
            )}
          </Field>
          {F("purchase_date", "Purchase date", { type: "date", placeholder: "optional" })}
          <div className="grid grid-cols-2 gap-4">
            {F("debt_amount", "Debt amount", { type: "number", inputMode: "decimal", step: "1000", suffix: "USD" })}
            {F("equity_amount", "Equity amount", { type: "number", inputMode: "decimal", step: "1000", suffix: "USD" })}
          </div>
          <p className="num text-xs text-fg-muted">Debt / (Debt + Equity) = {leverage === null ? "—" : fmtPct(leverage)}</p>
          <div className="grid grid-cols-2 gap-4">
            {F("interest_rate_pct", "Interest rate", { type: "number", inputMode: "decimal", step: "0.05", suffix: "% p.a." })}
            {F("amortization_years", "Amortization", { type: "number", inputMode: "numeric", step: "1", suffix: "years" })}
          </div>
          {F("covenant_dscr_threshold", "Covenant DSCR threshold", { type: "number", inputMode: "decimal", step: "0.05", suffix: "x", help: "Optional. Scenario results warn when year-1 DSCR falls below this.", placeholder: "optional" })}
          {serverError && <p role="alert" className="text-sm text-red">{serverError}</p>}
          <div className="mt-2 flex gap-2"><Button type="submit" loading={create.isPending}>Create deal</Button><Link href="/app" className={buttonClass("secondary")}>Cancel</Link></div>
        </form>
      </main>
    </div>
  );
}
