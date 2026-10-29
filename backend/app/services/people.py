from __future__ import annotations

from typing import Any

from app.extensions import db
from app.models import Person, SourceCredential
from app.security.crypto import encrypt_payload
from app.sources import get_adapter


class PeopleError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def list_people() -> list[Person]:
    return Person.query.order_by(Person.id.asc()).all()


def get_person(person_id: int) -> Person:
    person = db.session.get(Person, person_id)
    if not person:
        raise PeopleError("person not found", 404)
    return person


def update_person(person_id: int, *, display_name: str) -> Person:
    person = get_person(person_id)
    if not display_name.strip():
        raise PeopleError("display_name is required")
    person.display_name = display_name.strip()
    db.session.commit()
    return person


def upsert_credential(
    person_id: int,
    *,
    source_type: str,
    payload: dict[str, Any],
    label: str | None = None,
) -> SourceCredential:
    get_person(person_id)
    try:
        adapter = get_adapter(source_type)
    except KeyError as exc:
        raise PeopleError(str(exc), 400) from exc

    if source_type == "manual":
        raise PeopleError("manual source does not use credentials")

    if not adapter.validate_credential(payload):
        raise PeopleError("credential failed validation")

    cred = SourceCredential.query.filter_by(
        person_id=person_id, source_type=source_type
    ).first()
    if not cred:
        cred = SourceCredential(person_id=person_id, source_type=source_type, payload_encrypted="")
        db.session.add(cred)

    cred.payload_encrypted = encrypt_payload(payload)
    cred.label = label
    db.session.commit()
    return cred


def delete_credential(person_id: int, source_type: str) -> None:
    cred = SourceCredential.query.filter_by(
        person_id=person_id, source_type=source_type
    ).first()
    if not cred:
        raise PeopleError("credential not found", 404)
    db.session.delete(cred)
    db.session.commit()
