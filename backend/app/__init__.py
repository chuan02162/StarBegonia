from __future__ import annotations

from datetime import timedelta

from flask import Flask
from flask_cors import CORS

from app.api import register_blueprints
from app.config import Config
from app.extensions import db, jwt

_WEAK_SECRETS = {
    "",
    "dev-secret-change-me",
    "change-me-in-production",
    "change-me-jwt",
}


def _assert_production_secrets(app: Flask) -> None:
    if (app.config.get("ENV_NAME") or "").lower() not in {"production", "prod"}:
        return
    secret = app.config.get("SECRET_KEY") or ""
    jwt_secret = app.config.get("JWT_SECRET_KEY") or ""
    fernet = app.config.get("CREDENTIAL_FERNET_KEY") or ""
    if secret in _WEAK_SECRETS or jwt_secret in _WEAK_SECRETS:
        raise RuntimeError(
            "STARBEGONIA_ENV=production requires strong SECRET_KEY and JWT_SECRET_KEY"
        )
    if not fernet:
        raise RuntimeError(
            "STARBEGONIA_ENV=production requires CREDENTIAL_FERNET_KEY "
            '(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")'
        )
    origins = app.config.get("CORS_ORIGINS") or []
    if origins == ["*"]:
        raise RuntimeError(
            "STARBEGONIA_ENV=production requires CORS_ORIGINS set to your public site origin "
            "(not *)"
        )


def create_app(config_object: type = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(
        seconds=int(app.config["JWT_ACCESS_TOKEN_EXPIRES"])
    )
    _assert_production_secrets(app)

    origins = app.config.get("CORS_ORIGINS") or ["*"]
    CORS(app, resources={r"/api/*": {"origins": origins}})
    db.init_app(app)
    jwt.init_app(app)
    register_blueprints(app)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app
