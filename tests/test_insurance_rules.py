"""Unit tests for the insurance-mode rule registry and scorer."""

from graph.rules_insurance import (
    INSURANCE_RISK_RULES,
    JURISDICTION_TIER_TRIGGERS,
    LLM_EXTRACTED_TRIGGERS,
    RULES_BY_TRIGGER,
    compute_jurisdiction_flags,
    score_insurance_case,
)
from models.schemas import Entity
from models.schemas_insurance import InsuranceCase


# ---------------------------------------------------------------------------
# Registry integrity
# ---------------------------------------------------------------------------

class TestRegistryIntegrity:
    def test_has_31_rules(self):
        assert len(INSURANCE_RISK_RULES) == 31

    def test_unique_ids(self):
        ids = [rule.id for rule in INSURANCE_RISK_RULES]
        assert len(ids) == len(set(ids))

    def test_unique_trigger_fields(self):
        triggers = [rule.trigger_field for rule in INSURANCE_RISK_RULES]
        assert len(triggers) == len(set(triggers))

    def test_weights_in_valid_range(self):
        for rule in INSURANCE_RISK_RULES:
            assert 0 < rule.weight <= 1

    def test_jurisdiction_rules_are_not_llm_extracted(self):
        for trigger in JURISDICTION_TIER_TRIGGERS.values():
            assert RULES_BY_TRIGGER[trigger].llm_extracted is False
            assert trigger not in LLM_EXTRACTED_TRIGGERS

    def test_jurisdiction_tiers_are_weighted_differently(self):
        weights = {
            trigger: RULES_BY_TRIGGER[trigger].weight
            for trigger in JURISDICTION_TIER_TRIGGERS.values()
        }
        assert len(set(weights.values())) == 3
        assert weights["jurisdiction_call_for_action"] > weights["jurisdiction_enhanced_dd"]
        assert weights["jurisdiction_enhanced_dd"] > weights["jurisdiction_greylist"]

    def test_jurisdiction_labels_are_distinct(self):
        labels = {
            RULES_BY_TRIGGER[trigger].label_fr
            for trigger in JURISDICTION_TIER_TRIGGERS.values()
        }
        assert len(labels) == 3
        greylist_label = RULES_BY_TRIGGER["jurisdiction_greylist"].label_fr
        assert "n'exige pas" in greylist_label or "au cas par cas" in greylist_label


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
# compute_jurisdiction_flags() -- deterministic FATF lookup, no LLM judgment
# ---------------------------------------------------------------------------

def _case(souscripteur_country=None, **party_countries) -> dict:
    """Build a minimal case dict with a souscripteur and optional other parties."""
    case = {
        "souscripteur": {"name": "Souscripteur", "country": souscripteur_country},
        "assure": None,
        "beneficiaires": [],
        "payeur": None,
        "intermediaire": None,
    }
    for key, country in party_countries.items():
        if key == "beneficiaires":
            case["beneficiaires"] = [{"name": "Beneficiaire", "country": country}]
        else:
            case[key] = {"name": key, "country": country}
    return case


class TestComputeJurisdictionFlags:
    def test_countermeasures_country_sets_call_for_action(self):
        flags = compute_jurisdiction_flags(_case(souscripteur_country="IR"))
        assert flags["jurisdiction_call_for_action"] is True
        assert flags["jurisdiction_enhanced_dd"] is False
        assert flags["jurisdiction_greylist"] is False

    def test_dprk_sets_call_for_action(self):
        flags = compute_jurisdiction_flags(_case(souscripteur_country="KP"))
        assert flags["jurisdiction_call_for_action"] is True

    def test_myanmar_sets_enhanced_dd(self):
        flags = compute_jurisdiction_flags(_case(souscripteur_country="MM"))
        assert flags["jurisdiction_call_for_action"] is False
        assert flags["jurisdiction_enhanced_dd"] is True
        assert flags["jurisdiction_greylist"] is False

    def test_greylist_country_sets_greylist_only(self):
        flags = compute_jurisdiction_flags(_case(souscripteur_country="SY"))
        assert flags["jurisdiction_call_for_action"] is False
        assert flags["jurisdiction_enhanced_dd"] is False
        assert flags["jurisdiction_greylist"] is True

    def test_panama_is_not_on_any_fatf_list_and_does_not_trigger(self):
        """Panama was delisted by FATF in October 2023 -- the real-world case
        that exposed the LLM asserting FATF status from stale training data."""
        flags = compute_jurisdiction_flags(_case(souscripteur_country="PA"))
        assert flags["jurisdiction_call_for_action"] is False
        assert flags["jurisdiction_enhanced_dd"] is False
        assert flags["jurisdiction_greylist"] is False

    def test_clean_country_does_not_trigger(self):
        flags = compute_jurisdiction_flags(_case(souscripteur_country="TN"))
        assert not any(flags.values())

    def test_checks_all_parties_not_just_souscripteur(self):
        case = _case(souscripteur_country="TN", payeur="IR")
        flags = compute_jurisdiction_flags(case)
        assert flags["jurisdiction_call_for_action"] is True

    def test_checks_beneficiaires(self):
        case = _case(souscripteur_country="TN", beneficiaires="MM")
        flags = compute_jurisdiction_flags(case)
        assert flags["jurisdiction_enhanced_dd"] is True

    def test_no_country_does_not_trigger(self):
        flags = compute_jurisdiction_flags(_case())
        assert not any(flags.values())

    def test_different_parties_in_different_tiers_both_flag(self):
        case = _case(souscripteur_country="SY", payeur="IR")
        flags = compute_jurisdiction_flags(case)
        assert flags["jurisdiction_call_for_action"] is True
        assert flags["jurisdiction_greylist"] is True


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

    def test_risk_flags_returns_exactly_the_31_trigger_fields(self):
        case = self._make_case()
        flags = case.risk_flags()
        assert set(flags.keys()) == set(RULES_BY_TRIGGER.keys())
        assert len(flags) == 31

    def test_risk_flags_reflects_set_values(self):
        case = self._make_case(early_surrender=True, sanctions_list_hit=True)
        flags = case.risk_flags()
        assert flags["early_surrender"] is True
        assert flags["sanctions_list_hit"] is True
        assert flags["premium_income_mismatch"] is False
