from __future__ import annotations

from datetime import datetime

from app.extensions import db


class SourceCredential(db.Model):
    __tablename__ = "source_credentials"
    __table_args__ = (
        db.UniqueConstraint("person_id", "source_type", name="uq_person_source"),
    )

    id = db.Column(db.Integer, primary_key=True)
    person_id = db.Column(db.Integer, db.ForeignKey("people.id"), nullable=False)
    source_type = db.Column(db.String(64), nullable=False)
    payload_encrypted = db.Column(db.Text, nullable=False)
    label = db.Column(db.String(120), nullable=True)
    last_validated_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    person = db.relationship("Person", back_populates="credentials")

    def to_public_dict(self) -> dict:
        return {
            "id": self.id,
            "person_id": self.person_id,
            "source_type": self.source_type,
            "label": self.label,
            "configured": True,
            "last_validated_at": (
                self.last_validated_at.isoformat() + "Z" if self.last_validated_at else None
            ),
            "updated_at": self.updated_at.isoformat() + "Z",
        }
