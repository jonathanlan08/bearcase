"""The bounded paid pilot through Stripe Checkout.

The Stripe SDK sits behind `StripeGateway`, so tests substitute a fake and no test or development run ever
contacts Stripe. A checkout creates a pending purchase; the webhook, verified with the signing secret, marks it
paid (idempotently) on checkout.session.completed. Prices are configuration (pilot_price_cents), never client
input.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from bearcase.api.deps import DbDep, UserDep, accepted_membership_ids
from bearcase.api.schemas import CheckoutRequest
from bearcase.audit import record
from bearcase.config import Settings, get_settings
from bearcase.models import Deal, Purchase
from bearcase.models.base import utcnow
from bearcase.models.enums import PurchaseKind, PurchaseStatus

log = logging.getLogger("bearcase.billing")
router = APIRouter(prefix="/billing", tags=["billing"])
PILOT_DESCRIPTION = "BearCase pilot: one deal checked end to end with support, for a bounded period."
SIGNATURE_HEADER = "stripe-signature"
SAAS_TAX_CODE = "txcd_10103001"  # Software as a service, business use


@dataclass
class CheckoutSession:
    id: str
    url: str


class StripeGateway(Protocol):
    def create_checkout_session(
        self,
        *,
        amount_cents: int,
        currency: str,
        description: str,
        success_url: str,
        cancel_url: str,
        reference: str,
        customer_email: str,
    ) -> CheckoutSession: ...

    def construct_event(self, payload: bytes, signature: str, secret: str) -> dict[str, Any]: ...


class StripeSdkGateway:
    """The real thing: imports the SDK lazily so the module loads without a key."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def create_checkout_session(
        self,
        *,
        amount_cents: int,
        currency: str,
        description: str,
        success_url: str,
        cancel_url: str,
        reference: str,
        customer_email: str,
    ) -> CheckoutSession:
        import stripe

        session = stripe.checkout.Session.create(
            api_key=self._api_key,
            mode="payment",
            line_items=[
                {
                    "quantity": 1,
                    "price_data": {
                        "currency": currency,
                        "unit_amount": amount_cents,
                        "product_data": {
                            "name": "BearCase pilot",
                            "description": description,
                            # Required when the Stripe account uses Managed Payments; harmless otherwise.
                            "tax_code": SAAS_TAX_CODE,
                        },
                    },
                }
            ],
            success_url=success_url,
            cancel_url=cancel_url,
            client_reference_id=reference,
            customer_email=customer_email,
            metadata={"purchase_id": reference},
        )
        if not session.url:
            raise RuntimeError("Stripe returned a checkout session without a URL")
        return CheckoutSession(id=session.id, url=session.url)

    def construct_event(self, payload: bytes, signature: str, secret: str) -> dict[str, Any]:
        import stripe

        try:
            event = stripe.Webhook.construct_event(payload, signature, secret)
        except (ValueError, stripe.error.SignatureVerificationError) as exc:  # type: ignore[attr-defined]
            raise SignatureError(str(exc)) from exc
        return event.to_dict_recursive()


class SignatureError(ValueError):
    pass


def get_gateway(settings: Settings | None = None) -> StripeGateway | None:
    """The configured gateway, or None when billing is not set up. Tests monkeypatch this."""
    s = settings or get_settings()
    if not s.stripe_secret_key:
        return None
    return StripeSdkGateway(s.stripe_secret_key)


def _purchase_out(p: Purchase) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "kind": p.kind.value,
        "amount_cents": p.amount_cents,
        "currency": p.currency,
        "status": p.status.value,
        "deal_id": str(p.deal_id) if p.deal_id else None,
        "created_at": p.created_at.isoformat(),
        "paid_at": p.paid_at.isoformat() if p.paid_at else None,
    }


@router.get("/status")
def billing_status(db: DbDep, user: UserDep) -> dict[str, Any]:
    s = get_settings()
    purchases = db.scalars(select(Purchase).where(Purchase.user_id == user.id).order_by(Purchase.created_at.desc())).all()
    return {
        "configured": bool(s.stripe_secret_key),
        "pilot": {"amount_cents": s.pilot_price_cents, "currency": s.pilot_currency, "description": PILOT_DESCRIPTION},
        "purchases": [_purchase_out(p) for p in purchases],
        "has_paid_pilot": any(p.status == PurchaseStatus.PAID for p in purchases),
    }


@router.post("/checkout")
def checkout(body: CheckoutRequest, db: DbDep, user: UserDep) -> dict[str, str]:
    s = get_settings()
    gateway = get_gateway(s)
    if gateway is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Payments are not set up on this deployment. Email us to start a pilot instead.",
        )
    if user.is_demo:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Create an account before starting a pilot.")
    deal_id = None
    if body.deal_id is not None:
        deal = db.scalar(
            select(Deal).where(
                Deal.id == body.deal_id,
                (Deal.owner_id == user.id) | Deal.id.in_(accepted_membership_ids(user.id)),
            )
        )
        if deal is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Deal not found.")
        deal_id = deal.id
    purchase = Purchase(
        user_id=user.id,
        kind=PurchaseKind.PILOT,
        amount_cents=s.pilot_price_cents,
        currency=s.pilot_currency,
        status=PurchaseStatus.PENDING,
        deal_id=deal_id,
    )
    db.add(purchase)
    db.flush()
    base = s.app_base_url.rstrip("/")
    try:
        session = gateway.create_checkout_session(
            amount_cents=purchase.amount_cents,
            currency=purchase.currency,
            description=PILOT_DESCRIPTION,
            success_url=f"{base}/pilot?status=success&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{base}/pilot?status=cancelled",
            reference=str(purchase.id),
            customer_email=user.email,
        )
    except Exception as exc:
        db.rollback()
        log.warning("checkout session could not be created: %s", type(exc).__name__)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "The payment provider did not answer. Try again in a minute.") from exc
    purchase.stripe_session_id = session.id
    record(
        db,
        user_id=user.id,
        deal_id=deal_id,
        event_type="purchase.started",
        object_type="purchase",
        object_id=purchase.id,
        summary=f"Started checkout for the pilot ({purchase.amount_cents / 100:.2f} {purchase.currency.upper()})",
        payload={"amount_cents": purchase.amount_cents, "currency": purchase.currency},
    )
    db.commit()
    return {"url": session.url, "purchase_id": str(purchase.id)}


@router.post("/webhook")
async def webhook(request: Request, db: DbDep) -> dict[str, Any]:
    """Stripe calls this; there is no user session. The signature is verified before the body is trusted."""
    s = get_settings()
    gateway = get_gateway(s)
    if gateway is None or not s.stripe_webhook_secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Payments are not set up on this deployment.")
    payload = await request.body()
    signature = request.headers.get(SIGNATURE_HEADER, "")
    try:
        event = gateway.construct_event(payload, signature, s.stripe_webhook_secret)
    except SignatureError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid signature.") from None
    kind = str(event.get("type", ""))
    session = (event.get("data") or {}).get("object") or {}
    if kind not in {"checkout.session.completed", "checkout.session.async_payment_failed", "checkout.session.expired"}:
        return {"received": True, "handled": False}
    purchase = _find_purchase(db, session)
    if purchase is None:
        log.warning("webhook %s for an unknown checkout session", kind)
        return {"received": True, "handled": False}
    if kind == "checkout.session.completed":
        if purchase.status == PurchaseStatus.PAID:
            return {"received": True, "handled": True, "updated": False}
        purchase.status = PurchaseStatus.PAID
        purchase.paid_at = utcnow()
        intent = session.get("payment_intent")
        purchase.stripe_payment_intent = intent if isinstance(intent, str) else None
        record(
            db,
            user_id=purchase.user_id,
            deal_id=purchase.deal_id,
            event_type="purchase.paid",
            object_type="purchase",
            object_id=purchase.id,
            summary=f"Pilot paid ({purchase.amount_cents / 100:.2f} {purchase.currency.upper()})",
        )
    else:
        if purchase.status == PurchaseStatus.PAID:
            return {"received": True, "handled": True, "updated": False}
        purchase.status = PurchaseStatus.FAILED
    db.commit()
    return {"received": True, "handled": True, "updated": True}


def _find_purchase(db, session: dict[str, Any]) -> Purchase | None:  # type: ignore[no-untyped-def]
    session_id = session.get("id")
    if isinstance(session_id, str):
        found = db.scalar(select(Purchase).where(Purchase.stripe_session_id == session_id))
        if found:
            return found
    reference = session.get("client_reference_id") or (session.get("metadata") or {}).get("purchase_id")
    if isinstance(reference, str):
        try:
            return db.get(Purchase, uuid.UUID(reference))
        except ValueError:
            return None
    return None
