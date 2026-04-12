"""Tests for tools/goaml_tool.py"""

import pytest
from datetime import datetime
from tools.goaml_tool import build_str_xml, validate_str_xml


SAMPLE_TRANSACTION = {
    "transaction_id": "TX-001",
    "date": datetime(2026, 3, 15),
    "amount": 850000.0,
    "currency": "TND",
    "transaction_type": "virement",
    "sender": {
        "name": "Immobiliere Carthage SARL",
        "entity_type": "company",
        "id_number": "B123456789",
        "country": "TN",
        "is_pep": False,
        "sanctions_hit": False,
    },
    "receiver": {
        "name": "Gulf Properties FZE",
        "entity_type": "company",
        "country": "AE",
        "is_pep": False,
        "sanctions_hit": False,
    },
    "intermediaries": [
        {
            "name": "Mediterranean Holdings Ltd",
            "entity_type": "company",
            "country": "MT",
            "is_pep": False,
            "sanctions_hit": False,
        },
        {
            "name": "Atlantic Capital SA",
            "entity_type": "company",
            "country": "LU",
            "is_pep": False,
            "sanctions_hit": False,
        },
    ],
}

SAMPLE_NARRATIVE = (
    "La societe Immobiliere Carthage SARL a effectue un virement de 850 000 TND "
    "vers Gulf Properties FZE aux Emirats Arabes Unis via deux intermediaires."
)


def test_build_str_xml_returns_string():
    xml = build_str_xml(SAMPLE_TRANSACTION, SAMPLE_NARRATIVE, "CASE-001")
    assert isinstance(xml, str)
    assert len(xml) > 0


def test_build_str_xml_starts_with_declaration():
    xml = build_str_xml(SAMPLE_TRANSACTION, SAMPLE_NARRATIVE, "CASE-001")
    assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?>')


def test_build_str_xml_contains_required_fields():
    xml = build_str_xml(SAMPLE_TRANSACTION, SAMPLE_NARRATIVE, "CASE-001")
    assert "<report_code>STR</report_code>" in xml
    assert "<submission_code>E</submission_code>" in xml
    assert "<entity_reference>CASE-001</entity_reference>" in xml
    assert "<currency_code_local>TND</currency_code_local>" in xml
    assert "850000.0" in xml
    assert "2026-03-15" in xml


def test_build_str_xml_contains_entities():
    xml = build_str_xml(SAMPLE_TRANSACTION, SAMPLE_NARRATIVE, "CASE-001")
    assert "Immobiliere Carthage SARL" in xml
    assert "Gulf Properties FZE" in xml
    assert "Mediterranean Holdings Ltd" in xml
    assert "Atlantic Capital SA" in xml


def test_build_str_xml_contains_narrative():
    xml = build_str_xml(SAMPLE_TRANSACTION, SAMPLE_NARRATIVE, "CASE-001")
    assert SAMPLE_NARRATIVE in xml


def test_validate_str_xml_valid():
    xml = build_str_xml(SAMPLE_TRANSACTION, SAMPLE_NARRATIVE, "CASE-001")
    is_valid, errors = validate_str_xml(xml)
    assert is_valid, f"Validation errors: {errors}"
    assert errors == []


def test_validate_str_xml_missing_narrative():
    xml = build_str_xml(SAMPLE_TRANSACTION, "", "CASE-001")
    is_valid, errors = validate_str_xml(xml)
    assert not is_valid
    assert any("narrative" in e.lower() for e in errors)


def test_validate_str_xml_bad_xml():
    is_valid, errors = validate_str_xml("not xml at all")
    assert not is_valid
    assert any("parse" in e.lower() for e in errors)


def test_intermediaries_in_xml():
    xml = build_str_xml(SAMPLE_TRANSACTION, SAMPLE_NARRATIVE, "CASE-001")
    assert xml.count("<t_intermediary") == 2


def test_country_codes_in_xml():
    xml = build_str_xml(SAMPLE_TRANSACTION, SAMPLE_NARRATIVE, "CASE-001")
    assert "<country>AE</country>" in xml
    assert "<country>MT</country>" in xml
    assert "<country>LU</country>" in xml
