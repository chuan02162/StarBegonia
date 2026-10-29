from flask import Blueprint

from app.api import (
    aa_rules,
    analytics,
    auth,
    bills,
    categories,
    dedup,
    entries,
    households,
    people,
    settlements,
    sources,
)


def register_blueprints(app) -> None:
    api = Blueprint("api", __name__, url_prefix="/api/v1")
    api.register_blueprint(auth.bp, url_prefix="/auth")
    api.register_blueprint(people.bp, url_prefix="/people")
    api.register_blueprint(bills.bp, url_prefix="/bills")
    api.register_blueprint(entries.bp, url_prefix="/entries")
    api.register_blueprint(categories.bp, url_prefix="/categories")
    api.register_blueprint(sources.bp, url_prefix="/sources")
    api.register_blueprint(analytics.bp, url_prefix="/analytics")
    api.register_blueprint(households.bp, url_prefix="/households")
    api.register_blueprint(aa_rules.bp, url_prefix="/aa-rules")
    api.register_blueprint(settlements.bp, url_prefix="/settlements")
    api.register_blueprint(dedup.bp, url_prefix="/dedup")
    app.register_blueprint(api)
