from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from bearcase.api.deps import DbDep, DealDep, UserDep
from bearcase.api.schemas import (
    AssumptionsUpdate,
    ScenarioCreate,
    ScenarioFactsOut,
    ScenarioOut,
    ScenarioResultOut,
    SensitivityRequest,
)
from bearcase.audit import record
from bearcase.engine.scenarios import ASSUMPTION_SPECS, ScenarioInputs, sensitivity_grid
from bearcase.models import Scenario, ScenarioAssumption
from bearcase.models.enums import ClaimUnit, ScenarioKind
from bearcase.pipeline.analyze import ensure_scenarios, run_scenario, scenario_facts

router = APIRouter(tags=["scenarios"])
SPEC_BY_KEY = {s["key"]: s for s in ASSUMPTION_SPECS}


def _out(sc: Scenario) -> ScenarioOut:
    o = ScenarioOut.model_validate(sc)
    o.latest_result = ScenarioResultOut.model_validate(sc.results[-1]) if sc.results else None
    o.result_count = len(sc.results)
    return o


def _get(deal, scenario_id: uuid.UUID, db) -> Scenario:  # type: ignore[no-untyped-def]
    sc = db.scalar(select(Scenario).where(Scenario.id == scenario_id, Scenario.deal_id == deal.id))
    if sc is None:
        raise HTTPException(404, "Scenario not found.")
    return sc


@router.get("/deals/{deal_id}/scenarios", response_model=list[ScenarioOut])
def list_scenarios(deal: DealDep, db: DbDep) -> list[ScenarioOut]:
    return [
        _out(s)
        for s in db.scalars(
            select(Scenario).where(Scenario.deal_id == deal.id).order_by(Scenario.sort_order, Scenario.created_at)
        )
    ]


@router.get("/deals/{deal_id}/scenarios/facts", response_model=ScenarioFactsOut)
def facts(deal: DealDep, db: DbDep) -> ScenarioFactsOut:
    fa, missing = scenario_facts(db, deal)
    return ScenarioFactsOut(
        facts={k: (str(v) if isinstance(v, Decimal) else v) for k, v in fa.items()}, missing=missing, specs=ASSUMPTION_SPECS
    )


@router.post("/deals/{deal_id}/scenarios", response_model=ScenarioOut, status_code=201)
def create_scenario(deal: DealDep, body: ScenarioCreate, db: DbDep, user: UserDep) -> ScenarioOut:
    existing = ensure_scenarios(db, deal)
    base = (
        _get(deal, body.base_on_scenario_id, db)
        if body.base_on_scenario_id
        else next((s for s in existing if s.kind == ScenarioKind.BASE), existing[0])
    )
    sc = Scenario(
        deal_id=deal.id,
        name=body.name,
        kind=ScenarioKind.CUSTOM,
        description=body.description,
        is_seed=False,
        sort_order=100 + len(existing),
    )
    db.add(sc)
    db.flush()
    for a in base.assumptions:
        db.add(
            ScenarioAssumption(scenario_id=sc.id, key=a.key, label=a.label, value=a.value, unit=a.unit, sort_order=a.sort_order)
        )
    record(
        db,
        deal_id=deal.id,
        user_id=user.id,
        event_type="scenario.created",
        object_type="scenario",
        object_id=sc.id,
        summary=f"Created scenario '{sc.name}' from '{base.name}'",
    )
    db.commit()
    db.refresh(sc)
    return _out(sc)


@router.put("/deals/{deal_id}/scenarios/{scenario_id}/assumptions", response_model=ScenarioOut)
def update_assumptions(deal: DealDep, scenario_id: uuid.UUID, body: AssumptionsUpdate, db: DbDep, user: UserDep) -> ScenarioOut:
    sc = _get(deal, scenario_id, db)
    changes = {}
    by_key = {a.key: a for a in sc.assumptions}
    for key, value in body.values.items():
        spec = SPEC_BY_KEY.get(key)
        if spec is None:
            raise HTTPException(422, f"Unknown assumption '{key}'.")
        if not (Decimal(spec["min"]) <= value <= Decimal(spec["max"])):
            raise HTTPException(422, f"{spec['label']} must be between {spec['min']} and {spec['max']}.")
        if key in by_key:
            changes[key] = {"from": str(by_key[key].value), "to": str(value)}
            by_key[key].value = value
        else:
            db.add(
                ScenarioAssumption(
                    scenario_id=sc.id,
                    key=key,
                    label=spec["label"],
                    value=value,
                    unit=ClaimUnit(spec["unit"]),
                    sort_order=ASSUMPTION_SPECS.index(spec),
                )
            )
            changes[key] = {"from": "", "to": str(value)}
    record(
        db,
        deal_id=deal.id,
        user_id=user.id,
        event_type="scenario.assumptions_updated",
        object_type="scenario",
        object_id=sc.id,
        summary=f"Updated {len(changes)} assumptions on '{sc.name}'",
        payload={"changes": changes},
    )
    db.commit()
    db.refresh(sc)
    return _out(sc)


@router.post("/deals/{deal_id}/scenarios/{scenario_id}/run", response_model=ScenarioResultOut, status_code=201)
def run(deal: DealDep, scenario_id: uuid.UUID, db: DbDep, user: UserDep) -> ScenarioResultOut:
    sc = _get(deal, scenario_id, db)
    try:
        result = run_scenario(db, deal, sc, user.id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.commit()
    return ScenarioResultOut.model_validate(result)


@router.get("/deals/{deal_id}/scenarios/{scenario_id}/results", response_model=list[ScenarioResultOut])
def results(deal: DealDep, scenario_id: uuid.UUID, db: DbDep) -> list[ScenarioResultOut]:
    sc = _get(deal, scenario_id, db)
    return [ScenarioResultOut.model_validate(r) for r in sc.results]


@router.post("/deals/{deal_id}/scenarios/sensitivity")
def sensitivity(deal: DealDep, body: SensitivityRequest, db: DbDep) -> dict:
    sc = _get(deal, body.scenario_id, db)
    fa, missing = scenario_facts(db, deal)
    if missing:
        raise HTTPException(409, "Scenario inputs missing: " + ", ".join(missing))
    for k in (body.row_key, body.col_key):
        if k not in SPEC_BY_KEY:
            raise HTTPException(422, f"Unknown assumption '{k}'.")
    if len(body.row_values) > 9 or len(body.col_values) > 9:
        raise HTTPException(422, "At most 9 values per axis.")
    kwargs: dict[str, Any] = {**fa, **{a.key: a.value for a in sc.assumptions}}
    inp = ScenarioInputs(**kwargs)
    return sensitivity_grid(inp, body.row_key, body.row_values, body.col_key, body.col_values, body.output)
