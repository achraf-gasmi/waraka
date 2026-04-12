"""Shared fixtures and mock data for Waraka tests."""

import pytest

MOCK_ANALYST_INPUT: str = """
Notre client, la societe Immobiliere Carthage SARL (RC: B123456789, Tunis),
a effectue le 15 mars 2026 un virement de 850 000 TND vers une societe
denommee Gulf Properties FZE, domiciliee aux Emirats Arabes Unis (Abu Dhabi),
via deux societes intermediaires : une a Malte (Mediterranean Holdings Ltd)
et une au Luxembourg (Atlantic Capital SA). Le client affirme qu'il s'agit
d'un investissement immobilier, mais aucun contrat n'a ete fourni. Aucune
relation commerciale anterieure avec les beneficiaires n'existe dans nos
systemes. Le profil risque du client est classe moyen.
"""

EXPECTED_RISK_LEVEL: str = "critical"
EXPECTED_RISK_INDICATORS_MIN: int = 3
EXPECTED_ENTITY_COUNT: int = 4

MOCK_SANCTIONS_RESPONSE_CLEAN: dict = {
    "Immobiliere Carthage SARL": {"hit": False, "detail": None},
    "Gulf Properties FZE": {"hit": False, "detail": None},
    "Mediterranean Holdings Ltd": {"hit": False, "detail": None},
    "Atlantic Capital SA": {"hit": False, "detail": None},
}

MOCK_SANCTIONS_RESPONSE_HIT: dict = {
    "Gulf Properties FZE": {
        "hit": True,
        "detail": "Listed on OFAC SDN list -- designation date 2024-03-15",
    },
}
