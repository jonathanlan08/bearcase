"""Report citation validation. A material statement is any narrative sentence containing a digit
or a currency/percent symbol. Each must cite at least one resolvable evidence or metric id, or
sit inside a section explicitly marked as analysis derived from named metric inputs."""

from __future__ import annotations

import re
from typing import Any

_MATERIAL = re.compile(r"\d|\$|%")


def validate_sections(sections: list[dict[str, Any]], evidence_ids: set[str], metric_ids: set[str]) -> dict[str, Any]:
    uncited: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    total = 0
    material = 0
    cited = 0
    for section in sections:
        derived = section.get("derived_from") or []
        for i, stmt in enumerate(section.get("statements", [])):
            total += 1
            text = stmt.get("text", "")
            ev = [str(e) for e in stmt.get("evidence_ids", [])]
            me = [str(m) for m in stmt.get("metric_ids", [])]
            bad_ev = [e for e in ev if e not in evidence_ids]
            bad_me = [m for m in me if m not in metric_ids]
            if bad_ev or bad_me:
                unresolved.append({"section": section["key"], "index": i, "evidence_ids": bad_ev, "metric_ids": bad_me})
            if _MATERIAL.search(text):
                material += 1
                if (ev and not bad_ev) or (me and not bad_me) or derived:
                    cited += 1
                else:
                    uncited.append({"section": section["key"], "index": i, "text": text[:160]})
        for row in section.get("table", {}).get("rows", []):
            total += 1
            for e in row.get("evidence_ids", []):
                if str(e) not in evidence_ids:
                    unresolved.append({"section": section["key"], "row": row.get("label"), "evidence_ids": [str(e)]})
    return {
        "valid": not uncited and not unresolved,
        "statements_total": total,
        "material_statements": material,
        "material_cited": cited,
        "uncited": uncited,
        "unresolved": unresolved,
    }
