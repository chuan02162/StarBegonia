from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON

from app.extensions import db


class ClassificationRule(db.Model):
    """User-defined keyword → category rule (deterministic, pre-Jev)."""

    __tablename__ = "classification_rules"

    id = db.Column(db.Integer, primary_key=True)
    household_id = db.Column(
        db.Integer, db.ForeignKey("households.id"), nullable=False, index=True
    )
    category_id = db.Column(db.String(64), nullable=False, index=True)
    # Substring keywords (case-insensitive, OR semantics).
    keywords = db.Column(JSON, nullable=False, default=list)
    # Which field to match: name (default) or merchant.
    match_field = db.Column(db.String(32), nullable=False, default="name")
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    position = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    household = db.relationship("Household")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "household_id": self.household_id,
            "category_id": self.category_id,
            "keywords": self.keywords or [],
            "match_field": self.match_field,
            "enabled": self.enabled,
            "position": self.position,
            "created_at": self.created_at.isoformat() + "Z",
            "updated_at": self.updated_at.isoformat() + "Z",
        }
