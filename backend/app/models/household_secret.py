from __future__ import annotations

from datetime import datetime

from app.extensions import db


class HouseholdSecret(db.Model):
    __tablename__ = "household_secrets"
    __table_args__ = (
        db.UniqueConstraint("household_id", "key", name="uq_household_secret_key"),
    )

    id = db.Column(db.Integer, primary_key=True)
    household_id = db.Column(
        db.Integer, db.ForeignKey("households.id"), nullable=False, index=True
    )
    key = db.Column(db.String(64), nullable=False)
    value_encrypted = db.Column(db.Text, nullable=False)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
