from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from app.extensions import db
from app.models import AaRule, HouseholdMembership
from app.services.categories import get_vocabulary
from app.services.households import HouseholdError, require_active_household
from app.sources.registry import list_sources


class AaRuleError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def aa_residual_meta() -> dict[str, str]:
    vocab = get_vocabulary()
    residual = vocab.get("aa_residual") or {}
    return {
        "id": str(residual.get("id") or "family_subsidy"),
        "label": str(residual.get("label") or "家庭补贴"),
        "description": str(residual.get("description") or ""),
    }


def require_household(person_id: int):
    try:
        return require_active_household(person_id)
    except HouseholdError as exc:
        raise AaRuleError(exc.message, exc.status_code) from exc


def normalize_source_types(raw: Any) -> list[str]:
    if raw is None:
        raise AaRuleError("source_types required")
    if isinstance(raw, str):
        items = [raw]
    elif isinstance(raw, (list, tuple, set)):
        items = list(raw)
    else:
        raise AaRuleError("source_types must be a list")
    known = {s["source_type"] for s in list_sources()}
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in items:
        st = str(item or "").strip().lower()
        if not st:
            continue
        if st not in known:
            raise AaRuleError(f"unknown source_type: {st}")
        if st not in seen:
            seen.add(st)
            cleaned.append(st)
    if not cleaned:
        raise AaRuleError("至少选择一个数据源")
    return sorted(cleaned)


def normalize_category_ids(raw: Any) -> list[str]:
    """Empty list = all categories for the selected sources."""
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        items = [raw]
    elif isinstance(raw, (list, tuple, set)):
        items = list(raw)
    else:
        raise AaRuleError("category_ids must be a list")
    known = {c["id"] for c in (get_vocabulary().get("categories") or []) if c.get("id")}
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in items:
        cid = str(item or "").strip()
        if not cid:
            continue
        if cid not in known:
            raise AaRuleError(f"unknown category_id: {cid}")
        if cid not in seen:
            seen.add(cid)
            cleaned.append(cid)
    return sorted(cleaned)


def normalize_shares(raw: Any, *, member_ids: set[int]) -> dict[str, str]:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise AaRuleError("shares must be an object")
    out: dict[str, str] = {}
    total = Decimal("0")
    for key, value in raw.items():
        try:
            pid = int(key)
        except (TypeError, ValueError) as exc:
            raise AaRuleError(f"invalid person_id in shares: {key}") from exc
        if pid not in member_ids:
            raise AaRuleError(f"person {pid} is not an active household member")
        try:
            pct = Decimal(str(value))
        except (InvalidOperation, TypeError) as exc:
            raise AaRuleError(f"invalid percent for person {pid}") from exc
        if pct < 0 or pct > 100:
            raise AaRuleError(f"percent for person {pid} must be between 0 and 100")
        if pct == 0:
            continue
        normalized = format(pct.normalize(), "f")
        if "." in normalized:
            normalized = normalized.rstrip("0").rstrip(".")
        out[str(pid)] = normalized or "0"
        total += pct
    if total > Decimal("100"):
        raise AaRuleError("成员百分比合计不能超过 100%")
    return out


def residual_percent(shares: dict[str, str] | None) -> Decimal:
    total = sum(
        (Decimal(str(v)) for v in (shares or {}).values()),
        Decimal("0"),
    )
    return max(Decimal("0"), Decimal("100") - total)


def default_rule_name(source_types: list[str], category_ids: list[str] | None = None) -> str:
    base = "+".join(source_types) if source_types else "AA"
    cats = category_ids or []
    if not cats:
        return base
    return f"{base} / {','.join(cats)}"


def _active_member_ids(household_id: int) -> set[int]:
    rows = HouseholdMembership.query.filter_by(
        household_id=household_id, left_at=None
    ).all()
    return {m.person_id for m in rows}


def coverage_keys(source_types: list[str], category_ids: list[str]) -> set[str]:
    """Tokens describing what a rule claims.

    Wildcard (no categories): ``coles|*``
    Specific: ``coles|groceries``
    """
    keys: set[str] = set()
    cats = list(category_ids or [])
    for st in source_types:
        if not cats:
            keys.add(f"{st}|*")
        else:
            for cid in cats:
                keys.add(f"{st}|{cid}")
    return keys


def coverages_conflict(a: set[str], b: set[str]) -> set[str]:
    """Return human-readable overlap labels if coverages conflict."""
    conflicts: set[str] = set()
    for ka in a:
        sa, ca = ka.split("|", 1)
        for kb in b:
            sb, cb = kb.split("|", 1)
            if sa != sb:
                continue
            if ca == "*" or cb == "*" or ca == cb:
                label = sa if (ca == "*" or cb == "*") and ca != cb else f"{sa}/{ca if ca != '*' else cb}"
                if ca == "*" and cb == "*":
                    label = sa
                elif ca == "*":
                    label = f"{sa} (全部 vs {cb})"
                elif cb == "*":
                    label = f"{sa} (全部 vs {ca})"
                else:
                    label = f"{sa}/{ca}"
                conflicts.add(label)
    return conflicts


def _assert_no_coverage_overlap(
    *,
    household_id: int,
    source_types: list[str],
    category_ids: list[str],
    exclude_rule_id: int | None = None,
) -> None:
    wanted = coverage_keys(source_types, category_ids)
    q = AaRule.query.filter_by(household_id=household_id, enabled=True)
    if exclude_rule_id is not None:
        q = q.filter(AaRule.id != exclude_rule_id)
    for rule in q.all():
        other = coverage_keys(
            list(rule.source_types or []), list(rule.category_ids or [])
        )
        hit = coverages_conflict(wanted, other)
        if hit:
            raise AaRuleError(
                f"与规则 #{rule.id} 范围重叠: {', '.join(sorted(hit))}"
            )


def _serialize(rule: AaRule) -> dict[str, Any]:
    return rule.to_dict(residual_meta=aa_residual_meta())


def list_rules(*, person_id: int) -> list[dict[str, Any]]:
    hh = require_household(person_id)
    rules = (
        AaRule.query.filter_by(household_id=hh.id)
        .order_by(AaRule.id.asc())
        .all()
    )
    return [_serialize(r) for r in rules]


def get_rule(*, person_id: int, rule_id: int) -> dict[str, Any]:
    hh = require_household(person_id)
    rule = db.session.get(AaRule, rule_id)
    if not rule or rule.household_id != hh.id:
        raise AaRuleError("rule not found", 404)
    return _serialize(rule)


def create_rule(
    *,
    person_id: int,
    source_types: Any,
    category_ids: Any = None,
    shares: Any = None,
    enabled: bool = True,
    name: str | None = None,
) -> dict[str, Any]:
    hh = require_household(person_id)
    types = normalize_source_types(source_types)
    cats = normalize_category_ids(category_ids)
    member_ids = _active_member_ids(hh.id)
    if not member_ids:
        raise AaRuleError("家庭没有成员")
    norm_shares = normalize_shares(shares, member_ids=member_ids)
    if enabled:
        _assert_no_coverage_overlap(
            household_id=hh.id, source_types=types, category_ids=cats
        )
    label = (name or "").strip() or default_rule_name(types, cats)
    rule = AaRule(
        household_id=hh.id,
        name=label[:120],
        source_types=types,
        category_ids=cats,
        enabled=bool(enabled),
        shares=norm_shares,
    )
    db.session.add(rule)
    db.session.commit()
    return _serialize(rule)


def update_rule(
    *,
    person_id: int,
    rule_id: int,
    source_types: Any = None,
    category_ids: Any = None,
    shares: Any = None,
    enabled: bool | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    hh = require_household(person_id)
    rule = db.session.get(AaRule, rule_id)
    if not rule or rule.household_id != hh.id:
        raise AaRuleError("rule not found", 404)

    types = (
        normalize_source_types(source_types)
        if source_types is not None
        else list(rule.source_types or [])
    )
    cats = (
        normalize_category_ids(category_ids)
        if category_ids is not None
        else list(rule.category_ids or [])
    )
    member_ids = _active_member_ids(hh.id)
    if shares is not None:
        norm_shares = normalize_shares(shares, member_ids=member_ids)
    else:
        norm_shares = normalize_shares(
            {str(k): str(v) for k, v in (rule.shares or {}).items()},
            member_ids=member_ids,
        )

    next_enabled = rule.enabled if enabled is None else bool(enabled)
    if next_enabled:
        _assert_no_coverage_overlap(
            household_id=hh.id,
            source_types=types,
            category_ids=cats,
            exclude_rule_id=rule.id,
        )

    rule.source_types = types
    rule.category_ids = cats
    rule.shares = norm_shares
    rule.enabled = next_enabled
    if name is not None:
        label = name.strip() or default_rule_name(types, cats)
        rule.name = label[:120]

    db.session.commit()
    return _serialize(rule)


def delete_rule(*, person_id: int, rule_id: int) -> None:
    hh = require_household(person_id)
    rule = db.session.get(AaRule, rule_id)
    if not rule or rule.household_id != hh.id:
        raise AaRuleError("rule not found", 404)
    db.session.delete(rule)
    db.session.commit()


def resolve_rule(
    household_id: int,
    source_type: str,
    category_id: str | None = None,
) -> AaRule | None:
    """Prefer category-specific rule, else source-wide (empty category_ids)."""
    st = (source_type or "").strip().lower()
    if not st:
        return None
    cid = (category_id or "").strip() or None
    rules = AaRule.query.filter_by(household_id=household_id, enabled=True).all()
    specific: AaRule | None = None
    wildcard: AaRule | None = None
    for rule in rules:
        if st not in (rule.source_types or []):
            continue
        cats = list(rule.category_ids or [])
        if not cats:
            wildcard = rule
        elif cid and cid in cats:
            specific = rule
    return specific or wildcard
