from __future__ import annotations

from datetime import datetime

from app.extensions import db


class MerchantEnrichment(db.Model):
    __tablename__ = "merchant_enrichments"

    id = db.Column(db.Integer, primary_key=True)
    lookup_key = db.Column(db.String(255), nullable=False, unique=True, index=True)
    entity_name = db.Column(db.String(255), nullable=True)
    abn = db.Column(db.String(32), nullable=True)
    business_name = db.Column(db.Text, nullable=True)
    matched_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
