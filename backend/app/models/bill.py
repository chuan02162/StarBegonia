from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON

from app.extensions import db


class Bill(db.Model):
    __tablename__ = "bills"
    __table_args__ = (
        db.UniqueConstraint("source_type", "external_id", name="uq_source_external"),
    )

    id = db.Column(db.Integer, primary_key=True)
    source_type = db.Column(db.String(64), nullable=False, index=True)
    person_id = db.Column(db.Integer, db.ForeignKey("people.id"), nullable=False)
    household_id = db.Column(
        db.Integer, db.ForeignKey("households.id"), nullable=True, index=True
    )
    occurred_at = db.Column(db.DateTime, nullable=False, index=True)
    merchant = db.Column(db.String(255), nullable=True)
    currency = db.Column(db.String(8), nullable=False, default="AUD")
    external_id = db.Column(db.String(255), nullable=True)
    note = db.Column(db.Text, nullable=True)
    # Signed net amount (negative = money out, positive = money in). Stored
    # explicitly so line items can keep their receipt sign (positive items,
    # negative discounts) without losing the bill's direction.
    net_amount = db.Column(db.Numeric(14, 2), nullable=True)
    # unmatched | suggested | linked | ignored
    dedup_status = db.Column(
        db.String(32), nullable=False, default="unmatched", index=True
    )
    # When this bill is the secondary of a linked pair, points at the primary.
    dedup_primary_id = db.Column(
        db.Integer, db.ForeignKey("bills.id"), nullable=True, index=True
    )
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    person = db.relationship("Person")
    household = db.relationship("Household")
    entries = db.relationship(
        "Entry",
        back_populates="bill",
        cascade="all, delete-orphan",
        order_by="Entry.id",
    )

    @property
    def total_amount(self) -> Decimal:
        if self.net_amount is not None:
            return Decimal(self.net_amount)
        return sum((e.amount for e in self.entries), Decimal("0"))

    def to_dict(self, *, include_entries: bool = True) -> dict:
        data = {
            "id": self.id,
            "source_type": self.source_type,
            "person_id": self.person_id,
            "household_id": self.household_id,
            "occurred_at": self.occurred_at.isoformat() + "Z",
            "merchant": self.merchant,
            "currency": self.currency,
            "external_id": self.external_id,
            "note": self.note,
            "dedup_status": self.dedup_status,
            "dedup_primary_id": self.dedup_primary_id,
            "total_amount": str(self.total_amount),
            "created_at": self.created_at.isoformat() + "Z",
            "updated_at": self.updated_at.isoformat() + "Z",
        }
        if include_entries:
            data["entries"] = [e.to_dict() for e in self.entries]
        return data


class Entry(db.Model):
    __tablename__ = "entries"

    id = db.Column(db.Integer, primary_key=True)
    bill_id = db.Column(db.Integer, db.ForeignKey("bills.id"), nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Numeric(12, 4), nullable=False, default=Decimal("1"))
    unit_price = db.Column(db.Numeric(12, 4), nullable=True)
    discount = db.Column(db.Numeric(12, 4), nullable=False, default=Decimal("0"))
    amount = db.Column(db.Numeric(12, 4), nullable=False)
    currency = db.Column(db.String(8), nullable=False, default="AUD")
    category_id = db.Column(db.String(64), nullable=True, index=True)
    tags = db.Column(JSON, nullable=False, default=list)
    note = db.Column(db.Text, nullable=True)
    image_url = db.Column(db.String(1024), nullable=True)
    classification_status = db.Column(
        db.String(32), nullable=False, default="unclassified", index=True
    )
    category_confidence = db.Column(db.Numeric(6, 4), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    bill = db.relationship("Bill", back_populates="entries")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "bill_id": self.bill_id,
            "name": self.name,
            "quantity": str(self.quantity),
            "unit_price": str(self.unit_price) if self.unit_price is not None else None,
            "discount": str(self.discount),
            "amount": str(self.amount),
            "currency": self.currency,
            "category_id": self.category_id,
            "tags": self.tags or [],
            "note": self.note,
            "image_url": self.image_url,
            "classification_status": self.classification_status,
            "category_confidence": (
                str(self.category_confidence)
                if self.category_confidence is not None
                else None
            ),
        }
