"""Shared FATF high-risk jurisdiction lookup for banking and insurance modes.

Both graph/str_graph.py (banking mode R001) and graph/rules_insurance.py
(insurance mode's jurisdiction indicators) need the same country -> FATF
tier data. This module is the single place that loads config/fatf_lists.yaml
so the two modes never drift apart or duplicate the parsing logic.
"""

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import structlog
import yaml

logger = structlog.get_logger()

_FATF_LISTS_PATH = Path(__file__).resolve().parent.parent / "config" / "fatf_lists.yaml"
_FATF_STALE_AFTER_DAYS = 120


@dataclass(frozen=True)
class FATFCountryStatus:
    tier: str    # "countermeasures" | "enhanced_due_diligence" | "greylist"
    weight: float


def _load_fatf_data(path: Path = _FATF_LISTS_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    last_updated_str = data.get("last_updated")
    if last_updated_str:
        last_updated = datetime.strptime(last_updated_str, "%Y-%m-%d").date()
        age_days = (date.today() - last_updated).days
        if age_days > _FATF_STALE_AFTER_DAYS:
            logger.warning(
                "fatf_list_stale",
                last_updated=last_updated_str,
                age_days=age_days,
            )

    return data


def _load_fatf_country_statuses(path: Path = _FATF_LISTS_PATH) -> dict[str, FATFCountryStatus]:
    """Load the FATF blacklist/greylist config into a country -> (tier, weight) lookup.

    Higher-severity tiers are loaded first so a country listed in more than
    one tier keeps the status of its highest (most severe) tier.
    """
    data = _load_fatf_data(path)
    statuses: dict[str, FATFCountryStatus] = {}

    for tier_name, tier in data.get("blacklist", {}).items():
        tier_weight = tier["weight"]
        for country in tier.get("countries", []):
            statuses.setdefault(country, FATFCountryStatus(tier=tier_name, weight=tier_weight))

    greylist = data.get("greylist", {})
    grey_weight = greylist.get("weight", 0.0)
    for country in greylist.get("countries", []):
        statuses.setdefault(country, FATFCountryStatus(tier="greylist", weight=grey_weight))

    return statuses


FATF_COUNTRY_STATUS: dict[str, FATFCountryStatus] = _load_fatf_country_statuses()

FATF_COUNTRY_WEIGHTS: dict[str, float] = {
    country: status.weight for country, status in FATF_COUNTRY_STATUS.items()
}

FATF_COUNTRY_TIERS: dict[str, str] = {
    country: status.tier for country, status in FATF_COUNTRY_STATUS.items()
}
