from __future__ import annotations

from datetime import datetime

from app.extensions import db


class Person(db.Model):
    __tablename__ = "people"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    display_name = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship("User", back_populates="person")
    credentials = db.relationship(
        "SourceCredential",
        back_populates="person",
        cascade="all, delete-orphan",
    )

    def to_dict(self, *, include_credentials: bool = False) -> dict:
        data = {
            "id": self.id,
            "user_id": self.user_id,
            "display_name": self.display_name,
            "created_at": self.created_at.isoformat() + "Z",
        }
        if include_credentials:
            data["credentials"] = [c.to_public_dict() for c in self.credentials]
        return data
