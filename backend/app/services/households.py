from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_

from app.extensions import db
from app.models import (
    Bill,
    DedupLink,
    Household,
    HouseholdMembership,
    InternalTransferLink,
    Invite,
    Person,
    User,
)


class HouseholdError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def active_membership(person_id: int) -> HouseholdMembership | None:
    return HouseholdMembership.query.filter_by(
        person_id=person_id, left_at=None
    ).first()


def require_active_household(person_id: int) -> Household:
    m = active_membership(person_id)
    if not m:
        raise HouseholdError("你还不在任何家庭中，请先创建或加入", 400)
    return m.household


def get_household_for_person(person_id: int) -> dict[str, Any] | None:
    m = active_membership(person_id)
    if not m:
        return None
    hh = m.household
    data = hh.to_dict(include_members=True)
    data["my_role"] = m.role
    data["my_membership_id"] = m.id
    return data


def update_household(
    *, person_id: int, name: str | None = None, jev_context: Any = ...
) -> Household:
    """Active member can edit shared Jev context; owner can rename."""
    m = active_membership(person_id)
    if not m:
        raise HouseholdError("当前不在家庭中", 400)
    hh = m.household
    if name is not None:
        if m.role != "owner" and hh.owner_person_id != person_id:
            raise HouseholdError("只有创建者可以改家庭名称", 403)
        name = name.strip()
        if not name:
            raise HouseholdError("家庭名称不能为空")
        hh.name = name
    if jev_context is not ...:
        text = (jev_context or "").strip() if jev_context is not None else ""
        if len(text) > 4000:
            raise HouseholdError("Jev 提示词最长 4000 字")
        hh.jev_context = text or None
    db.session.commit()
    return hh


def create_household(*, person_id: int, name: str) -> Household:
    if active_membership(person_id):
        raise HouseholdError("已在家庭中，请先退出再创建新家庭", 409)
    name = (name or "").strip()
    if not name:
        raise HouseholdError("家庭名称不能为空")
    person = db.session.get(Person, person_id)
    if not person:
        raise HouseholdError("person not found", 404)

    hh = Household(name=name, owner_person_id=person_id)
    db.session.add(hh)
    db.session.flush()
    db.session.add(
        HouseholdMembership(
            household_id=hh.id,
            person_id=person_id,
            role="owner",
            joined_at=datetime.utcnow(),
        )
    )
    db.session.commit()
    return hh


def leave_household(*, person_id: int) -> None:
    m = active_membership(person_id)
    if not m:
        raise HouseholdError("当前不在家庭中", 400)
    hh = m.household
    was_owner = m.role == "owner" or hh.owner_person_id == person_id
    now = datetime.utcnow()
    m.left_at = now
    if was_owner:
        m.role = "member"
    db.session.flush()

    if was_owner:
        remaining = (
            HouseholdMembership.query.filter(
                HouseholdMembership.household_id == hh.id,
                HouseholdMembership.left_at.is_(None),
            )
            .order_by(HouseholdMembership.joined_at.asc())
            .first()
        )
        if remaining:
            remaining.role = "owner"
            hh.owner_person_id = remaining.person_id

    db.session.commit()


def _join_household(person_id: int, household_id: int, *, role: str = "member") -> HouseholdMembership:
    if active_membership(person_id):
        leave_household(person_id=person_id)
    hh = db.session.get(Household, household_id)
    if not hh:
        raise HouseholdError("家庭不存在", 404)
    m = HouseholdMembership(
        household_id=household_id,
        person_id=person_id,
        role=role,
        joined_at=datetime.utcnow(),
    )
    db.session.add(m)
    db.session.commit()
    return m


def create_invite_code(
    *,
    person_id: int,
    display_name_hint: str | None = None,
) -> Invite:
    m = active_membership(person_id)
    if not m:
        raise HouseholdError("请先创建或加入家庭", 400)
    if m.role != "owner":
        raise HouseholdError("只有家庭创建者可以邀请", 403)

    invite = Invite(
        code=secrets.token_urlsafe(16),
        household_id=m.household_id,
        created_by_person_id=person_id,
        display_name_hint=display_name_hint,
        status="pending",
        expires_at=datetime.utcnow() + timedelta(days=14),
    )
    db.session.add(invite)
    db.session.commit()
    return invite


def invite_by_email(*, person_id: int, email: str) -> Invite:
    m = active_membership(person_id)
    if not m:
        raise HouseholdError("请先创建或加入家庭", 400)
    if m.role != "owner":
        raise HouseholdError("只有家庭创建者可以邀请", 403)

    email = (email or "").strip().lower()
    if not email or "@" not in email:
        raise HouseholdError("邮箱无效")

    owner = db.session.get(Person, person_id)
    if owner and owner.user and owner.user.email == email:
        raise HouseholdError("不能邀请自己")

    existing_user = User.query.filter_by(email=email).first()
    if existing_user and existing_user.person:
        their = active_membership(existing_user.person.id)
        if their and their.household_id == m.household_id:
            raise HouseholdError("对方已在本家庭中", 409)

    pending = Invite.query.filter_by(
        household_id=m.household_id,
        target_email=email,
        status="pending",
    ).first()
    if pending:
        return pending

    invite = Invite(
        code=secrets.token_urlsafe(16),
        household_id=m.household_id,
        created_by_person_id=person_id,
        target_email=email,
        status="pending",
        expires_at=datetime.utcnow() + timedelta(days=14),
    )
    db.session.add(invite)
    db.session.commit()
    return invite


def list_household_invites(person_id: int) -> list[Invite]:
    m = active_membership(person_id)
    if not m or m.role != "owner":
        return []
    return (
        Invite.query.filter_by(household_id=m.household_id)
        .order_by(Invite.created_at.desc())
        .all()
    )


def list_pending_email_invites_for_user(user: User) -> list[Invite]:
    email = user.email.strip().lower()
    return (
        Invite.query.filter_by(target_email=email, status="pending")
        .order_by(Invite.created_at.desc())
        .all()
    )


def accept_invite(*, person_id: int, code: str | None = None, invite_id: int | None = None) -> Household:
    invite = None
    if invite_id is not None:
        invite = db.session.get(Invite, invite_id)
    elif code:
        invite = Invite.query.filter_by(code=code.strip()).first()
    if not invite:
        raise HouseholdError("邀请不存在", 404)
    if invite.status != "pending":
        raise HouseholdError("邀请已失效", 409)
    if invite.expires_at and invite.expires_at < datetime.utcnow():
        invite.status = "cancelled"
        db.session.commit()
        raise HouseholdError("邀请已过期", 410)
    if not invite.household_id:
        raise HouseholdError("邀请未绑定家庭", 400)

    person = db.session.get(Person, person_id)
    if not person or not person.user:
        raise HouseholdError("person not found", 404)

    if invite.target_email and invite.target_email.lower() != person.user.email.lower():
        raise HouseholdError("此邀请发给其他邮箱", 403)

    _join_household(person_id, invite.household_id, role="member")
    invite.status = "accepted"
    invite.used_at = datetime.utcnow()
    invite.used_by_user_id = person.user_id
    db.session.commit()
    return db.session.get(Household, invite.household_id)


def decline_invite(*, person_id: int, invite_id: int) -> None:
    invite = db.session.get(Invite, invite_id)
    if not invite or invite.status != "pending":
        raise HouseholdError("邀请不存在或已处理", 404)
    person = db.session.get(Person, person_id)
    if not person or not person.user:
        raise HouseholdError("person not found", 404)
    if invite.target_email and invite.target_email.lower() != person.user.email.lower():
        raise HouseholdError("此邀请发给其他邮箱", 403)
    invite.status = "declined"
    db.session.commit()


def register_with_invite(
    *,
    code: str,
    email: str,
    password: str,
    display_name: str,
) -> User:
    from app.security.passwords import hash_password

    invite = Invite.query.filter_by(code=code).first()
    if not invite:
        raise HouseholdError("invite not found", 404)
    if invite.is_used or invite.status not in ("pending",):
        raise HouseholdError("invite already used", 409)
    if invite.expires_at and invite.expires_at < datetime.utcnow():
        raise HouseholdError("invite expired", 410)
    if not invite.household_id:
        raise HouseholdError("invite has no household", 400)
    if invite.target_email and invite.target_email.lower() != email.strip().lower():
        raise HouseholdError("请使用邀请邮箱注册", 403)
    if User.query.filter_by(email=email.strip().lower()).first():
        raise HouseholdError("email already registered", 409)

    user = User(email=email.strip().lower(), password_hash=hash_password(password))
    db.session.add(user)
    db.session.flush()
    person = Person(user_id=user.id, display_name=display_name.strip())
    db.session.add(person)
    db.session.flush()

    db.session.add(
        HouseholdMembership(
            household_id=invite.household_id,
            person_id=person.id,
            role="member",
            joined_at=datetime.utcnow(),
        )
    )
    invite.status = "used"
    invite.used_at = datetime.utcnow()
    invite.used_by_user_id = user.id
    db.session.commit()
    return user


def bootstrap_with_household(
    email: str, password: str, display_name: str, household_name: str | None = None
) -> User:
    from app.security.passwords import hash_password

    if User.query.count() > 0:
        raise HouseholdError("household already initialized", 409)
    if not email or not password or not display_name:
        raise HouseholdError("email, password and display_name are required")

    user = User(email=email.strip().lower(), password_hash=hash_password(password))
    db.session.add(user)
    db.session.flush()
    person = Person(user_id=user.id, display_name=display_name.strip())
    db.session.add(person)
    db.session.flush()

    hh_name = (household_name or "").strip() or f"{display_name.strip()}的家庭"
    hh = Household(name=hh_name, owner_person_id=person.id)
    db.session.add(hh)
    db.session.flush()
    db.session.add(
        HouseholdMembership(
            household_id=hh.id,
            person_id=person.id,
            role="owner",
            joined_at=datetime.utcnow(),
        )
    )
    db.session.commit()
    return user


def visible_bills_query(person_id: int):
    """External household flows visible to person, with internal records suppressed."""
    memberships = HouseholdMembership.query.filter_by(person_id=person_id).all()
    if not memberships:
        return Bill.query.filter(sa_false())

    clauses = []
    for m in memberships:
        if m.left_at is None:
            # Active: all bills in this household
            clauses.append(Bill.household_id == m.household_id)
        else:
            # Former: bills entered shared ledger before leave
            clauses.append(
                and_(
                    Bill.household_id == m.household_id,
                    Bill.created_at >= m.joined_at,
                    Bill.created_at < m.left_at,
                )
            )
    return exclude_non_external_bills(Bill.query.filter(or_(*clauses)))


def exclude_non_external_bills(query):
    """Hide dedup secondary and linked household transfer bills from normal views."""
    dedup_secondary = db.session.query(DedupLink.id).filter(
        DedupLink.status == "linked",
        DedupLink.secondary_bill_id == Bill.id,
    ).exists()
    internal_transfer = db.session.query(InternalTransferLink.id).filter(
        InternalTransferLink.status == "linked",
        or_(
            InternalTransferLink.outgoing_bill_id == Bill.id,
            InternalTransferLink.incoming_bill_id == Bill.id,
        ),
    ).exists()
    return query.filter(~dedup_secondary, ~internal_transfer)


def sa_false():
    from sqlalchemy import false

    return false()


def bill_visible_to(person_id: int, bill: Bill) -> bool:
    if not bill.household_id:
        return False
    memberships = HouseholdMembership.query.filter_by(
        person_id=person_id, household_id=bill.household_id
    ).all()
    belongs_to_member = False
    for m in memberships:
        if m.left_at is None:
            belongs_to_member = True
            break
        if m.joined_at <= bill.created_at < m.left_at:
            belongs_to_member = True
            break
    if not belongs_to_member:
        return False
    return (
        exclude_non_external_bills(Bill.query.filter(Bill.id == bill.id)).first()
        is not None
    )
