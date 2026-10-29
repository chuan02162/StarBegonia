from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.aa_rules import (
    AaRuleError,
    coverage_keys,
    coverages_conflict,
    default_rule_name,
    normalize_shares,
    normalize_source_types,
    residual_percent,
)


def test_normalize_source_types_sorts_and_dedupes():
    assert normalize_source_types(["commbank", "coles", "coles"]) == [
        "coles",
        "commbank",
    ]


def test_normalize_source_types_rejects_unknown():
    with pytest.raises(AaRuleError, match="unknown source_type"):
        normalize_source_types(["paypal"])


def test_normalize_shares_sum_over_100():
    with pytest.raises(AaRuleError, match="不能超过 100"):
        normalize_shares({"1": "60", "2": "50"}, member_ids={1, 2})


def test_normalize_shares_allows_under_100_and_zero():
    shares = normalize_shares({"1": "40", "2": "0", "3": "25.5"}, member_ids={1, 2, 3})
    assert shares == {"1": "40", "3": "25.5"}
    assert residual_percent(shares) == Decimal("34.5")


def test_normalize_shares_rejects_non_member():
    with pytest.raises(AaRuleError, match="not an active"):
        normalize_shares({"9": "10"}, member_ids={1, 2})


def test_residual_full_and_empty():
    assert residual_percent({"1": "100"}) == Decimal("0")
    assert residual_percent({}) == Decimal("100")


def test_default_rule_name_with_categories():
    assert default_rule_name(["coles", "manual"]) == "coles+manual"
    assert default_rule_name(["coles"], ["groceries", "rent"]) == "coles / groceries,rent"


def test_coverage_conflict_wildcard_vs_specific():
    a = coverage_keys(["coles"], [])
    b = coverage_keys(["coles"], ["groceries"])
    assert coverages_conflict(a, b)


def test_coverage_no_conflict_different_categories():
    a = coverage_keys(["coles"], ["groceries"])
    b = coverage_keys(["coles"], ["rent"])
    assert not coverages_conflict(a, b)


def test_resolve_prefers_specific_category():
    rules = [
        SimpleNamespace(id=1, enabled=True, source_types=["coles"], category_ids=[]),
        SimpleNamespace(
            id=2, enabled=True, source_types=["coles"], category_ids=["rent"]
        ),
    ]

    def find(source_type: str, category_id: str | None):
        st = source_type.strip().lower()
        cid = (category_id or "").strip() or None
        specific = wildcard = None
        for rule in rules:
            if not rule.enabled or st not in rule.source_types:
                continue
            cats = list(rule.category_ids or [])
            if not cats:
                wildcard = rule
            elif cid and cid in cats:
                specific = rule
        return specific or wildcard

    assert find("coles", "rent").id == 2
    assert find("coles", "groceries").id == 1
    assert find("commbank", "rent") is None
