"""Tests for the insurance-mode extraction path through the STR graph.

Uses a mocked LLM response (no live API calls) for the scenario:
"Souscription d'un contrat vie capital 500 000 TND, prime payee en
especes 60 000 TND par un tiers sans lien, client focalise sur les
modalites de rachat"
"""

import uuid
from unittest.mock import patch, AsyncMock

from graph.str_graph import run_str_graph


INSURANCE_SCENARIO_INPUT: str = (
    "Souscription d'un contrat vie capital 500 000 TND, prime payee en "
    "especes 60 000 TND par un tiers sans lien, client focalise sur les "
    "modalites de rachat"
)

MOCK_INSURANCE_EXTRACTION_DATA: dict = {
    "operation_type": "souscription",
    "operation_date": "2026-03-15",
    "policy_reference": "POL-2026-001",
    "product_type": "assurance_vie",
    "product_risk_class": "eleve",
    "sum_assured": 500000,
    "currency": "TND",
    "souscripteur": {
        "name": "Client Test",
        "entity_type": "person",
        "country": "TN",
        "is_pep": False,
    },
    "assure": None,
    "beneficiaires": [],
    "payeur": {
        "name": "Tiers Payeur",
        "entity_type": "person",
        "country": "TN",
        "is_pep": False,
    },
    "intermediaire": None,
    "amount": 60000,
    "payment_method": "especes",
    "description": "Souscription contrat vie, prime en especes payee par un tiers",
    "red_flags": [],
    "cash_premium_above_threshold": True,
    "unrelated_third_party_payer": True,
    "exit_focused_behaviour": True,
}

MOCK_NARRATIVE: str = (
    "Souscription d'un contrat d'assurance vie d'un capital de 500 000 TND. "
    "La prime de 60 000 TND a ete reglee en especes par un tiers sans lien "
    "etabli avec le souscripteur, qui s'est par ailleurs montre focalise "
    "sur les modalites de rachat du contrat."
)


def _make_insurance_request() -> dict:
    return {
        "analyst_input": INSURANCE_SCENARIO_INPUT,
        "reporting_institution": "Assurances Test",
        "analyst_id": "ANA-INS-001",
        "case_reference": "TEST-INS-001",
        "case_id": str(uuid.uuid4()),
        "sector": "assurance",
    }


class TestInsuranceExtractionPipeline:
    async def test_insurance_scenario_sets_expected_flags(self):
        with (
            patch(
                "graph.str_graph.call_llm_structured",
                return_value=MOCK_INSURANCE_EXTRACTION_DATA,
            ),
            patch("graph.str_graph.call_llm", return_value=MOCK_NARRATIVE),
            patch(
                "graph.str_graph.screen_entities_async",
                new=AsyncMock(return_value={}),
            ),
        ):
            final_state = await run_str_graph(_make_insurance_request())

        assert not final_state.get("errors")

        case = final_state["extracted_transaction"]
        assert case["cash_premium_above_threshold"] is True
        assert case["unrelated_third_party_payer"] is True
        assert case["exit_focused_behaviour"] is True

    async def test_insurance_scenario_risk_level_is_critical(self):
        with (
            patch(
                "graph.str_graph.call_llm_structured",
                return_value=MOCK_INSURANCE_EXTRACTION_DATA,
            ),
            patch("graph.str_graph.call_llm", return_value=MOCK_NARRATIVE),
            patch(
                "graph.str_graph.screen_entities_async",
                new=AsyncMock(return_value={}),
            ),
        ):
            final_state = await run_str_graph(_make_insurance_request())

        assert final_state["risk_level"] == "critical"
        assert final_state["risk_score"] >= 0.6

    async def test_insurance_scenario_extracts_parties(self):
        with (
            patch(
                "graph.str_graph.call_llm_structured",
                return_value=MOCK_INSURANCE_EXTRACTION_DATA,
            ),
            patch("graph.str_graph.call_llm", return_value=MOCK_NARRATIVE),
            patch(
                "graph.str_graph.screen_entities_async",
                new=AsyncMock(return_value={}),
            ),
        ):
            final_state = await run_str_graph(_make_insurance_request())

        names = {e["name"] for e in final_state["extracted_entities"]}
        assert names == {"Client Test", "Tiers Payeur"}

    async def test_insurance_sanctions_hit_sets_case_flag_before_scoring(self):
        hit_sanctions = {"Client Test": {"hit": True, "detail": "OFAC SDN"}}

        with (
            patch(
                "graph.str_graph.call_llm_structured",
                return_value=MOCK_INSURANCE_EXTRACTION_DATA,
            ),
            patch("graph.str_graph.call_llm", return_value=MOCK_NARRATIVE),
            patch(
                "graph.str_graph.screen_entities_async",
                new=AsyncMock(return_value=hit_sanctions),
            ),
        ):
            final_state = await run_str_graph(_make_insurance_request())

        assert final_state["extracted_transaction"]["sanctions_list_hit"] is True
        assert final_state["risk_level"] == "critical"
        assert final_state["risk_score"] == 1.0
