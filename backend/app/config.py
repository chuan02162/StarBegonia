from __future__ import annotations

import os
from pathlib import Path


def _repo_root() -> Path:
    # backend/app/config.py -> repo root
    return Path(__file__).resolve().parents[2]


class Config:
    ENV_NAME = os.environ.get("STARBEGONIA_ENV", os.environ.get("FLASK_ENV", "development"))

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", SECRET_KEY)
    JWT_ACCESS_TOKEN_EXPIRES = int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRES", 60 * 60 * 24 * 7))

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg2://starbegonia:starbegonia@localhost:5432/starbegonia",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    CREDENTIAL_FERNET_KEY = os.environ.get("CREDENTIAL_FERNET_KEY", "")

    # Comma-separated; use * only for local. Production should be your public origin.
    CORS_ORIGINS = [
        o.strip()
        for o in os.environ.get("CORS_ORIGINS", "*").split(",")
        if o.strip()
    ]

    CATEGORIES_PATH = os.environ.get(
        "CATEGORIES_PATH",
        str(_repo_root() / "config" / "categories.yaml"),
    )
    DEFAULT_CURRENCY = os.environ.get("DEFAULT_CURRENCY", "AUD")

    JEV_API_KEY = os.environ.get("JEV_API_KEY", "")
    JEV_API_URL = os.environ.get(
        "JEV_API_URL", "https://api.typesafe.ai/v1/systemone"
    )
    JEV_MODEL = os.environ.get("JEV_MODEL", "jev-latest")
    JEV_CONCURRENCY = int(os.environ.get("JEV_CONCURRENCY", "8"))
    # Below this confidence → classification_status = pending
    JEV_CONFIDENCE_THRESHOLD = float(os.environ.get("JEV_CONFIDENCE_THRESHOLD", "0.7"))
    SOURCE_SYNC_CONCURRENCY = int(os.environ.get("SOURCE_SYNC_CONCURRENCY", "4"))

    # Public site origin (OAuth redirect + jwksUri base), e.g. http://1cchome1.duckdns.org:5173
    APP_PUBLIC_URL = os.environ.get("APP_PUBLIC_URL", "").rstrip("/")

    # OpenFeed (CDR Sharing API) — replaces BankSync
    OPENFEED_ISSUER = os.environ.get("OPENFEED_ISSUER", "https://auth.openfeed.au").rstrip(
        "/"
    )
    OPENFEED_CLIENT_ID = os.environ.get("OPENFEED_CLIENT_ID", "")  # oauth2ClientId (app-…)
    OPENFEED_APP_ID = os.environ.get("OPENFEED_APP_ID", "")  # bare UUID for consent deep-link
    OPENFEED_APP_PRIVATE_KEY = os.environ.get("OPENFEED_APP_PRIVATE_KEY", "")
    OPENFEED_DPOP_PRIVATE_KEY = os.environ.get("OPENFEED_DPOP_PRIVATE_KEY", "")
    OPENFEED_APP_KID = os.environ.get("OPENFEED_APP_KID", "")
    OPENFEED_DPOP_KID = os.environ.get("OPENFEED_DPOP_KID", "")

    # Nightly sync (worker process). Sydney wall clock by default.
    DAILY_SYNC_ENABLED = os.environ.get("DAILY_SYNC_ENABLED", "1") == "1"
    DAILY_SYNC_TZ = os.environ.get("DAILY_SYNC_TZ", "Australia/Sydney")
    DAILY_SYNC_HOUR = int(os.environ.get("DAILY_SYNC_HOUR", "0"))
    DAILY_SYNC_MINUTE = int(os.environ.get("DAILY_SYNC_MINUTE", "0"))
    DAILY_SYNC_GAP_SECONDS = float(os.environ.get("DAILY_SYNC_GAP_SECONDS", "45"))


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True
