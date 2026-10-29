from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON

from app.extensions import db


class AaRule(db.Model):
    __tablename__ = "aa_rules"

    id = db.Column(db.Integer, primary_key=True)
    household_id = db.Column(
        db.Integer, db.ForeignKey("households.id"), nullable=False, index=True
    )
    name = db.Column(db.String(120), nullable=True)
    source_types = db.Column(JSON, nullable=False, default=list)
    # Empty = all categories for the selected sources; else only these category ids.
    category_ids = db.Column(JSON, nullable=False, default=list)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    # { "<person_id>": "<percent string>" }
    shares = db.Column(JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    household = db.relationship("Household")

    def to_dict(self, *, residual_meta: dict | None = None) -> dict:
        shares = {str(k): str(v) for k, v in (self.shares or {}).items()}
        total = sum((Decimal(v) for v in shares.values()), Decimal("0"))
        residual = max(Decimal("0"), Decimal("100") - total)
        data = {
            "id": self.id,
            "household_id": self.household_id,
            "name": self.name,
            "source_types": list(self.source_types or []),
            "category_ids": list(self.category_ids or []),
            "enabled": bool(self.enabled),
            "shares": shares,
            "shares_total": str(total),
            "residual_percent": str(residual),
            "created_at": self.created_at.isoformat() + "Z",
            "updated_at": self.updated_at.isoformat() + "Z",
        }
        if residual_meta:
            data["aa_residual"] = residual_meta
        return data
