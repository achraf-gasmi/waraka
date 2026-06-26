"""LangGraph StateGraph for STR drafting -- 5 nodes, linear, no cycles."""

import operator
from datetime import datetime
from typing import Annotated, TypedDict, Optional

import structlog
from langgraph.graph import StateGraph, END

from agents.str_agent import (
    ENTITY_EXTRACTION_SYSTEM,
    ENTITY_EXTRACTION_USER,
    NARRATIVE_GENERATION_SYSTEM,
    NARRATIVE_GENERATION_USER,
    call_llm,
    call_llm_structured,
)
from models.schemas import Entity, Transaction, RiskLevel
from tools.goaml_tool import build_str_xml
from tools.ner_tool import (
    extract_entities_from_structured_response,
    apply_sanctions_to_entities,
)
from tools.sanctions_tool import screen_entities_async

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Risk rules -- pure rule-based scoring, no ML in v1
# ---------------------------------------------------------------------------

HIGH_RISK_COUNTRIES: list[str] = [
    "AE", "IR", "KP", "SY", "YE", "LY", "SD", "AF",   # FATF high-risk
    "VE", "MM", "NI", "PA", "UG",                        # FATF grey list
]

RISK_RULES: list[dict] = [
    {
        "id": "R001",
        "name": "Juridiction a haut risque",
        "weight": 0.3,
        "label": "Transaction vers une juridiction a haut risque selon le GAFI",
    },
    {
        "id": "R002",
        "name": "Montant eleve non habituel",
        "weight": 0.2,
        "label": "Montant superieur a 500 000 TND sans justification economique apparente",
    },
    {
        "id": "R003",
        "name": "Intermediaires multiples",
        "weight": 0.25,
        "label": "Recours a plusieurs intermediaires sans justification commerciale",
    },
    {
        "id": "R004",
        "name": "Hit sanctions",
        "weight": 0.4,
        "label": "Entite figurant sur une liste de sanctions internationale",
    },
    {
        "id": "R005",
        "name": "PPE implique",
        "weight": 0.3,
        "label": "Personne politiquement exposee impliquee dans la transaction",
    },
    {
        "id": "R006",
        "name": "Absence de relation anterieure",
        "weight": 0.15,
        "label": "Aucune relation commerciale anterieure avec le beneficiaire",
    },
    {
        "id": "R007",
        "name": "Structuration sous le seuil",
        "weight": 0.35,
        "label": "Paiements fractionnes sous le seuil de declaration (structuration / smurfing)",
    },
    {
        "id": "R008",
        "name": "Transactions multiples meme beneficiaire",
        "weight": 0.20,
        "label": "Transactions multiples sur une courte periode vers le meme beneficiaire",
    },
    {
        "id": "R009",
        "name": "Absence de justification commerciale",
        "weight": 0.20,
        "label": "Absence de facture, contrat ou justification commerciale",
    },
    {
        "id": "R010",
        "name": "Destination a controles LBA/FT faibles",
        "weight": 0.25,
        "label": "Juridiction destinataire reconnue pour des controles LBA/FT faibles",
    },
    {
        "id": "R011",
        "name": "Incoherence d'activite",
        "weight": 0.20,
        "label": "Incoherence entre l'activite commerciale declaree et la transaction observee",
    },
]


# ---------------------------------------------------------------------------
# LangGraph state
# Annotated[list, operator.add] fields accumulate across nodes (append
# semantics). All other fields use replace semantics (last write wins).
# ---------------------------------------------------------------------------

class STRState(TypedDict):
    request: dict
    extracted_entities: list
    extracted_transaction: dict
    sanctions_results: dict
    risk_indicators: list[str]
    risk_level: str
    confidence: float
    narrative_fr: str
    goaml_xml: str
    analyst_notes: Annotated[list[str], operator.add]
    errors: Annotated[list[str], operator.add]


# ---------------------------------------------------------------------------
# Node 1: extract_entities
# ---------------------------------------------------------------------------

def extract_entities_node(state: STRState) -> dict:
    """Extract entities and transaction from analyst free text via Claude tool_use."""
    request = state["request"]
    case_id = request.get("case_id", "unknown")
    log = logger.bind(case_id=case_id, node="extract_entities")
    log.info("node_start")

    user_prompt = ENTITY_EXTRACTION_USER.format(
        analyst_input=request.get("analyst_input", ""),
        reporting_institution=request.get("reporting_institution", ""),
    )

    data = call_llm_structured(
        system=ENTITY_EXTRACTION_SYSTEM,
        user=user_prompt,
        case_id=case_id,
    )

    if not data:
        log.error("extraction_llm_failed")
        return {
            "errors": ["LLM extraction failed"],
            "extracted_entities": [],
            "extracted_transaction": {},
        }

    entities, transaction, initial_red_flags = extract_entities_from_structured_response(
        data, case_id
    )

    result: dict = {
        "extracted_entities": [e.model_dump() for e in entities],
        "extracted_transaction": (
            transaction.model_dump(mode="json") if transaction else {}
        ),
    }
    if initial_red_flags:
        result["analyst_notes"] = [f"Red flag detecte: {f}" for f in initial_red_flags]

    log.info("node_complete", entity_count=len(entities), has_transaction=transaction is not None)
    return result


# ---------------------------------------------------------------------------
# Node 2: screen_sanctions
# ---------------------------------------------------------------------------

async def screen_sanctions_node(state: STRState) -> dict:
    """Screen all extracted entities against OpenSanctions in parallel."""
    case_id = state["request"].get("case_id", "unknown")
    log = logger.bind(case_id=case_id, node="screen_sanctions")
    log.info("node_start")

    entities_raw: list[dict] = state.get("extracted_entities", [])
    entity_names = [e["name"] for e in entities_raw if e.get("name")]

    if not entity_names:
        log.warning("no_entities_to_screen")
        return {"sanctions_results": {}}

    try:
        results = await screen_entities_async(entity_names, case_id)

        entities = [Entity(**e) for e in entities_raw]
        updated = apply_sanctions_to_entities(entities, results)

        hits = [name for name, r in results.items() if r.get("hit")]
        log.info("node_complete", screened=len(entity_names), hits=len(hits))
        if hits:
            log.warning("sanctions_hits_found", hits=hits)

        partial: dict = {
            "sanctions_results": results,
            "extracted_entities": [e.model_dump() for e in updated],
        }
        if hits:
            partial["analyst_notes"] = [f"SANCTIONS HIT: {name}" for name in hits]
        return partial

    except Exception as exc:
        log.error("sanctions_screening_failed", error=str(exc))
        return {
            "sanctions_results": {},
            "analyst_notes": ["Verification sanctions echouee -- verifier manuellement"],
        }


# ---------------------------------------------------------------------------
# Node 3: assess_risk
# ---------------------------------------------------------------------------

def assess_risk_node(state: STRState) -> dict:
    """Apply rule-based risk scoring to produce risk indicators and confidence."""
    case_id = state["request"].get("case_id", "unknown")
    log = logger.bind(case_id=case_id, node="assess_risk")
    log.info("node_start")

    tx: dict = state.get("extracted_transaction", {})
    sanctions: dict = state.get("sanctions_results", {})

    matched_labels: list[str] = []
    total_weight: float = 0.0

    # R001 -- high-risk jurisdiction
    receiver_country = (tx.get("receiver") or {}).get("country", "")
    if receiver_country in HIGH_RISK_COUNTRIES:
        matched_labels.append(RISK_RULES[0]["label"])
        total_weight += RISK_RULES[0]["weight"]

    # R002 -- large amount
    amount = tx.get("amount", 0) or 0
    if float(amount) > 500_000:
        matched_labels.append(RISK_RULES[1]["label"])
        total_weight += RISK_RULES[1]["weight"]

    # R003 -- multiple intermediaries
    intermediaries = tx.get("intermediaries", []) or []
    if len(intermediaries) >= 2:
        matched_labels.append(RISK_RULES[2]["label"])
        total_weight += RISK_RULES[2]["weight"]

    # R004 -- sanctions hit
    if any(v.get("hit") for v in sanctions.values()):
        matched_labels.append(RISK_RULES[3]["label"])
        total_weight += RISK_RULES[3]["weight"]

    # R005 -- PEP
    sender = tx.get("sender") or {}
    receiver = tx.get("receiver") or {}
    if sender.get("is_pep") or receiver.get("is_pep"):
        matched_labels.append(RISK_RULES[4]["label"])
        total_weight += RISK_RULES[4]["weight"]

    # R006 -- no prior relationship
    if tx.get("no_prior_relationship"):
        matched_labels.append(RISK_RULES[5]["label"])
        total_weight += RISK_RULES[5]["weight"]

    # R007 -- structuring below reporting threshold (smurfing)
    if tx.get("structuring_below_threshold"):
        matched_labels.append(RISK_RULES[6]["label"])
        total_weight += RISK_RULES[6]["weight"]

    # R008 -- multiple transactions to the same beneficiary
    if tx.get("multiple_transactions_same_beneficiary"):
        matched_labels.append(RISK_RULES[7]["label"])
        total_weight += RISK_RULES[7]["weight"]

    # R009 -- no invoice / contract / commercial justification
    if tx.get("no_commercial_justification"):
        matched_labels.append(RISK_RULES[8]["label"])
        total_weight += RISK_RULES[8]["weight"]

    # R010 -- destination known for weak AML/CFT controls
    if tx.get("weak_aml_destination"):
        matched_labels.append(RISK_RULES[9]["label"])
        total_weight += RISK_RULES[9]["weight"]

    # R011 -- declared activity inconsistent with observed transaction
    if tx.get("activity_inconsistency"):
        matched_labels.append(RISK_RULES[10]["label"])
        total_weight += RISK_RULES[10]["weight"]

    confidence = min(total_weight, 1.0)

    if confidence >= 0.6:
        risk_level = RiskLevel.CRITICAL.value
    elif confidence >= 0.4:
        risk_level = RiskLevel.HIGH.value
    elif confidence >= 0.2:
        risk_level = RiskLevel.MEDIUM.value
    else:
        risk_level = RiskLevel.LOW.value

    log.info(
        "node_complete",
        risk_level=risk_level,
        confidence=confidence,
        indicator_count=len(matched_labels),
    )
    return {
        "risk_indicators": matched_labels,
        "confidence": confidence,
        "risk_level": risk_level,
    }


# ---------------------------------------------------------------------------
# Node 4: generate_narrative
# ---------------------------------------------------------------------------

def _summarize_entities(entities: list[dict]) -> str:
    lines = []
    for e in entities:
        pep = " [PPE]" if e.get("is_pep") else ""
        sanc = " [SANCTIONS HIT]" if e.get("sanctions_hit") else ""
        lines.append(
            f"- {e.get('name', 'N/A')} ({e.get('entity_type', 'N/A')}, "
            f"{e.get('country', 'N/A')}){pep}{sanc}"
        )
    return "\n".join(lines) if lines else "Aucune entite extraite"


def _summarize_transaction(tx: dict) -> str:
    if not tx:
        return "Aucune transaction extraite"
    lines = [
        f"Type: {tx.get('transaction_type', 'N/A')}",
        f"Montant: {tx.get('amount', 0)} {tx.get('currency', 'TND')}",
        f"Date: {tx.get('date', 'N/A')}",
        f"Emetteur: {(tx.get('sender') or {}).get('name', 'N/A')} ({(tx.get('sender') or {}).get('country', 'N/A')})",
        f"Beneficiaire: {(tx.get('receiver') or {}).get('name', 'N/A')} ({(tx.get('receiver') or {}).get('country', 'N/A')})",
    ]
    intermediaries = tx.get("intermediaries", []) or []
    if intermediaries:
        names = ", ".join(i.get("name", "N/A") for i in intermediaries)
        lines.append(f"Intermediaires: {names}")
    return "\n".join(lines)


def _summarize_sanctions(sanctions: dict) -> str:
    if not sanctions:
        return "Aucune verification effectuee"
    lines = []
    for name, result in sanctions.items():
        status = "HIT" if result.get("hit") else "Propre"
        detail = f" -- {result['detail']}" if result.get("detail") else ""
        lines.append(f"- {name}: {status}{detail}")
    return "\n".join(lines)


def generate_narrative_node(state: STRState) -> dict:
    """Generate a formal French compliance narrative via Claude."""
    request = state["request"]
    case_id = request.get("case_id", "unknown")
    log = logger.bind(case_id=case_id, node="generate_narrative")
    log.info("node_start")

    user_prompt = NARRATIVE_GENERATION_USER.format(
        entities_summary=_summarize_entities(state.get("extracted_entities", [])),
        transaction_summary=_summarize_transaction(state.get("extracted_transaction", {})),
        risk_indicators="\n".join(
            f"- {r}" for r in state.get("risk_indicators", [])
        ) or "Aucun indicateur identifie",
        sanctions_summary=_summarize_sanctions(state.get("sanctions_results", {})),
        reporting_institution=request.get("reporting_institution", "N/A"),
        declaration_date=datetime.utcnow().strftime("%d/%m/%Y"),
    )

    narrative = call_llm(
        system=NARRATIVE_GENERATION_SYSTEM,
        user=user_prompt,
        case_id=case_id,
    )

    if not narrative:
        log.error("narrative_llm_failed")
        return {
            "narrative_fr": "ERREUR: La generation du recit a echoue. Veuillez rediger manuellement.",
            "analyst_notes": ["Recit non genere -- revision manuelle requise"],
        }

    log.info("node_complete", narrative_length=len(narrative))
    return {"narrative_fr": narrative}


# ---------------------------------------------------------------------------
# Node 5: build_goaml_xml
# ---------------------------------------------------------------------------

def build_goaml_xml_node(state: STRState) -> dict:
    """Build valid goAML STR-T XML from structured state."""
    request = state["request"]
    case_id = request.get("case_id", "unknown")
    log = logger.bind(case_id=case_id, node="build_goaml_xml")
    log.info("node_start")

    case_ref = request.get("case_reference") or case_id

    try:
        xml = build_str_xml(
            transaction=state.get("extracted_transaction", {}),
            narrative=state.get("narrative_fr", ""),
            case_ref=case_ref,
            reporting_entity_id=request.get("reporting_institution", "WARAKA_BANK"),
        )
        log.info("node_complete", xml_length=len(xml))
        return {"goaml_xml": xml}
    except Exception as exc:
        log.error("xml_build_failed", error=str(exc))
        return {
            "goaml_xml": "",
            "analyst_notes": [f"Construction XML echouee: {exc}"],
        }


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------

_graph_builder = StateGraph(STRState)

_graph_builder.add_node("extract_entities", extract_entities_node)
_graph_builder.add_node("screen_sanctions", screen_sanctions_node)
_graph_builder.add_node("assess_risk", assess_risk_node)
_graph_builder.add_node("generate_narrative", generate_narrative_node)
_graph_builder.add_node("build_goaml_xml", build_goaml_xml_node)

_graph_builder.set_entry_point("extract_entities")
_graph_builder.add_edge("extract_entities", "screen_sanctions")
_graph_builder.add_edge("screen_sanctions", "assess_risk")
_graph_builder.add_edge("assess_risk", "generate_narrative")
_graph_builder.add_edge("generate_narrative", "build_goaml_xml")
_graph_builder.add_edge("build_goaml_xml", END)

str_graph = _graph_builder.compile()


async def run_str_graph(request_dict: dict) -> STRState:
    """Run the full STR drafting pipeline.

    Args:
        request_dict: STRDraftRequest as dict, must include 'case_id'.

    Returns:
        Final STRState after all 5 nodes have executed.
    """
    initial_state: STRState = {
        "request": request_dict,
        "extracted_entities": [],
        "extracted_transaction": {},
        "sanctions_results": {},
        "risk_indicators": [],
        "risk_level": RiskLevel.LOW.value,
        "confidence": 0.0,
        "narrative_fr": "",
        "goaml_xml": "",
        "analyst_notes": [],
        "errors": [],
    }
    return await str_graph.ainvoke(initial_state)
