from __future__ import annotations

from functools import wraps
from typing import Callable

from flask import jsonify
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from app.extensions import db
from app.models import Person, User


def current_user() -> User | None:
    identity = get_jwt_identity()
    if identity is None:
        return None
    return db.session.get(User, int(identity))


def current_person() -> Person | None:
    user = current_user()
    return user.person if user else None


def login_required(fn: Callable):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        user = current_user()
        if not user or not user.person:
            return jsonify({"error": "unauthorized"}), 401
        return fn(*args, **kwargs)

    return wrapper
