"""goAML XML builder and validator -- no LLM, no external XML libs."""

import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Optional


def build_str_xml(
    transaction: dict,
    narrative: str,
    case_ref: str,
    reporting_entity_id: str = "WARAKA_BANK",
    branch_id: str = "HQ",
) -> str:
    """Build goAML-compatible STR-T XML from structured data.

    Args:
        transaction: Transaction dict (matches Transaction Pydantic model).
        narrative: French compliance narrative text.
        case_ref: Bank internal case reference.
        reporting_entity_id: goAML reporting entity identifier.
        branch_id: Branch identifier.

    Returns:
        UTF-8 encoded goAML STR XML string.
    """
    report = ET.Element("report")

    ET.SubElement(report, "rentity_id").text = reporting_entity_id
    ET.SubElement(report, "rentity_branch").text = branch_id
    ET.SubElement(report, "submission_code").text = "E"
    ET.SubElement(report, "report_code").text = "STR"
    ET.SubElement(report, "entity_reference").text = case_ref
    ET.SubElement(report, "fiu_ref_number")
    ET.SubElement(report, "submission_date").text = datetime.utcnow().strftime(
        "%Y-%m-%d"
    )
    ET.SubElement(report, "currency_code_local").text = transaction.get(
        "currency", "TND"
    )

    reporting_person = ET.SubElement(report, "reporting_person")
    ET.SubElement(reporting_person, "role").text = "R"
    ET.SubElement(reporting_person, "occupation").text = "COMPLIANCE_OFFICER"

    location = ET.SubElement(report, "location")
    ET.SubElement(location, "address_type").text = "B"
    ET.SubElement(location, "country").text = "TN"

    tx_elem = ET.SubElement(report, "transaction")
    ET.SubElement(tx_elem, "transactionnumber").text = transaction.get(
        "transaction_id", "TX-UNKNOWN"
    )
    ET.SubElement(tx_elem, "transaction_location").text = "TN"

    tx_date = transaction.get("date", "")
    if isinstance(tx_date, datetime):
        tx_date = tx_date.strftime("%Y-%m-%d")
    elif tx_date and "T" in str(tx_date):
        tx_date = str(tx_date)[:10]
    ET.SubElement(tx_elem, "date_transaction").text = str(tx_date)

    ET.SubElement(tx_elem, "teller")
    ET.SubElement(tx_elem, "authorized")
    ET.SubElement(tx_elem, "amount_local").text = str(transaction.get("amount", 0))

    sender = transaction.get("sender", {})
    from_elem = ET.SubElement(tx_elem, "t_from_my_client")
    _add_entity_xml(from_elem, sender, "from")

    receiver = transaction.get("receiver", {})
    to_elem = ET.SubElement(tx_elem, "t_to_my_client")
    _add_entity_xml(to_elem, receiver, "to")

    for idx, intermediary in enumerate(
        transaction.get("intermediaries", []), start=1
    ):
        inter_elem = ET.SubElement(tx_elem, "t_intermediary")
        inter_elem.set("sequence", str(idx))
        _add_entity_xml(inter_elem, intermediary, "intermediary")

    ET.SubElement(report, "narrative").text = narrative

    ET.indent(report, space="  ")
    xml_bytes = ET.tostring(report, encoding="unicode", xml_declaration=False)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_bytes


def _add_entity_xml(parent: ET.Element, entity: dict, role: str) -> None:
    """Add entity fields to a parent XML element."""
    entity_type = entity.get("entity_type", "company")
    name = entity.get("name", "")
    country = entity.get("country", "")
    id_number = entity.get("id_number", "")

    if entity_type == "person":
        ET.SubElement(parent, "first_name").text = name.split()[0] if name else ""
        ET.SubElement(parent, "last_name").text = (
            " ".join(name.split()[1:]) if len(name.split()) > 1 else ""
        )
        if id_number:
            ET.SubElement(parent, "id_number").text = id_number
    else:
        ET.SubElement(parent, "name").text = name
        if id_number:
            ET.SubElement(parent, "registration_number").text = id_number

    if country:
        ET.SubElement(parent, "country").text = country

    if entity.get("is_pep"):
        ET.SubElement(parent, "is_pep").text = "true"

    if entity.get("sanctions_hit"):
        ET.SubElement(parent, "sanctions_hit").text = "true"
        detail = entity.get("sanctions_detail", "")
        if detail:
            ET.SubElement(parent, "sanctions_detail").text = detail


def validate_str_xml(xml_string: str) -> tuple[bool, list[str]]:
    """Validate goAML STR XML structure.

    Returns:
        Tuple of (is_valid, list_of_errors).
    """
    errors: list[str] = []

    try:
        root = ET.fromstring(
            xml_string.replace('<?xml version="1.0" encoding="UTF-8"?>\n', "").strip()
        )
    except ET.ParseError as exc:
        return False, [f"XML parse error: {exc}"]

    required_top_level = [
        "rentity_id",
        "submission_code",
        "report_code",
        "entity_reference",
        "submission_date",
        "currency_code_local",
        "reporting_person",
        "transaction",
        "narrative",
    ]
    for field in required_top_level:
        if root.find(field) is None:
            errors.append(f"Missing required element: <{field}>")

    tx = root.find("transaction")
    if tx is not None:
        required_tx = ["transactionnumber", "date_transaction", "amount_local"]
        for field in required_tx:
            if tx.find(field) is None:
                errors.append(f"Missing required transaction element: <{field}>")

    report_code = root.findtext("report_code", "")
    if report_code != "STR":
        errors.append(f"report_code must be 'STR', got '{report_code}'")

    submission_code = root.findtext("submission_code", "")
    if submission_code != "E":
        errors.append(f"submission_code must be 'E', got '{submission_code}'")

    narrative = root.findtext("narrative", "")
    if not narrative or not narrative.strip():
        errors.append("narrative element must not be empty")

    return len(errors) == 0, errors
