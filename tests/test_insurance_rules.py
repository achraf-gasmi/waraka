"""Unit tests for the insurance-mode rule registry and scorer."""

from graph.rules_insurance import (
    INSURANCE_RISK_RULES,
    RULES_BY_TRIGGER,
    score_insurance_case,
)
from models.schemas import Entity
from models.schemas_insurance import InsuranceCase


# ---------------------------------------------------------------------------
# Registry integrity
# ---------------------------------------------------------------------------

class TestRegistryIntegrity:
    def test_has_29_rules(self):
        assert len(INSURANCE_RISK_RULES) == 29

    def test_unique_ids(self):
        ids = [rule.id for rule in INSURANCE_RISK_RULES]
        assert len(ids) == len(set(ids))

    def test_unique_trigger_fields(self):
        triggers = [rule.trigger_field for rule in INSURANCE_RISK_RULES]
        assert len(triggers) == len(set(triggers))

    def test_weights_in_valid_range(self):
        for rule in INSURANCE_RISK_RULES:
            assert 0 < rule.weight <= 1


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _flags(**overrides: bool) -> dict:
    flags = {trigger: False for trigger in RULES_BY_TRIGGER}
    flags.update(overrides)
    return flags


class TestScoreInsuranceCase:
    def test_sanctions_only_is_critical(self):
        _, severity, level = score_insurance_case(_flags(sanctions_list_hit=True))
        assert level == "critical"
        assert severity >= 0.6

    def test_early_surrender_and_cash_premium_is_critical(self):
        _, severity, level = score_insurance_case(
            _flags(early_surrender=True, cash_premium_above_threshold=True)
        )
        assert level == "critical"
        assert severity >= 0.6

    def test_premium_income_mismatch_only_is_high(self):
        _, severity, level = score_insurance_case(_flags(premium_income_mismatch=True))
        assert level == "high"
        assert 0.4 <= severity < 0.6

    def test_linked_multiple_contracts_only_is_medium(self):
        _, severity, level = score_insurance_case(_flags(linked_multiple_contracts=True))
        assert level == "medium"
        assert 0.2 <= severity < 0.4

    def test_no_flags_is_low(self):
        matched, severity, level = score_insurance_case(_flags())
        assert level == "low"
        assert severity == 0.0
        assert matched == []

    def test_severity_capped_at_1(self):
        all_true = {trigger: True for trigger in RULES_BY_TRIGGER}
        _, severity, level = score_insurance_case(all_true)
        assert severity == 1.0
        assert level == "critical"


# ---------------------------------------------------------------------------
# InsuranceCase.risk_flags()
# ---------------------------------------------------------------------------

class TestInsuranceCaseRiskFlags:
    def _make_case(self, **overrides) -> InsuranceCase:
        return InsuranceCase(
            case_id="TEST-CASE",
            operation_type="souscription",
            souscripteur=Entity(name="Client Test", entity_type="person"),
            **overrides,
        )

    def test_risk_flags_returns_exactly_the_29_trigger_fields(self):
        case = self._make_case()
        flags = case.risk_flags()
        assert set(flags.keys()) == set(RULES_BY_TRIGGER.keys())
        assert len(flags) == 29

    def test_risk_flags_reflects_set_values(self):
        case = self._make_case(early_surrender=True, sanctions_list_hit=True)
        flags = case.risk_flags()
        assert flags["early_surrender"] is True
        assert flags["sanctions_list_hit"] is True
        assert flags["premium_income_mismatch"] is False
