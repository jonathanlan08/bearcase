"""Deal sharing: an owner invites collaborators by email; an invitee accepts with a signed-in account whose
address matches. Owners manage members; a member may remove themselves. Every member action is audited under
the acting user's id."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from bearcase.api.deps import DbDep, DealDep, UserDep, deal_role, require_role
from bearcase.api.routes.auth import consume_token, issue_token, link_for
from bearcase.api.schemas import MemberInvite, MemberOut, MembersOut, TokenRequest
from bearcase.audit import record
from bearcase.email import get_emailer
from bearcase.models import Deal, DealMember, User
from bearcase.models.base import utcnow
from bearcase.models.enums import MemberRole, TokenPurpose

router = APIRouter(tags=["members"])
MAX_MEMBERS = 5


def _member_out(m: DealMember) -> MemberOut:
    return MemberOut(
        id=m.id,
        email=m.invited_email,
        role="editor" if m.role == MemberRole.EDITOR else "viewer",
        accepted=m.accepted_at is not None,
        display_name=m.user.display_name if m.user is not None else None,
    )


def _send_invite(db, deal: Deal, owner: User, member: DealMember) -> None:  # type: ignore[no-untyped-def]
    token = issue_token(db, owner, TokenPurpose.INVITE, {"member_id": str(member.id), "deal_id": str(deal.id)})
    link = link_for(TokenPurpose.INVITE, token)
    role = "edit" if member.role == MemberRole.EDITOR else "view"
    text = (
        f"{owner.display_name} ({owner.email}) invited you to {role} the deal {deal.company_name} on BearCase.\n\n"
        f"Open this link within 7 days, signed in with an account for {member.invited_email}, to accept:\n\n{link}\n\n"
        "If you do not know the sender, ignore this message."
    )
    html = (
        f"<p>{owner.display_name} ({owner.email}) invited you to {role} the deal <strong>{deal.company_name}</strong> "
        f"on BearCase.</p><p>Open this link within 7 days, signed in with an account for {member.invited_email}, "
        f'to accept:</p><p><a href="{link}">{link}</a></p><p>If you do not know the sender, ignore this message.</p>'
    )
    get_emailer().send(member.invited_email, f"{owner.display_name} shared {deal.company_name} with you", text, html)


@router.get("/deals/{deal_id}/members", response_model=MembersOut)
def list_members(deal: DealDep, db: DbDep, user: UserDep) -> MembersOut:
    role = deal_role(db, deal, user) or "viewer"
    members = db.scalars(select(DealMember).where(DealMember.deal_id == deal.id).order_by(DealMember.created_at)).all()
    return MembersOut(
        owner={"email": deal.owner.email, "display_name": deal.owner.display_name},
        members=[_member_out(m) for m in members],
        role=role,
        limit=MAX_MEMBERS,
    )


@router.post("/deals/{deal_id}/members", response_model=MemberOut, status_code=201)
def invite_member(deal: DealDep, body: MemberInvite, db: DbDep, user: UserDep) -> MemberOut:
    require_role(deal, user, "owner")
    if user.is_demo or user.email_verified_at is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Verify your email address before sharing a deal.")
    if body.email == user.email.lower():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You already own this deal.")
    if db.scalar(select(DealMember).where(DealMember.deal_id == deal.id, DealMember.invited_email == body.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "That person has already been invited to this deal.")
    count = db.scalar(select(func.count(DealMember.id)).where(DealMember.deal_id == deal.id)) or 0
    if count >= MAX_MEMBERS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"A deal can be shared with at most {MAX_MEMBERS} people.")
    existing = db.scalar(select(User).where(User.email == body.email, User.is_demo.is_(False)))
    member = DealMember(
        deal_id=deal.id,
        user_id=existing.id if existing else None,
        invited_email=body.email,
        role=MemberRole(body.role),
        invited_by=user.id,
    )
    db.add(member)
    db.flush()
    _send_invite(db, deal, user, member)
    record(
        db,
        deal_id=deal.id,
        user_id=user.id,
        event_type="deal.member_invited",
        object_type="deal_member",
        object_id=member.id,
        summary=f"Invited {member.invited_email} as {body.role}",
        payload={"email": member.invited_email, "role": body.role},
    )
    db.commit()
    return _member_out(member)


@router.post("/invites/accept")
def accept_invite(body: TokenRequest, db: DbDep, user: UserDep) -> dict[str, uuid.UUID]:
    """Accept an invitation with the signed-in account. The account's email must match the invited address."""
    if user.is_demo:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Create an account with the invited email address to accept.")
    row = consume_token(db, body.token, TokenPurpose.INVITE)
    member_id = row.payload.get("member_id")
    member = db.get(DealMember, uuid.UUID(member_id)) if member_id else None
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This invitation is no longer valid.")
    if member.invited_email.lower() != user.email.lower():
        db.rollback()  # keep the token usable for the right account
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, f"This invitation was sent to {member.invited_email}; sign in with that account."
        )
    if member.accepted_at is None:
        member.user_id = user.id
        member.accepted_at = utcnow()
        record(
            db,
            deal_id=member.deal_id,
            user_id=user.id,
            event_type="deal.member_accepted",
            object_type="deal_member",
            object_id=member.id,
            summary=f"{user.email} joined as {member.role.value}",
            payload={"role": member.role.value},
        )
    db.commit()
    return {"deal_id": member.deal_id}


@router.delete("/deals/{deal_id}/members/{member_id}", status_code=204)
def remove_member(deal: DealDep, member_id: uuid.UUID, db: DbDep, user: UserDep) -> None:
    member = db.scalar(select(DealMember).where(DealMember.id == member_id, DealMember.deal_id == deal.id))
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found.")
    if deal.owner_id != user.id and member.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the deal owner can remove other members.")
    email = member.invited_email
    db.delete(member)
    record(
        db,
        deal_id=deal.id,
        user_id=user.id,
        event_type="deal.member_removed",
        object_type="deal_member",
        object_id=member_id,
        summary=f"Removed {email} from the deal" if deal.owner_id == user.id else f"{email} left the deal",
        payload={"email": email},
    )
    db.commit()
