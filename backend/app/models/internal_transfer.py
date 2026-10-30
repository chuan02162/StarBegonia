from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON

from app.extensions import db


class InternalTransferLink(db.Model):
    __tablename__ = "internal_transfer_links"
    __table_args__ = (
        db.UniqueConstraint(
            "outgoing_bill_id",
            "incoming_bill_id",
            name="uq_internal_transfer_out_in",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    household_id = db.Column(
        db.Integer, db.ForeignKey("households.id"), nullable=False, index=True
    )
    outgoing_bill_id = db.Column(
        db.Integer, db.ForeignKey("bills.id"), nullable=False, index=True
    )
    incoming_bill_id = db.Column(
        db.Integer, db.ForeignKey("bills.id"), nullable=False, index=True
    )
    reference = db.Column(db.String(64), nullable=False, index=True)
    # linked only for now; row deleted on unlink
    status = db.Column(db.String(32), nullable=False, default="linked", index=True)
    # { "<bill_id>": "<category_id or null>" } before forcing transfer
    previous_categories = db.Column(JSON, nullable=False, default=dict)
    matched_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    household = db.relationship("Household")
    outgoing_bill = db.relationship("Bill", foreign_keys=[outgoing_bill_id])
    incoming_bill = db.relationship("Bill", foreign_keys=[incoming_bill_id])

    def to_dict(self, *, include_bills: bool = True) -> dict:
        data = {
            "id": self.id,
            "household_id": self.household_id,
            "outgoing_bill_id": self.outgoing_bill_id,
            "incoming_bill_id": self.incoming_bill_id,
            "reference": self.reference,
            "status": self.status,
            "previous_categories": self.previous_categories or {},
            "matched_at": self.matched_at.isoformat() + "Z",
            "created_at": self.created_at.isoformat() + "Z",
        }
        if include_bills:
            data["outgoing_bill"] = (
                self.outgoing_bill.to_dict(include_entries=False)
                if self.outgoing_bill
                else None
            )
            data["incoming_bill"] = (
                self.incoming_bill.to_dict(include_entries=False)
                if self.incoming_bill
                else None
            )
        return data
