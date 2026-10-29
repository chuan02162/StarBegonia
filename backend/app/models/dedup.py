from __future__ import annotations

from datetime import datetime

from app.extensions import db


class DedupLink(db.Model):
    __tablename__ = "dedup_links"
    __table_args__ = (
        db.UniqueConstraint(
            "primary_bill_id",
            "secondary_bill_id",
            name="uq_dedup_primary_secondary",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    household_id = db.Column(
        db.Integer, db.ForeignKey("households.id"), nullable=False, index=True
    )
    primary_bill_id = db.Column(
        db.Integer, db.ForeignKey("bills.id"), nullable=False
    )
    secondary_bill_id = db.Column(
        db.Integer, db.ForeignKey("bills.id"), nullable=False
    )
    # suggested | linked | ignored
    status = db.Column(db.String(32), nullable=False, default="suggested", index=True)
    score = db.Column(db.Numeric(6, 4), nullable=True)
    reason = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)

    household = db.relationship("Household")
    primary_bill = db.relationship("Bill", foreign_keys=[primary_bill_id])
    secondary_bill = db.relationship("Bill", foreign_keys=[secondary_bill_id])

    def to_dict(self, *, include_bills: bool = True) -> dict:
        data = {
            "id": self.id,
            "household_id": self.household_id,
            "primary_bill_id": self.primary_bill_id,
            "secondary_bill_id": self.secondary_bill_id,
            "status": self.status,
            "score": str(self.score) if self.score is not None else None,
            "reason": self.reason,
            "created_at": self.created_at.isoformat() + "Z",
            "resolved_at": (
                self.resolved_at.isoformat() + "Z" if self.resolved_at else None
            ),
        }
        if include_bills:
            data["primary_bill"] = (
                self.primary_bill.to_dict(include_entries=False)
                if self.primary_bill
                else None
            )
            data["secondary_bill"] = (
                self.secondary_bill.to_dict(include_entries=False)
                if self.secondary_bill
                else None
            )
        return data
