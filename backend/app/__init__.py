from __future__ import annotations

from datetime import timedelta

from flask import Flask
from flask_cors import CORS

from app.api import register_blueprints
from app.config import Config
from app.extensions import db, jwt


def create_app(config_object: type = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(
        seconds=int(app.config["JWT_ACCESS_TOKEN_EXPIRES"])
    )

    CORS(app, resources={r"/api/*": {"origins": "*"}})
    db.init_app(app)
    jwt.init_app(app)
    register_blueprints(app)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app
