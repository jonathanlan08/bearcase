"""Accounts, sharing, chat budget, and billing: verification and reset links, invitations end to end with two
clients, member roles on the mutating routes, the monthly answer budget, and Stripe checkout behind a fake."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import uuid
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from bearcase.api.app import app
from bearcase.api.routes import billing as billing_route
from bearcase.api.routes import chat as chat_route
from bearcase.api.routes.auth import token_hash
from bearcase.api.routes.billing import CheckoutSession, SignatureError
from bearcase.config import Settings
from bearcase.db import get_session_factory
from bearcase.email import console_outbox, last_email_to
from bearcase.models import AuditEvent, AuthToken, ChatMessage, ChatThread, DealMember, Purchase, User, UserSession
from bearcase.models.base import utcnow
from bearcase.models.enums import TokenPurpose
from bearcase.seed import seed_northstar

CSV = b"customer_name,revenue_type,revenue\nA,maintenance,100\nB,project,50\n"
PASSWORD = "password123"


def _register(email: str, name: str = "Person") -> TestClient:
    c = TestClient(app)
    r = c.post("/api/auth/register", json={"email": email, "password": PASSWORD, "display_name": name})
    assert r.status_code == 201, r.text
    return c


def _token_from(email: str, path: str) -> str:
    """The token in the newest console email to `email` whose link has `path`."""
    for message in reversed(console_outbox()):
        if message.to.lower() != email.lower():
            continue
        m = re.search(rf"http://localhost:3000{path}\?token=([A-Za-z0-9_\-]+)", message.text)
        if m:
            return m.group(1)
    raise AssertionError(f"no {path} link mailed to {email}")


def _verify(c: TestClient, email: str) -> None:
    r = c.post("/api/auth/verify", json={"token": _token_from(email, "/verify")})
    assert r.status_code == 200 and r.json() == {"verified": True}, r.text


def _seed_deal(c: TestClient) -> str:
    me = c.get("/api/auth/me").json()
    session = get_session_factory()()
    try:
        user = session.get(User, uuid.UUID(me["id"]))
        assert user is not None
        deal_id = str(seed_northstar(session, user).id)
        session.commit()
    finally:
        session.close()
    return deal_id


def _upload(c: TestClient, deal_id: str) -> Any:
    return c.post(
        f"/api/deals/{deal_id}/documents", files=[("files", ("revenue.csv", CSV, "text/csv"))], params={"process": "false"}
    )


# ---- verification -----------------------------------------------------------------------------------------


def test_register_sends_a_verification_email_and_the_link_is_single_use(db):
    email = "verify-me@example.com"
    before = len(console_outbox())
    c = _register(email, "Verify Me")
    assert len(console_outbox()) == before + 1
    message = last_email_to(email)
    assert message is not None and message.subject == "Confirm your BearCase email" and message.html
    assert "/verify?token=" in message.text
    me = c.get("/api/auth/me").json()
    assert me["email_verified"] is False and me["is_demo"] is False
    token = _token_from(email, "/verify")
    assert db.scalar(select(AuthToken).where(AuthToken.token_hash == token_hash(token))) is not None
    assert not any(t.token_hash == token for t in db.scalars(select(AuthToken)))  # only the hash is stored
    r = c.post("/api/auth/verify", json={"token": token})
    assert r.status_code == 200 and r.json() == {"verified": True}
    assert c.get("/api/auth/me").json()["email_verified"] is True
    r = c.post("/api/auth/verify", json={"token": token})
    assert r.status_code == 400 and "already been used" in r.json()["detail"]
    assert c.post("/api/auth/verify", json={"token": "not-a-real-token-at-all"}).status_code == 400
    # a verified account asking again is told so without a new message
    assert c.post("/api/auth/resend-verification").json() == {"sent": False, "verified": True}


def test_verification_link_expires_after_24_hours(db):
    email = "expired@example.com"
    c = _register(email)
    token = _token_from(email, "/verify")
    row = db.scalar(select(AuthToken).where(AuthToken.token_hash == token_hash(token)))
    assert row is not None and row.purpose == TokenPurpose.VERIFY
    assert timedelta(hours=23) < row.expires_at - row.created_at <= timedelta(hours=24)
    row.expires_at = utcnow() - timedelta(minutes=1)
    db.commit()
    r = c.post("/api/auth/verify", json={"token": token})
    assert r.status_code == 400 and "expired" in r.json()["detail"]
    assert c.get("/api/auth/me").json()["email_verified"] is False
    # resend issues a fresh link and retires the old one
    assert c.post("/api/auth/resend-verification").json() == {"sent": True, "verified": False}
    fresh = _token_from(email, "/verify")
    assert fresh != token
    assert c.post("/api/auth/verify", json={"token": fresh}).json() == {"verified": True}


def test_demo_visitors_cannot_resend_verification():
    c = TestClient(app)
    assert c.post("/api/demo/session").status_code == 200
    assert c.get("/api/auth/me").json()["email_verified"] is False
    assert c.post("/api/auth/resend-verification").status_code == 400


# ---- password reset ---------------------------------------------------------------------------------------


def test_request_reset_is_always_200_and_reset_changes_password_and_revokes_sessions(db):
    email = "reset-me@example.com"
    before = len(console_outbox())
    first = _register(email, "Reset Me")
    second = TestClient(app)
    assert second.post("/api/auth/login", json={"email": email, "password": PASSWORD}).status_code == 200
    user_id = uuid.UUID(first.get("/api/auth/me").json()["id"])
    assert db.scalar(select(func.count(UserSession.id)).where(UserSession.user_id == user_id)) == 2

    anon = TestClient(app)
    r = anon.post("/api/auth/request-reset", json={"email": "nobody-here@example.com"})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert len(console_outbox()) == before + 1  # registration only; nothing for the unknown address
    r = anon.post("/api/auth/request-reset", json={"email": email.upper()})
    assert r.status_code == 200
    message = last_email_to(email)
    assert message is not None and message.subject == "Reset your BearCase password" and "/reset?token=" in message.text
    token = _token_from(email, "/reset")
    row = db.scalar(select(AuthToken).where(AuthToken.token_hash == token_hash(token)))
    assert row is not None and row.purpose == TokenPurpose.RESET
    assert row.expires_at - row.created_at <= timedelta(hours=1)

    assert anon.post("/api/auth/reset", json={"token": token, "password": "short"}).status_code == 422
    r = anon.post("/api/auth/reset", json={"token": token, "password": "new-password-456"})
    assert r.status_code == 200 and r.json() == {"ok": True}
    db.expire_all()
    assert db.scalar(select(func.count(UserSession.id)).where(UserSession.user_id == user_id)) == 0
    assert first.get("/api/auth/me").status_code == 401 and second.get("/api/auth/me").status_code == 401
    assert anon.post("/api/auth/login", json={"email": email, "password": PASSWORD}).status_code == 401
    r = anon.post("/api/auth/login", json={"email": email, "password": "new-password-456"})
    assert r.status_code == 200 and r.json()["email_verified"] is True  # the link proved the mailbox
    r = anon.post("/api/auth/reset", json={"token": token, "password": "another-password-789"})
    assert r.status_code == 400 and "already been used" in r.json()["detail"]


# ---- sharing ----------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def shared() -> dict[str, Any]:
    owner = _register("share-owner@example.com", "Owner")
    _verify(owner, "share-owner@example.com")
    deal_id = _seed_deal(owner)
    return {"owner": owner, "deal_id": deal_id}


def test_sharing_needs_a_verified_owner(db):
    owner = _register("unverified-owner@example.com", "Unverified")
    deal_id = _seed_deal(owner)
    r = owner.post(f"/api/deals/{deal_id}/members", json={"email": "friend@example.com", "role": "viewer"})
    assert r.status_code == 403 and "Verify your email" in r.json()["detail"]
    _verify(owner, "unverified-owner@example.com")
    r = owner.post(f"/api/deals/{deal_id}/members", json={"email": "friend@example.com", "role": "viewer"})
    assert r.status_code == 201, r.text


def test_invite_flow_viewer_then_editor(shared, db):
    owner, deal_id = shared["owner"], shared["deal_id"]
    invitee_email = "collaborator@example.com"
    r = owner.post(f"/api/deals/{deal_id}/members", json={"email": invitee_email.upper(), "role": "viewer"})
    assert r.status_code == 201, r.text
    member = r.json()
    assert member["email"] == invitee_email and member["role"] == "viewer" and member["accepted"] is False
    message = last_email_to(invitee_email)
    assert message is not None and "Northstar" in message.subject and "/invite?token=" in message.text
    token = _token_from(invitee_email, "/invite")
    listing = owner.get(f"/api/deals/{deal_id}/members").json()
    assert listing["owner"]["email"] == "share-owner@example.com" and listing["role"] == "owner" and listing["limit"] == 5
    assert [(m["email"], m["accepted"]) for m in listing["members"]] == [(invitee_email, False)]

    # a stranger sees nothing, before and after the invitation is accepted
    stranger = _register("stranger-two@example.com", "Stranger")
    assert stranger.get(f"/api/deals/{deal_id}").status_code == 404
    assert stranger.get(f"/api/deals/{deal_id}/members").status_code == 404
    # the wrong account cannot accept, and the link stays usable for the right one
    r = stranger.post("/api/invites/accept", json={"token": token})
    assert r.status_code == 403 and invitee_email in r.json()["detail"]

    invitee = _register(invitee_email, "Collaborator")
    assert invitee.get(f"/api/deals/{deal_id}").status_code == 404  # pending, not yet a member
    r = invitee.post("/api/invites/accept", json={"token": token})
    assert r.status_code == 200 and r.json() == {"deal_id": deal_id}, r.text
    assert invitee.post("/api/invites/accept", json={"token": token}).status_code == 400  # single use

    # viewer: read and chat, no changes
    assert invitee.get(f"/api/deals/{deal_id}").status_code == 200
    assert invitee.get(f"/api/deals/{deal_id}/claims").status_code == 200
    assert invitee.get(f"/api/deals/{deal_id}/seller-questions/export?format=md").status_code == 200
    shared_row = next(d for d in invitee.get("/api/deals").json() if d["id"] == deal_id)
    assert shared_row["role"] == "viewer"
    r = invitee.post(f"/api/deals/{deal_id}/chat", json={"message": "Which documents are missing?"})
    assert r.status_code == 200 and "event: done" in r.text
    r = _upload(invitee, deal_id)
    assert r.status_code == 403 and "editor access" in r.json()["detail"]
    assert invitee.post(f"/api/deals/{deal_id}/process").status_code == 403
    claim_id = invitee.get(f"/api/deals/{deal_id}/claims").json()[0]["id"]
    assert invitee.post(f"/api/deals/{deal_id}/claims/{claim_id}/review", json={"action": "accept"}).status_code == 403
    scenario_id = invitee.get(f"/api/deals/{deal_id}/scenarios").json()[0]["id"]
    assert invitee.post(f"/api/deals/{deal_id}/scenarios/{scenario_id}/run").status_code == 403
    assert invitee.get(f"/api/deals/{deal_id}/review-dataset").status_code == 403
    assert invitee.post(f"/api/deals/{deal_id}/members", json={"email": "x@example.com"}).status_code == 403
    assert invitee.delete(f"/api/deals/{deal_id}").status_code == 403
    assert stranger.get(f"/api/deals/{deal_id}").status_code == 404

    # the owner removes the viewer and invites the same address back as an editor
    member_id = owner.get(f"/api/deals/{deal_id}/members").json()["members"][0]["id"]
    assert owner.delete(f"/api/deals/{deal_id}/members/{member_id}").status_code == 204
    assert invitee.get(f"/api/deals/{deal_id}").status_code == 404
    r = owner.post(f"/api/deals/{deal_id}/members", json={"email": invitee_email, "role": "editor"})
    assert r.status_code == 201 and r.json()["role"] == "editor"
    r = invitee.post("/api/invites/accept", json={"token": _token_from(invitee_email, "/invite")})
    assert r.status_code == 200
    r = _upload(invitee, deal_id)
    assert r.status_code == 201, r.text
    doc_id = r.json()[0]["id"]
    assert invitee.post(f"/api/deals/{deal_id}/claims/{claim_id}/review", json={"action": "accept"}).status_code == 200
    assert invitee.post(f"/api/deals/{deal_id}/scenarios/{scenario_id}/run").status_code == 201
    assert invitee.delete(f"/api/deals/{deal_id}/documents/{doc_id}").status_code == 204
    # editors still cannot do the owner-only things
    assert invitee.get(f"/api/deals/{deal_id}/review-dataset").status_code == 403
    assert invitee.post(f"/api/deals/{deal_id}/members", json={"email": "x@example.com"}).status_code == 403
    assert invitee.delete(f"/api/deals/{deal_id}").status_code == 403
    # member actions are audited under the member's id
    invitee_id = uuid.UUID(invitee.get("/api/auth/me").json()["id"])
    events = db.scalars(
        select(AuditEvent.event_type).where(AuditEvent.deal_id == uuid.UUID(deal_id), AuditEvent.user_id == invitee_id)
    ).all()
    assert {"deal.member_accepted", "document.uploaded", "document.deleted"} <= set(events)
    shared["invitee"] = invitee
    shared["invitee_email"] = invitee_email


def test_member_can_remove_themselves(shared):
    owner, deal_id, invitee = shared["owner"], shared["deal_id"], shared["invitee"]
    listing = invitee.get(f"/api/deals/{deal_id}/members").json()
    assert listing["role"] == "editor"
    me = next(m for m in listing["members"] if m["email"] == shared["invitee_email"])
    other = owner.post(f"/api/deals/{deal_id}/members", json={"email": "third@example.com", "role": "viewer"}).json()
    assert invitee.delete(f"/api/deals/{deal_id}/members/{other['id']}").status_code == 403
    assert invitee.delete(f"/api/deals/{deal_id}/members/{me['id']}").status_code == 204
    assert invitee.get(f"/api/deals/{deal_id}").status_code == 404
    assert invitee.get(f"/api/deals/{deal_id}/members").status_code == 404
    assert owner.delete(f"/api/deals/{deal_id}/members/{other['id']}").status_code == 204
    assert owner.delete(f"/api/deals/{deal_id}/members/{other['id']}").status_code == 404


def test_invite_limits(shared, db):
    owner, deal_id = shared["owner"], shared["deal_id"]
    assert owner.post(f"/api/deals/{deal_id}/members", json={"email": "share-owner@example.com"}).status_code == 400
    assert owner.post(f"/api/deals/{deal_id}/members", json={"email": "not-an-email"}).status_code == 422
    for i in range(5):
        r = owner.post(f"/api/deals/{deal_id}/members", json={"email": f"seat{i}@example.com", "role": "viewer"})
        assert r.status_code == 201, r.text
    assert owner.post(f"/api/deals/{deal_id}/members", json={"email": "seat0@example.com"}).status_code == 409
    r = owner.post(f"/api/deals/{deal_id}/members", json={"email": "seat5@example.com"})
    assert r.status_code == 400 and "at most 5" in r.json()["detail"]
    assert db.scalar(select(func.count(DealMember.id)).where(DealMember.deal_id == uuid.UUID(deal_id))) == 5
    for m in owner.get(f"/api/deals/{deal_id}/members").json()["members"]:
        assert owner.delete(f"/api/deals/{deal_id}/members/{m['id']}").status_code == 204


def test_owner_can_delete_the_deal_and_members_lose_it(db):
    owner = _register("deleter@example.com", "Deleter")
    _verify(owner, "deleter@example.com")
    deal_id = _seed_deal(owner)
    owner.post(f"/api/deals/{deal_id}/members", json={"email": "deleted-member@example.com", "role": "editor"})
    member = _register("deleted-member@example.com")
    assert (
        member.post("/api/invites/accept", json={"token": _token_from("deleted-member@example.com", "/invite")}).status_code
        == 200
    )
    assert member.get(f"/api/deals/{deal_id}").status_code == 200
    assert owner.delete(f"/api/deals/{deal_id}").status_code == 204
    assert owner.get(f"/api/deals/{deal_id}").status_code == 404
    assert member.get(f"/api/deals/{deal_id}").status_code == 404
    assert db.scalar(select(func.count(DealMember.id)).where(DealMember.deal_id == uuid.UUID(deal_id))) == 0


# ---- chat budget ------------------------------------------------------------------------------------------


def test_chat_budget_returns_429_at_the_limit(monkeypatch, db):
    settings = Settings(_env_file=None, chat_monthly_request_limit=2)
    monkeypatch.setattr(chat_route, "get_settings", lambda: settings)
    c = _register("budget@example.com", "Budget")
    deal_id = _seed_deal(c)
    other_deal = _seed_deal(c)
    cfg = c.get(f"/api/deals/{deal_id}/chat/config").json()
    assert cfg["budget"] == {"limit": 2, "used": 0, "resets_on": chat_route.month_window()[1].isoformat()}
    assert c.post(f"/api/deals/{deal_id}/chat", json={"message": "Which documents are missing?"}).status_code == 200
    assert c.post(f"/api/deals/{other_deal}/chat", json={"message": "What are the biggest risks?"}).status_code == 200
    cfg = c.get(f"/api/deals/{deal_id}/chat/config").json()
    assert cfg["budget"]["used"] == 2 and cfg["budget"]["limit"] == 2  # counted across deals
    r = c.post(f"/api/deals/{deal_id}/chat", json={"message": "One more?"})
    assert r.status_code == 429
    resets = chat_route.month_window()[1]
    assert (
        r.json()["detail"]
        == f"You have used this month's 2 assistant answers. The budget resets on {resets:%B} {resets.day}, {resets.year}."
    )
    user_id = uuid.UUID(c.get("/api/auth/me").json()["id"])
    assert (
        db.scalar(
            select(func.count(ChatMessage.id))
            .join(ChatThread, ChatThread.id == ChatMessage.thread_id)
            .where(ChatThread.user_id == user_id, ChatMessage.role == "assistant")
        )
        == 2
    )
    # a bigger limit, same month: the count carries and reads are never blocked
    monkeypatch.setattr(chat_route, "get_settings", lambda: Settings(_env_file=None, chat_monthly_request_limit=3))
    assert c.get(f"/api/deals/{deal_id}/chat/threads").status_code == 200
    assert c.post(f"/api/deals/{deal_id}/chat", json={"message": "Now?"}).status_code == 200


def test_month_window_rolls_over_in_december():
    from datetime import UTC, datetime

    start, resets = chat_route.month_window(datetime(2026, 12, 15, tzinfo=UTC))
    assert start == datetime(2026, 12, 1, tzinfo=UTC) and resets.isoformat() == "2027-01-01"


# ---- billing ----------------------------------------------------------------------------------------------


class FakeGateway:
    def __init__(self) -> None:
        self.sessions: list[dict[str, Any]] = []

    def create_checkout_session(self, **kwargs: Any) -> CheckoutSession:
        self.sessions.append(kwargs)
        sid = f"cs_test_{len(self.sessions)}"
        return CheckoutSession(id=sid, url=f"https://checkout.stripe.test/{sid}")

    def construct_event(self, payload: bytes, signature: str, secret: str) -> dict[str, Any]:
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise SignatureError("bad signature")
        return json.loads(payload)


def _signed(secret: str, event: dict[str, Any]) -> tuple[bytes, dict[str, str]]:
    payload = json.dumps(event).encode()
    return payload, {"stripe-signature": hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()}


def test_billing_is_503_when_not_configured(client, demo):
    status = client.get("/api/billing/status").json()
    assert status["configured"] is False and status["purchases"] == []
    assert status["pilot"] == {"amount_cents": 50000, "currency": "usd", "description": billing_route.PILOT_DESCRIPTION}
    r = client.post("/api/billing/checkout", json={})
    assert r.status_code == 503 and "not set up" in r.json()["detail"]
    assert client.post("/api/billing/webhook", content=b"{}").status_code == 503


def test_checkout_and_webhook_with_a_fake_gateway(monkeypatch, db):
    settings = Settings(_env_file=None, stripe_secret_key="sk_test_fake", stripe_webhook_secret="whsec_fake")
    gateway = FakeGateway()
    monkeypatch.setattr(billing_route, "get_settings", lambda: settings)
    monkeypatch.setattr(billing_route, "get_gateway", lambda s=None: gateway)
    c = _register("buyer-pilot@example.com", "Pilot Buyer")
    deal_id = _seed_deal(c)
    assert c.get("/api/billing/status").json()["configured"] is True

    assert c.post("/api/billing/checkout", json={"deal_id": str(uuid.uuid4())}).status_code == 404
    r = c.post("/api/billing/checkout", json={"deal_id": deal_id})
    assert r.status_code == 200, r.text
    assert r.json()["url"] == "https://checkout.stripe.test/cs_test_1"
    call = gateway.sessions[0]
    assert call["amount_cents"] == 50000 and call["currency"] == "usd" and call["customer_email"] == "buyer-pilot@example.com"
    assert call["success_url"] == "http://localhost:3000/pilot?status=success&session_id={CHECKOUT_SESSION_ID}"
    assert call["cancel_url"] == "http://localhost:3000/pilot?status=cancelled"
    purchase = db.scalar(select(Purchase).where(Purchase.stripe_session_id == "cs_test_1"))
    assert purchase is not None and purchase.status.value == "pending" and str(purchase.deal_id) == deal_id
    assert call["reference"] == str(purchase.id)
    status = c.get("/api/billing/status").json()
    assert [p["status"] for p in status["purchases"]] == ["pending"] and status["has_paid_pilot"] is False

    anon = TestClient(app)
    event = {"type": "checkout.session.completed", "data": {"object": {"id": "cs_test_1", "payment_intent": "pi_1"}}}
    payload, headers = _signed("whsec_fake", event)
    assert anon.post("/api/billing/webhook", content=payload, headers={"stripe-signature": "nope"}).status_code == 400
    assert anon.post("/api/billing/webhook", content=payload).status_code == 400
    r = anon.post("/api/billing/webhook", content=payload, headers=headers)
    assert r.status_code == 200 and r.json() == {"received": True, "handled": True, "updated": True}
    r = anon.post("/api/billing/webhook", content=payload, headers=headers)  # idempotent
    assert r.status_code == 200 and r.json()["updated"] is False
    db.expire_all()
    purchase = db.scalar(select(Purchase).where(Purchase.stripe_session_id == "cs_test_1"))
    assert (
        purchase is not None and purchase.status.value == "paid" and purchase.paid_at and purchase.stripe_payment_intent == "pi_1"
    )
    status = c.get("/api/billing/status").json()
    assert status["purchases"][0]["status"] == "paid" and status["has_paid_pilot"] is True
    # unrelated events and unknown sessions are acknowledged, not applied
    payload, headers = _signed("whsec_fake", {"type": "invoice.paid", "data": {"object": {"id": "in_1"}}})
    assert anon.post("/api/billing/webhook", content=payload, headers=headers).json()["handled"] is False
    payload, headers = _signed("whsec_fake", {"type": "checkout.session.completed", "data": {"object": {"id": "cs_unknown"}}})
    assert anon.post("/api/billing/webhook", content=payload, headers=headers).json()["handled"] is False
    # demo visitors are asked to create an account first
    visitor = TestClient(app)
    visitor.post("/api/demo/session")
    assert visitor.post("/api/billing/checkout", json={}).status_code == 403


def test_checkout_provider_failure_leaves_no_purchase(monkeypatch, db):
    settings = Settings(_env_file=None, stripe_secret_key="sk_test_fake", stripe_webhook_secret="whsec_fake")

    class Broken(FakeGateway):
        def create_checkout_session(self, **kwargs: Any) -> CheckoutSession:
            raise RuntimeError("stripe down")

    monkeypatch.setattr(billing_route, "get_settings", lambda: settings)
    monkeypatch.setattr(billing_route, "get_gateway", lambda s=None: Broken())
    c = _register("buyer-broken@example.com")
    user_id = uuid.UUID(c.get("/api/auth/me").json()["id"])
    assert c.post("/api/billing/checkout", json={}).status_code == 502
    assert db.scalar(select(func.count(Purchase.id)).where(Purchase.user_id == user_id)) == 0
