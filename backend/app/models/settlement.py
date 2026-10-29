from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON

from app.extensions import db


class Settlement(db.Model):
    __tablename__ = "settlements"

    id = db.Column(db.Integer, primary_key=True)
    household_id = db.Column(
        db.Integer, db.ForeignKey("households.id"), nullable=False, index=True
    )
    created_by_person_id = db.Column(
        db.Integer, db.ForeignKey("people.id"), nullable=False
    )
    period_start = db.Column(db.DateTime, nullable=False, index=True)
    period_end = db.Column(db.DateTime, nullable=False)
    granularity = db.Column(db.String(32), nullable=True)  # week|month|quarter|year
    currency = db.Column(db.String(8), nullable=False, default="AUD")
    # draft | confirmed | settled
    status = db.Column(db.String(32), nullable=False, default="draft")
    result = db.Column(JSON, nullable=False, default=dict)
    note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    confirmed_at = db.Column(db.DateTime, nullable=True)
    settled_at = db.Column(db.DateTime, nullable=True)

    household = db.relationship("Household")
    created_by = db.relationship("Person", foreign_keys=[created_by_person_id])

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "household_id": self.household_id,
            "created_by_person_id": self.created_by_person_id,
            "period_start": self.period_start.isoformat() + "Z",
            "period_end": self.period_end.isoformat() + "Z",
            "granularity": self.granularity,
            "currency": self.currency,
            "status": self.status,
            "result": self.result or {},
            "note": self.note,
            "created_at": self.created_at.isoformat() + "Z",
            "confirmed_at": (
                self.confirmed_at.isoformat() + "Z" if self.confirmed_at else None
            ),
            "settled_at": (
                self.settled_at.isoformat() + "Z" if self.settled_at else None
            ),
        }
