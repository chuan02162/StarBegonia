from __future__ import annotations

from datetime import datetime

from app.extensions import db


class Invite(db.Model):
    """Household invite: register code and/or email pull."""

    __tablename__ = "invites"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True, nullable=False, index=True)
    household_id = db.Column(
        db.Integer, db.ForeignKey("households.id"), nullable=True, index=True
    )
    created_by_person_id = db.Column(db.Integer, db.ForeignKey("people.id"), nullable=False)
    display_name_hint = db.Column(db.String(120), nullable=True)
    target_email = db.Column(db.String(255), nullable=True, index=True)
    status = db.Column(
        db.String(32), nullable=False, default="pending"
    )  # pending|accepted|declined|cancelled|used
    used_at = db.Column(db.DateTime, nullable=True)
    used_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)

    created_by = db.relationship("Person", foreign_keys=[created_by_person_id])
    household = db.relationship("Household")

    @property
    def is_used(self) -> bool:
        return self.status in ("accepted", "used") or self.used_at is not None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "code": self.code,
            "household_id": self.household_id,
            "household_name": self.household.name if self.household else None,
            "display_name_hint": self.display_name_hint,
            "target_email": self.target_email,
            "status": self.status,
            "used": self.is_used,
            "used_at": self.used_at.isoformat() + "Z" if self.used_at else None,
            "created_at": self.created_at.isoformat() + "Z",
            "expires_at": self.expires_at.isoformat() + "Z" if self.expires_at else None,
        }
