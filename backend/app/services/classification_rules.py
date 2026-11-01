from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.orm import joinedload
from sqlalchemy import func, or_

from app.extensions import db
from app.models import Bill, ClassificationRule, Entry


def rules_for_household(household_id: int) -> list[ClassificationRule]:
    return (
        ClassificationRule.query.filter_by(household_id=household_id, enabled=True)
        .order_by(ClassificationRule.position.asc(), ClassificationRule.id.asc())
        .all()
    )


def best_match(
    entry: Entry, rules: list[ClassificationRule]
) -> ClassificationRule | None:
    """Longest matching keyword wins, across each rule's match field."""
    best_rule: ClassificationRule | None = None
    best_len = 0
    for rule in rules:
        field = (rule.match_field or "name").strip().lower()
        text = (
            (entry.bill.merchant if entry.bill else "")
            if field == "merchant"
            else (entry.name or "")
        )
        normalized = (text or "").casefold()
        for keyword in rule.keywords or []:
            kw = str(keyword or "").strip().casefold()
            if kw and kw in normalized and len(kw) > best_len:
                best_len = len(kw)
                best_rule = rule
    return best_rule


def apply_rule_matches(
    entries: list[Entry],
    *,
    rules_cache: dict[int, list[ClassificationRule]],
) -> list[int]:
    """Assign matched rules in-place; returns the matched entry ids."""
    matched_ids: list[int] = []
    for entry in entries:
        household_id = entry.bill.household_id if entry.bill else None
        if household_id is None:
            continue
        rules = rules_cache.get(household_id)
        if rules is None:
            rules = rules_for_household(household_id)
            rules_cache[household_id] = rules
        rule = best_match(entry, rules)
        if rule is None:
            continue
        entry.category_id = rule.category_id
        entry.category_confidence = Decimal("1.0")
        entry.classification_status = "confirmed"
        entry.tags = []
        matched_ids.append(entry.id)
    return matched_ids


def apply_rules_to_household(
    household_id: int,
    *,
    scope: str = "unclassified",
) -> dict[str, Any]:
    """Retroactively apply rules to existing entries in a household."""
    rules = rules_for_household(household_id)
    if not rules:
        return {"matched": 0, "scanned": 0}

    q = Entry.query.join(Bill, Entry.bill_id == Bill.id).filter(
        Bill.household_id == household_id,
        Entry.manual_override == False,  # noqa: E712
    )
    if scope == "unclassified":
        q = q.filter(Entry.classification_status == "unclassified")
    elif scope == "pending":
        q = q.filter(Entry.classification_status.in_(["unclassified", "pending"]))
    elif scope == "confirmed":
        q = q.filter(Entry.classification_status == "confirmed")

    entries = q.options(joinedload(Entry.bill)).all()
    cache: dict[int, list[ClassificationRule]] = {household_id: rules}
    matched_ids = apply_rule_matches(entries, rules_cache=cache)
    matched = len(matched_ids)
    if matched:
        db.session.commit()
    return {"matched": matched, "scanned": len(entries)}


def count_matches(
    household_id: int, keywords: list[str], match_field: str
) -> int:
    """How many existing entries would match these keywords."""
    kws = [str(k).strip().casefold() for k in (keywords or []) if str(k or "").strip()]
    if not kws:
        return 0
    column = Bill.merchant if (match_field or "name") == "merchant" else Entry.name
    conditions = [func.lower(column).like(f"%{kw}%") for kw in kws]
    return (
        db.session.query(Entry.id)
        .join(Bill, Entry.bill_id == Bill.id)
        .filter(Bill.household_id == household_id, or_(*conditions))
        .count()
    )


def merge_rules(household_id: int) -> list[ClassificationRule]:
    """Merge rules that share the same category + match field into one."""
    rules = (
        ClassificationRule.query.filter_by(household_id=household_id)
        .order_by(ClassificationRule.position.asc(), ClassificationRule.id.asc())
        .all()
    )
    groups: dict[tuple[str, str], list[ClassificationRule]] = {}
    for rule in rules:
        groups.setdefault((rule.category_id, rule.match_field), []).append(rule)

    for group in groups.values():
        if len(group) < 2:
            continue
        keeper = group[0]
        keywords: list[str] = []
        seen: set[str] = set()
        for rule in group:
            for keyword in rule.keywords or []:
                keyword = str(keyword or "").strip()
                if keyword and keyword not in seen:
                    seen.add(keyword)
                    keywords.append(keyword)
        keeper.keywords = keywords
        keeper.enabled = True
        for rule in group[1:]:
            db.session.delete(rule)

    db.session.commit()
    return (
        ClassificationRule.query.filter_by(household_id=household_id)
        .order_by(ClassificationRule.position.asc(), ClassificationRule.id.asc())
        .all()
    )
