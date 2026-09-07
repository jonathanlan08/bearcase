"""A compact deal brief the chat model reads before answering: deal terms, statement headline lines, every
calculated metric, the add-back schedule, findings, scenarios, missing documents, and claim counts, each with
the citation id the model must use. Built only from persisted rows; nothing here calculates a number.

Why: on a free tier every provider request costs seconds and quota, and a reply that reads the deal through
tools needs two to five sequential requests. With the brief in the prompt most questions need none; the tools
remain for what the brief leaves out (claim wording, evidence passages, the full statement). Document text is
untrusted, so the brief carries ids and short labels only, never passages, and strips anything that could
read as markup or a citation marker.

Cached per deal: an entry is trusted for chat_brief_ttl_seconds, then its version stamp (newest metric,
row counts, add-back decisions) is rechecked and the text rebuilt only when the stamp moved. The analysis
pipeline and the review routes call invalidate_brief when they persist rows, so a change shows up in the
next reply even inside the TTL. The cache is per process; a multi-process deployment is bounded by the TTL."""

from __future__ import annotations

import hashlib
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bearcase.config import get_settings
from bearcase.engine.metrics import format_value
from bearcase.models import (
    Adjustment,
    Claim,
    Deal,
    Document,
    Evidence,
    FinancialMetric,
    FinancialPeriod,
    Finding,
    ReviewDecision,
    Scenario,
    ScenarioResult,
)
from bearcase.models.enums import DocumentStatus, FindingKind, MetricSource

BRIEF_TARGET_CHARS = 14000  # about 3,500 tokens at four characters per token
SHORT_ID = 8  # the shortest prefix resolve_citations accepts; lengthened only if two ids share it
LABEL_MAX = 120
RATIONALE_MAX = 160
PASSAGE_MAX = 200  # nothing quoted from a document may be longer than this
MAX_FINDINGS = 40
MAX_DOCUMENTS = 25
MAX_CACHE_ENTRIES = 256
HEADLINE_LINES = ("revenue", "gross_profit", "operating_expenses", "ebitda", "operating_income", "net_income")
SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
_UNSAFE = re.compile(r"[\[\]<>{}`]|\s+")
_CACHE: dict[uuid.UUID, _Entry] = {}


@dataclass
class _Entry:
    stamp: str
    text: str
    checked_at: float


def clean_label(text: str | None, limit: int = LABEL_MAX) -> str:
    """One line of plain text from a value that may come from a document: whitespace collapsed, brackets,
    braces, angle brackets, and backticks removed (so nothing can imitate a citation marker or a tag), and
    cut to `limit` characters. Never longer than PASSAGE_MAX."""
    if not text:
        return ""
    limit = min(limit, PASSAGE_MAX)
    out = _UNSAFE.sub(lambda m: " " if m.group(0).isspace() else "", str(text)).strip()
    return out if len(out) <= limit else out[: limit - 1].rstrip() + "…"


def short_ids(ids: set[str]) -> dict[str, str]:
    """Map every id to the shortest common prefix length (at least SHORT_ID) that keeps them distinct, so a
    marker built from the brief resolves to exactly one row."""
    length = SHORT_ID
    while length < 36 and len({i[:length] for i in ids}) < len(ids):
        length += 4
    return {i: i[:length] for i in ids}


def _fmt(value: Any, unit: str) -> str:
    return format_value(value, unit)


def _e_list(ids: list[Any], short: dict[str, str], limit: int = 3) -> str:
    known = [short[str(i)] for i in ids if str(i) in short][:limit]
    return f" E:{','.join(known)}" if known else ""


def _m_list(ids: list[Any], short: dict[str, str], limit: int = 2) -> str:
    known = [short[str(i)] for i in ids if str(i) in short][:limit]
    return f" M:{','.join(known)}" if known else ""


def _effective_status(claim: Claim) -> str:
    current = next((d for d in reversed(claim.review_decisions) if d.is_current), None)
    return current.resulting_status if current and current.resulting_status else claim.status.value


def render_brief(db: Session, deal: Deal) -> str:
    """Build the brief text from persisted rows. Deterministic for a given database state."""
    periods = list(
        db.scalars(select(FinancialPeriod).where(FinancialPeriod.deal_id == deal.id).order_by(FinancialPeriod.ordinal))
    )
    plabel = {p.id: p.label for p in periods}
    metrics = list(
        db.scalars(
            select(FinancialMetric)
            .where(FinancialMetric.deal_id == deal.id)
            .order_by(FinancialMetric.created_at, FinancialMetric.id)
        )
    )
    # one row per (key, period, source): the newest wins, as the tools and the financials page show it
    latest: dict[tuple[str, uuid.UUID | None, str], FinancialMetric] = {}
    for m in metrics:
        latest[(m.key, m.period_id, m.source.value)] = m
    metrics = list(latest.values())
    adjustments = list(
        db.scalars(select(Adjustment).where(Adjustment.deal_id == deal.id).order_by(Adjustment.sort_order, Adjustment.id))
    )
    findings = sorted(
        db.scalars(select(Finding).where(Finding.deal_id == deal.id)),
        key=lambda f: (SEVERITY_RANK.get(f.severity.value, 9), f.kind.value, f.title, str(f.id)),
    )
    scenarios = list(db.scalars(select(Scenario).where(Scenario.deal_id == deal.id).order_by(Scenario.sort_order, Scenario.id)))
    claims = list(db.scalars(select(Claim).where(Claim.deal_id == deal.id)))
    documents = list(db.scalars(select(Document).where(Document.deal_id == deal.id).order_by(Document.created_at, Document.id)))
    m_short = short_ids({str(m.id) for m in metrics})
    e_short = short_ids({str(e) for e in db.scalars(select(Evidence.id).where(Evidence.deal_id == deal.id))})

    lines: list[str] = []
    company = clean_label(deal.company_name, 80)
    lines.append(
        f"Deal: {company} ({clean_label(deal.industry, 60)}). Every id after M: or E: is a citation id for a metric "
        "or an evidence row; cite it in square brackets exactly as written here."
    )
    covenant = _fmt(deal.covenant_dscr_threshold, "multiple") if deal.covenant_dscr_threshold is not None else "none"
    terms = (
        f"Terms: purchase price {_fmt(deal.purchase_price, 'usd')} ({deal.purchase_price_basis.value}); "
        f"debt {_fmt(deal.debt_amount, 'usd')}; equity {_fmt(deal.equity_amount, 'usd')}; "
        f"rate {_fmt(deal.interest_rate_pct, 'pct')}; amortization {deal.amortization_years} years; "
        f"covenant DSCR {covenant}"
    )
    if deal.debt_assumed or deal.cash_acquired:
        terms += f"; debt assumed {_fmt(deal.debt_assumed, 'usd')}; cash acquired {_fmt(deal.cash_acquired, 'usd')}"
    lines.append(terms + ".")

    # statement headline lines, one line per key with every period
    by_key: dict[str, dict[uuid.UUID, FinancialMetric]] = {}
    for m in metrics:
        if m.source == MetricSource.EXTRACTED and m.period_id is not None:
            by_key.setdefault(m.key, {})[m.period_id] = m
    if periods and by_key:
        lines.append(f"Statement ({', '.join(plabel[p.id] for p in periods)}), mapped from the uploaded financials:")
        for key in HEADLINE_LINES:
            cells = by_key.get(key)
            if not cells:
                continue
            label = next(iter(cells.values())).label
            parts = [
                f"{plabel[p.id]} {_fmt(cells[p.id].value, cells[p.id].unit.value)} [M:{m_short[str(cells[p.id].id)]}]"
                for p in periods
                if p.id in cells
            ]
            lines.append(f"- {label}: {' | '.join(parts)}")
        other = sorted({k for k in by_key if k not in HEADLINE_LINES})
        if other:
            lines.append(f"- Other mapped lines (ids via get_financials): {', '.join(other)}")

    # every calculated, verified, and scenario metric
    derived = [m for m in metrics if m.source != MetricSource.EXTRACTED]
    if derived:
        lines.append("Metrics (persisted engine outputs; the formula is on the row):")
        for m in derived:
            period = f" ({plabel[m.period_id]})" if m.period_id and m.period_id in plabel else ""
            flag = " needs review" if m.requires_review else ""
            lines.append(f"- {m.label}{period}: {_fmt(m.value, m.unit.value)} [M:{m_short[str(m.id)]}]{flag}")

    if adjustments:
        lines.append("Add-backs (seller schedule with the decision on each; reviewer decisions are marked):")
        for a in adjustments:
            who = " (reviewer)" if a.decided_by_user_id is not None else ""
            why = clean_label(a.decision_rationale, RATIONALE_MAX)
            lines.append(
                f"- {clean_label(a.label)}: {_fmt(a.amount, 'usd')} {a.direction.value}; decision {a.decision.value}{who}"
                f"{'; ' + why if why else ''}{_e_list(a.evidence_ids, e_short)}"
            )

    missing = [f for f in findings if f.kind == FindingKind.MISSING_DOCUMENT]
    listed = [f for f in findings if f.kind != FindingKind.MISSING_DOCUMENT][:MAX_FINDINGS]
    if listed:
        lines.append("Findings (severity, kind, title; ids to cite):")
        for f in listed:
            lines.append(
                f"- ({f.severity.value}) {f.kind.value}: {clean_label(f.title, LABEL_MAX)}"
                f"{_e_list(f.evidence_ids, e_short)}{_m_list(f.metric_ids, m_short)}"
            )
        hidden = len(findings) - len(missing) - len(listed)
        if hidden > 0:
            lines.append(f"- ...and {hidden} more (get_findings)")

    if scenarios:
        lines.append("Scenarios (year 1 of the persisted run; assumptions and bridges via get_scenarios):")
        by_result: dict[str, list[str]] = {}
        for m in derived:
            rid = (m.input_snapshot or {}).get("scenario_result_id")
            if rid:
                by_result.setdefault(str(rid), []).append(m_short[str(m.id)])
        for sc in scenarios:
            r = sc.results[-1] if sc.results else None
            if r is None:
                lines.append(f"- {clean_label(sc.name, 60)} ({sc.kind.value}): not run")
                continue
            y1 = r.outputs.get("year1") or {}
            outs = (
                f"revenue {_fmt(y1.get('revenue'), 'usd')}, EBITDA {_fmt(y1.get('ebitda'), 'usd')}, "
                f"CFADS {_fmt(y1.get('cfads'), 'usd')}, debt service {_fmt(y1.get('debt_service'), 'usd')}, "
                f"DSCR {_fmt(y1.get('dscr'), 'multiple')}; cash-on-cash {_fmt(r.outputs.get('cash_on_cash_pct'), 'pct')}, "
                f"IRR {_fmt(r.outputs.get('irr_pct'), 'pct')}"
            )
            ids = by_result.get(str(r.id), [])
            warns = "; ".join(clean_label(w.get("message"), 100) for w in (r.warnings or [])[:3] if isinstance(w, dict))
            lines.append(
                f"- {clean_label(sc.name, 60)} ({sc.kind.value}): {outs}"
                f"{' M:' + ','.join(ids) if ids else ''}{'; warnings: ' + warns if warns else '; no warnings'}"
            )

    ready = [d for d in documents if d.status == DocumentStatus.READY]
    if ready:
        names = ", ".join(f"{clean_label(d.display_name, 60)} ({d.doc_type.value})" for d in ready[:MAX_DOCUMENTS])
        lines.append(f"Documents in the deal room ({len(ready)} processed): {names}.")
    if missing:
        lines.append("Missing documents (findings; there is no evidence to cite for an absence):")
        lines.extend(f"- ({f.severity.value}) {clean_label(f.title, LABEL_MAX)}" for f in missing)
    else:
        lines.append("Missing documents: none recorded.")

    counts: dict[str, int] = {}
    for c in claims:
        counts[_effective_status(c)] = counts.get(_effective_status(c), 0) + 1
    order = ("supported", "contradicted", "unsupported", "review_required", "pending")
    tally = ", ".join(f"{k.replace('_', ' ')} {counts[k]}" for k in order if k in counts)
    lines.append(
        f"Claims: {len(claims)} extracted ({tally or 'none'}). Wording, values, and evidence for each claim come from "
        "list_claims / get_claim."
    )
    return "\n".join(lines)


def brief_stamp(db: Session, deal: Deal) -> str:
    """Version of the rows the brief reads: newest metric, row counts, and a hash of the add-back decisions."""
    newest = db.scalar(select(func.max(FinancialMetric.created_at)).where(FinancialMetric.deal_id == deal.id))
    claims = db.scalar(select(func.count()).select_from(Claim).where(Claim.deal_id == deal.id))
    findings = db.scalar(select(func.count()).select_from(Finding).where(Finding.deal_id == deal.id))
    decisions = db.scalar(select(func.count()).select_from(ReviewDecision).where(ReviewDecision.deal_id == deal.id))
    results = db.scalar(select(func.count()).select_from(ScenarioResult).join(Scenario).where(Scenario.deal_id == deal.id))
    rows = db.execute(
        select(Adjustment.id, Adjustment.decision, Adjustment.decision_rationale).where(Adjustment.deal_id == deal.id)
    ).all()
    digest = hashlib.sha256("|".join(sorted(f"{i}:{d.value}:{r or ''}" for i, d, r in rows)).encode()).hexdigest()[:16]
    return f"{newest}|{claims}|{findings}|{decisions}|{results}|{digest}"


def build_brief(db: Session, deal: Deal) -> str:
    """The brief for a deal, from the cache when its stamp has not moved."""
    ttl = get_settings().chat_brief_ttl_seconds
    now = time.monotonic()
    entry = _CACHE.get(deal.id)
    if entry is not None and now - entry.checked_at < ttl:
        return entry.text
    stamp = brief_stamp(db, deal)
    if entry is not None and entry.stamp == stamp:
        entry.checked_at = now
        return entry.text
    text = render_brief(db, deal)
    if len(_CACHE) >= MAX_CACHE_ENTRIES:
        oldest = min(_CACHE, key=lambda k: _CACHE[k].checked_at)
        _CACHE.pop(oldest, None)
    _CACHE[deal.id] = _Entry(stamp=stamp, text=text, checked_at=now)
    return text


def invalidate_brief(deal_id: uuid.UUID) -> None:
    """Drop the cached brief for a deal. Called wherever analysis results or reviewer decisions are persisted."""
    _CACHE.pop(deal_id, None)


def cached_brief(deal_id: uuid.UUID) -> str | None:
    """The cached text, if any (tests and diagnostics)."""
    entry = _CACHE.get(deal_id)
    return entry.text if entry else None


def compact_brief(text: str, max_chars: int = 5500) -> str:
    """A shorter brief for providers that meter tokens per minute tightly: the statement table goes (the
    metrics section already carries the headline figures), the rest is kept in order and cut at a line."""
    sections: list[list[str]] = [[]]
    for line in text.split("\n"):
        if line and not line.startswith(" ") and line.endswith(":") and sections[-1]:
            sections.append([])
        sections[-1].append(line)
    kept = [sec for sec in sections if not (sec and sec[0].startswith("Statement"))]
    out = "\n".join("\n".join(sec) for sec in kept)
    if len(out) > max_chars:
        out = out[:max_chars].rsplit("\n", 1)[0] + "\n(brief shortened for this provider; open the app for the rest)"
    return out
