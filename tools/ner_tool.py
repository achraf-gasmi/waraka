"""Entity extraction helper for French AML compliance text.

This module provides utilities to parse and validate the JSON output
produced by the LLM entity extraction node, coercing raw dicts into
validated Pydantic models.
"""

import json
import re
import structlog
from datetime import datetime
from typing import Optional

from models.schemas import Entity, Transaction, TransactionType

logger = structlog.get_logger()


def parse_entity(raw: dict) -> Entity:
    """Parse a raw entity dict from LLM output into an Entity model.

    Args:
        raw: Raw dict from LLM JSON output.

    Returns:
        Validated Entity Pydantic model.
    """
    return Entity(
        name=raw.get("name", ""),
        name_arabic=raw.get("name_arabic"),
        entity_type=raw.get("entity_type", "company"),
        id_number=raw.get("id_number"),
        nationality=raw.get("nationality"),
        country=_normalize_country(raw.get("country")),
        address=raw.get("address"),
        is_pep=bool(raw.get("is_pep", False)),
        sanctions_hit=False,
        sanctions_detail=None,
    )


def parse_transaction(raw: dict, entities: list[Entity]) -> Optional[Transaction]:
    """Parse a raw transaction dict from LLM output into a Transaction model.

    Args:
        raw: Raw transaction dict from LLM JSON output.
        entities: Already-parsed list of Entity models (for sender/receiver lookup).

    Returns:
        Validated Transaction model, or None if parsing fails.
    """
    try:
        sender_raw = raw.get("sender", {})
        receiver_raw = raw.get("receiver", {})
        intermediaries_raw = raw.get("intermediaries", [])

        sender = parse_entity(sender_raw) if sender_raw else _unknown_entity()
        receiver = parse_entity(receiver_raw) if receiver_raw else _unknown_entity()
        intermediaries = [parse_entity(i) for i in intermediaries_raw if i]

        tx_type_raw = raw.get("transaction_type", "autre").lower()
        tx_type = _normalize_tx_type(tx_type_raw)

        date_raw = raw.get("date", "")
        tx_date = _parse_date(date_raw)

        amount_raw = raw.get("amount", 0)
        amount = _parse_amount(amount_raw)

        tx_id = raw.get("transaction_id") or _generate_tx_id()

        return Transaction(
            transaction_id=tx_id,
            date=tx_date,
            amount=amount,
            currency=raw.get("currency", "TND").upper(),
            transaction_type=tx_type,
            sender=sender,
            receiver=receiver,
            intermediaries=intermediaries,
            description=raw.get("description"),
            red_flags=raw.get("red_flags", []),
            no_prior_relationship=bool(raw.get("no_prior_relationship", False)),
        )
    except Exception as exc:
        logger.error("transaction_parse_failed", error=str(exc))
        return None


def extract_entities_from_llm_response(
    llm_json: str, case_id: str
) -> tuple[list[Entity], Optional[Transaction], list[str]]:
    """Parse the full LLM JSON extraction response.

    Args:
        llm_json: Raw JSON string from the LLM.
        case_id: Case ID for structured logging.

    Returns:
        Tuple of (entities, transaction, initial_red_flags).
        On parse failure, returns ([], None, []).
    """
    log = logger.bind(case_id=case_id)

    cleaned = _clean_json_string(llm_json)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        log.error("llm_json_parse_failed", error=str(exc), raw=cleaned[:200])
        return [], None, []

    raw_entities: list[dict] = data.get("entities", [])
    raw_transaction: dict = data.get("transaction", {})
    red_flags: list[str] = data.get("initial_red_flags", [])

    entities = [parse_entity(e) for e in raw_entities if e.get("name")]

    transaction = parse_transaction(raw_transaction, entities) if raw_transaction else None

    log.info(
        "extraction_complete",
        entity_count=len(entities),
        has_transaction=transaction is not None,
        red_flag_count=len(red_flags),
    )

    return entities, transaction, red_flags


def extract_entities_from_structured_response(
    data: dict, case_id: str
) -> tuple[list[Entity], Optional[Transaction], list[str]]:
    """Parse the validated dict returned by call_llm_structured (tool_use).

    Unlike extract_entities_from_llm_response, this receives an already-parsed
    dict — no JSON decoding or fence-stripping needed.

    Returns:
        Tuple of (entities, transaction, initial_red_flags).
    """
    log = logger.bind(case_id=case_id)

    raw_entities: list[dict] = data.get("entities", [])
    raw_transaction: dict = data.get("transaction", {})
    red_flags: list[str] = data.get("initial_red_flags", [])

    entities = [parse_entity(e) for e in raw_entities if e.get("name")]
    transaction = parse_transaction(raw_transaction, entities) if raw_transaction else None

    log.info(
        "structured_extraction_complete",
        entity_count=len(entities),
        has_transaction=transaction is not None,
        red_flag_count=len(red_flags),
    )
    return entities, transaction, red_flags


def apply_sanctions_to_entities(
    entities: list[Entity],
    sanctions_results: dict[str, dict],
) -> list[Entity]:
    """Merge sanctions screening results back into entity models.

    Args:
        entities: List of Entity models.
        sanctions_results: Dict from screen_entities() keyed by entity name.

    Returns:
        Updated list of Entity models with sanctions_hit and sanctions_detail set.
    """
    updated: list[Entity] = []
    for entity in entities:
        result = sanctions_results.get(entity.name, {})
        updated.append(
            entity.model_copy(
                update={
                    "sanctions_hit": result.get("hit", False),
                    "sanctions_detail": result.get("detail"),
                }
            )
        )
    return updated


def _normalize_country(country: Optional[str]) -> Optional[str]:
    """Normalize country to ISO 3166-1 alpha-2 if possible."""
    if not country:
        return None
    country = country.strip().upper()
    # Common mappings from French/English country names
    COUNTRY_MAP = {
        "EMIRATS ARABES UNIS": "AE",
        "UNITED ARAB EMIRATES": "AE",
        "UAE": "AE",
        "MALTE": "MT",
        "MALTA": "MT",
        "LUXEMBOURG": "LU",
        "TUNISIE": "TN",
        "TUNISIA": "TN",
        "FRANCE": "FR",
        "MAROC": "MA",
        "MOROCCO": "MA",
        "ALGERIE": "DZ",
        "ALGERIA": "DZ",
        "IRAN": "IR",
        "SYRIE": "SY",
        "SYRIA": "SY",
        "LIBYE": "LY",
        "LIBYA": "LY",
        "SOUDAN": "SD",
        "SUDAN": "SD",
        "COREE DU NORD": "KP",
        "NORTH KOREA": "KP",
        "YEMEN": "YE",
        "VENEZUELA": "VE",
        "PANAMA": "PA",
    }
    if country in COUNTRY_MAP:
        return COUNTRY_MAP[country]
    # Already a 2-letter code
    if len(country) == 2 and country.isalpha():
        return country
    return country


def _normalize_tx_type(raw: str) -> TransactionType:
    """Map LLM transaction type string to TransactionType enum."""
    mapping = {
        "virement": TransactionType.WIRE,
        "wire": TransactionType.WIRE,
        "transfer": TransactionType.WIRE,
        "especes": TransactionType.CASH,
        "cash": TransactionType.CASH,
        "cheque": TransactionType.CHEQUE,
        "check": TransactionType.CHEQUE,
        "crypto": TransactionType.CRYPTO,
        "cryptocurrency": TransactionType.CRYPTO,
    }
    return mapping.get(raw.lower(), TransactionType.OTHER)


def _parse_date(date_raw: str) -> datetime:
    """Parse date string from LLM output."""
    if not date_raw:
        return datetime.utcnow()

    formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(str(date_raw)[:19], fmt)
        except ValueError:
            continue

    # Fallback: try extracting digits
    digits = re.sub(r"[^\d]", "", str(date_raw))
    if len(digits) >= 8:
        try:
            return datetime.strptime(digits[:8], "%Y%m%d")
        except ValueError:
            pass

    return datetime.utcnow()


def _parse_amount(amount_raw) -> float:
    """Parse amount from LLM output (handles strings like '850 000')."""
    if isinstance(amount_raw, (int, float)):
        return float(amount_raw)
    # Remove spaces and commas used as thousand separators
    cleaned = re.sub(r"[\s,]", "", str(amount_raw))
    # Remove currency suffixes
    cleaned = re.sub(r"[A-Za-z]+$", "", cleaned)
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _unknown_entity() -> Entity:
    return Entity(name="UNKNOWN", entity_type="company")


def _generate_tx_id() -> str:
    from datetime import timezone
    ts = int(datetime.now(timezone.utc).timestamp())
    return f"TX-{ts}"


def _clean_json_string(raw: str) -> str:
    """Strip markdown code fences if LLM wrapped JSON in them."""
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        # Remove first and last fence lines
        inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        raw = "\n".join(inner)
    return raw
