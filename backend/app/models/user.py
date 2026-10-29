from __future__ import annotations

from datetime import datetime

from app.extensions import db


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    person = db.relationship("Person", back_populates="user", uselist=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "person": self.person.to_dict() if self.person else None,
            "created_at": self.created_at.isoformat() + "Z",
        }
