from datetime import UTC, datetime

from app.models import OriginDecision, TariffRule, TradeCreate


def decide_origin(
    trade: TradeCreate,
    hs_code: str,
    rules: list[TariffRule],
    excluded_materials: list[dict[str, object]],
    *,
    has_document: bool,
    evidence_confidence: float,
    documented_wholly_obtained: bool | None,
    documented_value_added_pct: float | None,
    documented_tariff_heading: str | None,
) -> OriginDecision:
    if not has_document or evidence_confidence < 0.8:
        return OriginDecision(
            verified=False,
            reason=(
                "A supporting document with sufficiently confident extracted evidence is required."
            ),
            confidence=0,
            evaluated_at=datetime.now(UTC),
        )
    today = datetime.now(UTC).date()
    matches = [
        rule
        for rule in rules
        if hs_code.startswith(rule.hs_code_prefix)
        and rule.origin_country == trade.origin_country
        and rule.destination_country == trade.destination_country
        and rule.effective_from <= today
        and (rule.effective_to is None or rule.effective_to >= today)
    ]
    if not matches:
        return OriginDecision(
            verified=False,
            reason="No active authoritative rule matches the HS code and trade corridor.",
            confidence=0,
            evaluated_at=datetime.now(UTC),
        )

    matches.sort(
        key=lambda rule: (len(rule.hs_code_prefix), rule.organization_id is not None), reverse=True
    )
    rule = matches[0]
    if rule.rule_type == "wholly_obtained":
        verified = trade.wholly_obtained is True and documented_wholly_obtained is True
        reason = (
            "Submitted declaration is corroborated by document extraction "
            "and satisfies the active rule."
            if verified
            else "Wholly-obtained evidence is missing or not corroborated "
            "by the submitted document."
        )
    elif rule.rule_type == "value_added":
        verified = (
            trade.value_added_pct is not None
            and documented_value_added_pct is not None
            and rule.minimum_value_added_pct is not None
            and trade.value_added_pct >= rule.minimum_value_added_pct
            and documented_value_added_pct >= float(rule.minimum_value_added_pct)
            and abs(float(trade.value_added_pct) - documented_value_added_pct) <= 0.01
        )
        reason = (
            "Submitted value-added figure is corroborated by document extraction "
            "and satisfies the threshold."
            if verified
            else "Value-added evidence is missing, inconsistent, or below the active threshold."
        )
    elif rule.rule_type == "change_in_tariff_classification":
        verified = (
            trade.non_originating_tariff_heading is not None
            and documented_tariff_heading is not None
            and rule.required_tariff_heading_prefix is not None
            and trade.non_originating_tariff_heading == documented_tariff_heading
            and not trade.non_originating_tariff_heading.startswith(
                rule.required_tariff_heading_prefix
            )
        )
        reason = (
            "Submitted tariff heading is corroborated by document extraction "
            "and meets the tariff-shift rule."
            if verified
            else "Tariff-shift evidence is missing, inconsistent, or does not meet the rule."
        )
    elif rule.rule_type == "specific_process":
        verified = False
        reason = (
            "Specific-process evidence cannot be inferred from the submitted fields; "
            "manual review is required."
        )
    else:
        alternatives = [
            rule.minimum_value_added_pct is not None
            and trade.value_added_pct is not None
            and documented_value_added_pct is not None
            and trade.value_added_pct >= rule.minimum_value_added_pct
            and documented_value_added_pct >= float(rule.minimum_value_added_pct)
            and abs(float(trade.value_added_pct) - documented_value_added_pct) <= 0.01,
            rule.required_tariff_heading_prefix is not None
            and trade.non_originating_tariff_heading is not None
            and documented_tariff_heading == trade.non_originating_tariff_heading
            and not trade.non_originating_tariff_heading.startswith(
                rule.required_tariff_heading_prefix
            ),
            trade.wholly_obtained is True and documented_wholly_obtained is True,
        ]
        verified = any(alternatives)
        reason = (
            "At least one evidenced alternative satisfies the active rule."
            if verified
            else "No documented alternative satisfies the active rule."
        )

    excluded_match = any(
        item.get("code") == evidence.get("code")
        for item in rule.excluded_inputs
        for evidence in excluded_materials
    )
    if excluded_match:
        verified = False
        reason = "An evidenced input is excluded by the active rule."

    return OriginDecision(
        verified=verified,
        rule_id=rule.id,
        agreement=rule.agreement,
        reason=reason,
        confidence=evidence_confidence if verified else 0.0,
        evaluated_at=datetime.now(UTC),
    )
