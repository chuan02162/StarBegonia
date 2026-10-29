from __future__ import annotations

from datetime import datetime

from app.extensions import db


class Household(db.Model):
    __tablename__ = "households"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    owner_person_id = db.Column(db.Integer, db.ForeignKey("people.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    owner = db.relationship("Person", foreign_keys=[owner_person_id])
    memberships = db.relationship(
        "HouseholdMembership",
        back_populates="household",
        cascade="all, delete-orphan",
    )

    def to_dict(self, *, include_members: bool = False) -> dict:
        data = {
            "id": self.id,
            "name": self.name,
            "owner_person_id": self.owner_person_id,
            "created_at": self.created_at.isoformat() + "Z",
        }
        if include_members:
            active = [m for m in self.memberships if m.left_at is None]
            data["members"] = [m.to_dict() for m in active]
        return data


class HouseholdMembership(db.Model):
    __tablename__ = "household_memberships"

    id = db.Column(db.Integer, primary_key=True)
    household_id = db.Column(
        db.Integer, db.ForeignKey("households.id"), nullable=False, index=True
    )
    person_id = db.Column(
        db.Integer, db.ForeignKey("people.id"), nullable=False, index=True
    )
    role = db.Column(db.String(32), nullable=False, default="member")  # owner|member
    joined_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    left_at = db.Column(db.DateTime, nullable=True)

    household = db.relationship("Household", back_populates="memberships")
    person = db.relationship("Person")

    @property
    def is_active(self) -> bool:
        return self.left_at is None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "household_id": self.household_id,
            "person_id": self.person_id,
            "display_name": self.person.display_name if self.person else None,
            "email": self.person.user.email if self.person and self.person.user else None,
            "role": self.role,
            "joined_at": self.joined_at.isoformat() + "Z",
            "left_at": self.left_at.isoformat() + "Z" if self.left_at else None,
            "active": self.is_active,
        }
