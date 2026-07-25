"""Integration tests for the STR drafting pipeline.

These tests use the real LLM (ANTHROPIC_API_KEY required) for the
full integration test, and mocked LLM for unit tests.
"""

import json
import pytest
from unittest.mock import patch, AsyncMock

from tests.conftest import (
    MOCK_ANALYST_INPUT,
    EXPECTED_RISK_LEVEL,
    EXPECTED_RISK_INDICATORS_MIN,
    EXPECTED_ENTITY_COUNT,
    MOCK_SANCTIONS_RESPONSE_CLEAN,
    MOCK_SANCTIONS_RESPONSE_SKIPPED,
    MOCK_SANCTIONS_RESPONSE_TIMEOUT,
)
from graph.str_graph import run_str_graph, assess_risk_node, STRState
from tools.goaml_tool import validate_str_xml
from models.schemas import RiskLevel, Entity
from api.main import _compute_sanctions_status
import uuid


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MOCK_ENTITY_EXTRACTION_DATA: dict = {
    "entities": [
        {
            "name": "Immobiliere Carthage SARL",
            "entity_type": "company",
            "id_number": "B123456789",
            "country": "TN",
            "is_pep": False,
        },
        {
            "name": "Gulf Properties FZE",
            "entity_type": "company",
            "country": "AE",
            "is_pep": False,
        },
        {
            "name": "Mediterranean Holdings Ltd",
            "entity_type": "company",
            "country": "MT",
            "is_pep": False,
        },
        {
            "name": "Atlantic Capital SA",
            "entity_type": "company",
            "country": "LU",
            "is_pep": False,
        },
    ],
    "transaction": {
        "transaction_id": "TX-MOCK-001",
        "date": "2026-03-15",
        "amount": 850000,
        "currency": "TND",
        "transaction_type": "virement",
        "sender": {
            "name": "Immobiliere Carthage SARL",
            "entity_type": "company",
            "country": "TN",
            "is_pep": False,
        },
        "receiver": {
            "name": "Gulf Properties FZE",
            "entity_type": "company",
            "country": "AE",
            "is_pep": False,
        },
        "intermediaries": [
            {
                "name": "Mediterranean Holdings Ltd",
                "entity_type": "company",
                "country": "MT",
                "is_pep": False,
            },
            {
                "name": "Atlantic Capital SA",
                "entity_type": "company",
                "country": "LU",
                "is_pep": False,
            },
        ],
        "no_prior_relationship": True,
        "red_flags": ["high_risk_jurisdiction", "multiple_intermediaries"],
    },
    "initial_red_flags": [
        "Transaction vers une juridiction a haut risque (EAU)",
        "Recours a plusieurs intermediaires",
        "Absence de relation anterieure",
    ],
}

MOCK_NARRATIVE: str = (
    "La societe Immobiliere Carthage SARL a effectue le 15 mars 2026 "
    "un virement de 850 000 TND vers Gulf Properties FZE aux Emirats Arabes Unis "
    "via deux intermediaires (Mediterranean Holdings Ltd et Atlantic Capital SA). "
    "Aucun contrat fourni. Aucune relation anterieure."
)


def _make_request_dict(analyst_input: str = MOCK_ANALYST_INPUT) -> dict:
    return {
        "analyst_input": analyst_input,
        "reporting_institution": "BH Bank",
        "analyst_id": "ANA-TEST-001",
        "case_reference": "TEST-CASE-001",
        "case_id": str(uuid.uuid4()),
    }


# ---------------------------------------------------------------------------
# Unit tests -- assess_risk_node (sync, no LLM needed)
# ---------------------------------------------------------------------------

class TestAssessRiskNode:
    def _base_state(self) -> STRState:
        return {
            "request": {"case_id": "TEST", "analyst_id": "A", "reporting_institution": "B", "analyst_input": ""},
            "extracted_entities": [],
            "extracted_transaction": {
                "transaction_id": "TX-001",
                "date": "2026-03-15",
                "amount": 850000,
                "currency": "TND",
                "transaction_type": "virement",
                "sender": {"name": "Carthage SARL", "entity_type": "company", "country": "TN", "is_pep": False},
                "receiver": {"name": "Gulf Properties", "entity_type": "company", "country": "IR", "is_pep": False},
                "intermediaries": [
                    {"name": "Inter1", "entity_type": "company", "country": "MT"},
                    {"name": "Inter2", "entity_type": "company", "country": "LU"},
                ],
                "no_prior_relationship": True,
            },
            "sanctions_results": {},
            "risk_indicators": [],
            "risk_level": "low",
            "confidence": 0.0,
            "narrative_fr": "",
            "goaml_xml": "",
            "analyst_notes": [],
            "errors": [],
        }

    def test_demo_scenario_is_critical(self):
        state = self._base_state()
        result = assess_risk_node(state)
        assert result["risk_level"] == RiskLevel.CRITICAL.value

    def test_demo_scenario_confidence_above_threshold(self):
        state = self._base_state()
        result = assess_risk_node(state)
        assert result["confidence"] >= 0.6

    def test_demo_scenario_has_4_indicators(self):
        """R001 (IR, FATF blacklist tier, weight 0.40), R002 (850k > 500k), R003 (2 intermediaries), R006 (no prior)."""
        state = self._base_state()
        result = assess_risk_node(state)
        assert len(result["risk_indicators"]) >= 4

    def test_sanctions_hit_increases_confidence(self):
        state = self._base_state()
        state["sanctions_results"] = {"Gulf Properties": {"hit": True, "detail": "OFAC"}}
        result = assess_risk_node(state)
        assert result["confidence"] >= 0.85

    def test_low_amount_safe_jurisdiction_is_low_risk(self):
        state = self._base_state()
        state["extracted_transaction"]["amount"] = 10000
        state["extracted_transaction"]["receiver"]["country"] = "FR"
        state["extracted_transaction"]["intermediaries"] = []
        state["extracted_transaction"]["no_prior_relationship"] = False
        result = assess_risk_node(state)
        assert result["risk_level"] in (RiskLevel.LOW.value, RiskLevel.MEDIUM.value)

    def test_confidence_capped_at_1(self):
        state = self._base_state()
        state["sanctions_results"] = {"x": {"hit": True, "detail": "test"}}
        state["extracted_transaction"]["sender"]["is_pep"] = True
        result = assess_risk_node(state)
        assert result["confidence"] <= 1.0


# ---------------------------------------------------------------------------
# Integration tests -- full pipeline with mocked LLM and sanctions
# ---------------------------------------------------------------------------

class TestFullPipelineMocked:
    async def test_full_pipeline_mocked_llm(self):
        """Run the full 5-node graph with mocked LLM and sanctions."""
        with (
            patch("graph.str_graph.call_llm_structured", return_value=MOCK_ENTITY_EXTRACTION_DATA),
            patch("graph.str_graph.call_llm", return_value=MOCK_NARRATIVE),
            patch(
                "graph.str_graph.screen_entities_async",
                new=AsyncMock(return_value=MOCK_SANCTIONS_RESPONSE_CLEAN),
            ),
        ):
            final_state = await run_str_graph(_make_request_dict())

        assert final_state["risk_level"] == EXPECTED_RISK_LEVEL
        assert len(final_state["risk_indicators"]) >= EXPECTED_RISK_INDICATORS_MIN
        assert len(final_state["extracted_entities"]) >= EXPECTED_ENTITY_COUNT

        xml = final_state["goaml_xml"]
        assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?>')
        is_valid, errors = validate_str_xml(xml)
        assert is_valid, f"goAML XML validation failed: {errors}"

        assert len(final_state["narrative_fr"]) > 50
        assert not final_state.get("errors")

    async def test_full_pipeline_with_sanctions_hit(self):
        """Pipeline correctly flags sanctions hit."""
        hit_sanctions = {
            "Immobiliere Carthage SARL": {"hit": False, "detail": None},
            "Gulf Properties FZE": {"hit": True, "detail": "Listed on OFAC SDN list"},
            "Mediterranean Holdings Ltd": {"hit": False, "detail": None},
            "Atlantic Capital SA": {"hit": False, "detail": None},
        }

        with (
            patch("graph.str_graph.call_llm_structured", return_value=MOCK_ENTITY_EXTRACTION_DATA),
            patch("graph.str_graph.call_llm", return_value=MOCK_NARRATIVE),
            patch(
                "graph.str_graph.screen_entities_async",
                new=AsyncMock(return_value=hit_sanctions),
            ),
        ):
            final_state = await run_str_graph(_make_request_dict())

        assert "SANCTIONS HIT: Gulf Properties FZE" in final_state.get("analyst_notes", [])
        assert final_state["confidence"] >= 0.85

    async def test_missing_api_key_produces_distinct_analyst_notes_and_incomplete_status(self):
        """When OPENSANCTIONS_API_KEY is missing, entities come back status='skipped'.

        The pipeline must emit a distinct per-entity analyst note (not the generic
        catastrophic-failure line), and the resulting entities must NOT be reported
        as sanctions_status='all_screened' at the API layer.
        """
        with (
            patch("graph.str_graph.call_llm_structured", return_value=MOCK_ENTITY_EXTRACTION_DATA),
            patch("graph.str_graph.call_llm", return_value=MOCK_NARRATIVE),
            patch(
                "graph.str_graph.screen_entities_async",
                new=AsyncMock(return_value=MOCK_SANCTIONS_RESPONSE_SKIPPED),
            ),
        ):
            final_state = await run_str_graph(_make_request_dict())

        entities = [Entity(**e) for e in final_state["extracted_entities"]]
        assert all(e.sanctions_status == "skipped" for e in entities)

        notes = final_state.get("analyst_notes", [])
        assert any("NON EFFECTUEE" in n for n in notes)
        assert "Verification sanctions echouee -- verifier manuellement" not in notes

        sanctions_status = _compute_sanctions_status(entities)
        assert sanctions_status != "all_screened"
        assert sanctions_status == "none_screened"

    async def test_timeout_produces_distinct_analyst_notes_and_incomplete_status(self):
        """When sanctions checks time out, entities come back status='failed'.

        Same fail-closed guarantee as the missing-API-key case: distinct notes,
        and sanctions_status must not read as 'all_screened'.
        """
        with (
            patch("graph.str_graph.call_llm_structured", return_value=MOCK_ENTITY_EXTRACTION_DATA),
            patch("graph.str_graph.call_llm", return_value=MOCK_NARRATIVE),
            patch(
                "graph.str_graph.screen_entities_async",
                new=AsyncMock(return_value=MOCK_SANCTIONS_RESPONSE_TIMEOUT),
            ),
        ):
            final_state = await run_str_graph(_make_request_dict())

        entities = [Entity(**e) for e in final_state["extracted_entities"]]
        assert all(e.sanctions_status == "failed" for e in entities)

        notes = final_state.get("analyst_notes", [])
        assert any("EN ECHEC" in n for n in notes)
        assert "Verification sanctions echouee -- verifier manuellement" not in notes

        sanctions_status = _compute_sanctions_status(entities)
        assert sanctions_status != "all_screened"
        assert sanctions_status == "none_screened"

    async def test_all_screened_when_every_entity_screened_clean(self):
        """Sanity check: a fully successful screen does read as 'all_screened'."""
        with (
            patch("graph.str_graph.call_llm_structured", return_value=MOCK_ENTITY_EXTRACTION_DATA),
            patch("graph.str_graph.call_llm", return_value=MOCK_NARRATIVE),
            patch(
                "graph.str_graph.screen_entities_async",
                new=AsyncMock(return_value=MOCK_SANCTIONS_RESPONSE_CLEAN),
            ),
        ):
            final_state = await run_str_graph(_make_request_dict())

        entities = [Entity(**e) for e in final_state["extracted_entities"]]
        assert _compute_sanctions_status(entities) == "all_screened"

    async def test_llm_failure_does_not_crash_pipeline(self):
        """If LLM returns None, pipeline completes with error notes."""
        with (
            patch("graph.str_graph.call_llm_structured", return_value=None),
            patch("graph.str_graph.call_llm", return_value=None),
            patch(
                "graph.str_graph.screen_entities_async",
                new=AsyncMock(return_value={}),
            ),
        ):
            final_state = await run_str_graph(_make_request_dict())

        assert isinstance(final_state, dict)
        assert final_state.get("errors")


# ---------------------------------------------------------------------------
# Live integration test -- requires ANTHROPIC_API_KEY (skipped if not set)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not __import__("os").environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set -- skipping live LLM test",
)
class TestLiveIntegration:
    async def test_demo_scenario_live(self):
        """Full pipeline with real Claude API and demo scenario."""
        with patch(
            "graph.str_graph.screen_entities_async",
            new=AsyncMock(return_value=MOCK_SANCTIONS_RESPONSE_CLEAN),
        ):
            final_state = await run_str_graph(_make_request_dict())

        assert final_state["risk_level"] == EXPECTED_RISK_LEVEL
        assert final_state["confidence"] >= 0.6
        assert len(final_state["risk_indicators"]) >= EXPECTED_RISK_INDICATORS_MIN
        assert len(final_state["extracted_entities"]) >= EXPECTED_ENTITY_COUNT

        xml = final_state["goaml_xml"]
        is_valid, errors = validate_str_xml(xml)
        assert is_valid, f"XML invalid: {errors}"

        assert len(final_state["narrative_fr"]) >= 200
        assert not final_state.get("errors")
