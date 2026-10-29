from __future__ import annotations

from app.models import Invite, User
from app.security.passwords import verify_password
from app.services import households as household_service


class AuthError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def bootstrap_household(
    email: str, password: str, display_name: str, household_name: str | None = None
) -> User:
    try:
        return household_service.bootstrap_with_household(
            email, password, display_name, household_name
        )
    except household_service.HouseholdError as exc:
        raise AuthError(exc.message, exc.status_code) from exc


def login(email: str, password: str) -> User:
    user = User.query.filter_by(email=email.strip().lower()).first()
    if not user or not verify_password(password, user.password_hash):
        raise AuthError("invalid email or password", 401)
    return user


def create_invite(*, created_by_person_id: int, display_name_hint: str | None = None) -> Invite:
    try:
        return household_service.create_invite_code(
            person_id=created_by_person_id,
            display_name_hint=display_name_hint,
        )
    except household_service.HouseholdError as exc:
        raise AuthError(exc.message, exc.status_code) from exc


def list_invites(person_id: int) -> list[Invite]:
    return household_service.list_household_invites(person_id)


def register_with_invite(
    *,
    code: str,
    email: str,
    password: str,
    display_name: str,
) -> User:
    try:
        return household_service.register_with_invite(
            code=code,
            email=email,
            password=password,
            display_name=display_name,
        )
    except household_service.HouseholdError as exc:
        raise AuthError(exc.message, exc.status_code) from exc


def needs_bootstrap() -> bool:
    return User.query.count() == 0
