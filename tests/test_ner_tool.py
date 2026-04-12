"""Tests for tools/ner_tool.py"""

import json
import pytest
from datetime import datetime
from tools.ner_tool import (
    parse_entity,
    parse_transaction,
    extract_entities_from_llm_response,
    apply_sanctions_to_entities,
    _normalize_country,
    _parse_amount,
    _parse_date,
    _clean_json_string,
)
from models.schemas import Entity, TransactionType


CASE_ID = "TEST-NER-001"

SAMPLE_LLM_JSON = json.dumps({
    "entities": [
        {"name": "Immobiliere Carthage SARL", "entity_type": "company", "id_number": "B123456789", "country": "TN"},
        {"name": "Gulf Properties FZE", "entity_type": "company", "country": "AE"},
        {"name": "Mediterranean Holdings Ltd", "entity_type": "company", "country": "MT"},
        {"name": "Atlantic Capital SA", "entity_type": "company", "country": "LU"},
    ],
    "transaction": {
        "transaction_id": "TX-TEST-001",
        "date": "2026-03-15",
        "amount": 850000,
        "currency": "TND",
        "transaction_type": "virement",
        "sender": {"name": "Immobiliere Carthage SARL", "entity_type": "company", "country": "TN"},
        "receiver": {"name": "Gulf Properties FZE", "entity_type": "company", "country": "AE"},
        "intermediaries": [
            {"name": "Mediterranean Holdings Ltd", "entity_type": "company", "country": "MT"},
            {"name": "Atlantic Capital SA", "entity_type": "company", "country": "LU"},
        ],
        "red_flags": ["high_risk_jurisdiction", "multiple_intermediaries"],
    },
    "initial_red_flags": [
        "Transaction vers une juridiction a haut risque",
        "Recours a plusieurs intermediaires",
    ],
})


def test_parse_entity_company():
    raw = {"name": "Gulf Properties FZE", "entity_type": "company", "country": "AE"}
    entity = parse_entity(raw)
    assert entity.name == "Gulf Properties FZE"
    assert entity.entity_type == "company"
    assert entity.country == "AE"
    assert entity.is_pep is False
    assert entity.sanctions_hit is False


def test_parse_entity_person():
    raw = {"name": "Mohamed Ben Ali", "entity_type": "person", "is_pep": True}
    entity = parse_entity(raw)
    assert entity.entity_type == "person"
    assert entity.is_pep is True


def test_parse_transaction_basic():
    raw = {
        "transaction_id": "TX-001",
        "date": "2026-03-15",
        "amount": 850000,
        "currency": "TND",
        "transaction_type": "virement",
        "sender": {"name": "Carthage SARL", "entity_type": "company", "country": "TN"},
        "receiver": {"name": "Gulf Properties", "entity_type": "company", "country": "AE"},
        "intermediaries": [],
    }
    tx = parse_transaction(raw, [])
    assert tx is not None
    assert tx.amount == 850000.0
    assert tx.currency == "TND"
    assert tx.transaction_type == TransactionType.WIRE
    assert tx.sender.name == "Carthage SARL"
    assert tx.receiver.country == "AE"


def test_parse_transaction_with_intermediaries():
    raw = {
        "date": "2026-03-15",
        "amount": 850000,
        "currency": "TND",
        "transaction_type": "virement",
        "sender": {"name": "A", "entity_type": "company"},
        "receiver": {"name": "B", "entity_type": "company"},
        "intermediaries": [
            {"name": "Inter1", "entity_type": "company", "country": "MT"},
            {"name": "Inter2", "entity_type": "company", "country": "LU"},
        ],
    }
    tx = parse_transaction(raw, [])
    assert tx is not None
    assert len(tx.intermediaries) == 2


def test_extract_entities_from_llm_response_full():
    entities, transaction, red_flags = extract_entities_from_llm_response(
        SAMPLE_LLM_JSON, CASE_ID
    )
    assert len(entities) == 4
    assert transaction is not None
    assert transaction.amount == 850000.0
    assert len(transaction.intermediaries) == 2
    assert len(red_flags) == 2


def test_extract_entities_from_llm_response_markdown_fence():
    wrapped = "```json\n" + SAMPLE_LLM_JSON + "\n```"
    entities, transaction, red_flags = extract_entities_from_llm_response(
        wrapped, CASE_ID
    )
    assert len(entities) == 4


def test_extract_entities_from_llm_response_bad_json():
    entities, transaction, red_flags = extract_entities_from_llm_response(
        "this is not json", CASE_ID
    )
    assert entities == []
    assert transaction is None
    assert red_flags == []


def test_apply_sanctions_to_entities():
    entities = [
        Entity(name="Gulf Properties FZE", entity_type="company"),
        Entity(name="Carthage SARL", entity_type="company"),
    ]
    sanctions = {
        "Gulf Properties FZE": {"hit": True, "detail": "OFAC SDN match"},
        "Carthage SARL": {"hit": False, "detail": None},
    }
    updated = apply_sanctions_to_entities(entities, sanctions)
    assert updated[0].sanctions_hit is True
    assert updated[0].sanctions_detail == "OFAC SDN match"
    assert updated[1].sanctions_hit is False


def test_normalize_country_known_names():
    assert _normalize_country("Emirats Arabes Unis") == "AE"
    assert _normalize_country("MALTE") == "MT"
    assert _normalize_country("luxembourg") == "LU"
    assert _normalize_country("TN") == "TN"
    assert _normalize_country(None) is None


def test_parse_amount_various_formats():
    assert _parse_amount(850000) == 850000.0
    assert _parse_amount("850 000") == 850000.0
    assert _parse_amount("850,000") == 850000.0
    assert _parse_amount("850000 TND") == 850000.0
    assert _parse_amount("invalid") == 0.0


def test_parse_date_formats():
    d1 = _parse_date("2026-03-15")
    assert d1.year == 2026 and d1.month == 3 and d1.day == 15

    d2 = _parse_date("15/03/2026")
    assert d2.year == 2026 and d2.month == 3 and d2.day == 15


def test_clean_json_string_strips_fence():
    raw = '```json\n{"key": "value"}\n```'
    assert _clean_json_string(raw) == '{"key": "value"}'

    raw2 = '{"key": "value"}'
    assert _clean_json_string(raw2) == '{"key": "value"}'
