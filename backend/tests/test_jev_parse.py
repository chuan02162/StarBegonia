from __future__ import annotations

from app.services.jev import _parse_answers


def test_parse_answers_category():
    result = _parse_answers(
        {
            "model": "jev-1.14.0",
            "answers": {
                "category": {
                    "type": "choice",
                    "choice": "groceries",
                    "confidence": 0.92,
                    "probabilities": {"groceries": 0.92},
                },
            },
        }
    )
    assert result["category_id"] == "groceries"
    assert result["confidence"] == 0.92
