"""Insurance-mode extraction prompts and parsing for Waraka.

Mirrors the style of agents/str_agent.py (banking mode) but targets
InsuranceCase instead of Transaction. The boolean flag list embedded in
INSURANCE_EXTRACTION_SYSTEM is generated from graph.rules_insurance so the
prompt and the scoring registry never drift apart.
"""

import structlog
from typing import Optional

from agents.str_agent import _ENTITY_SCHEMA
from graph.rules_insurance import LLM_EXTRACTED_TRIGGERS, RULES_BY_TRIGGER
from models.schemas import Entity
from models.schemas_insurance import (
    InsuranceCase,
    InsuranceProductType,
    OperationType,
    PaymentMethod,
    ProductRiskClass,
)
from tools.ner_tool import parse_entity, _parse_amount, _parse_date

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Flag definitions -- generated from the rule registry so the prompt and the
# scoring registry never drift apart.
#
# Only llm_extracted=True rules are surfaced here. The jurisdiction_* flags
# (rule.llm_extracted=False) are deliberately excluded: FATF status is a
# fact to look up, not something to ask an LLM to judge from its training
# data (see rules_insurance.compute_jurisdiction_flags).
# ---------------------------------------------------------------------------


def _build_flag_definitions() -> str:
    return "\n".join(
        f"- {rule.trigger_field} : {rule.label_fr}"
        for rule in LLM_EXTRACTED_TRIGGERS.values()
    )


_FLAG_DEFINITIONS: str = _build_flag_definitions()


def _build_json_fallback_contract() -> str:
    flag_lines = ",\n".join(f'  "{trigger}": false' for trigger in LLM_EXTRACTED_TRIGGERS)
    return f"""{{
  "operation_type": "souscription | paiement_prime | avenant | avance_sur_contrat | rachat_partiel | rachat_total | indemnisation | transfert",
  "operation_date": "YYYY-MM-DD or null",
  "policy_reference": "string or null",
  "product_type": "assurance_vie | capitalisation | assurance_transport | assurance_automobile | assurance_sante | multirisque | autre",
  "product_risk_class": "eleve | moyen | faible",
  "sum_assured": number or null,
  "currency": "TND",
  "souscripteur": {{ ...entity fields... }},
  "assure": {{ ...entity fields... }} or null,
  "beneficiaires": [ ...entity list... ],
  "payeur": {{ ...entity fields... }} or null,
  "intermediaire": {{ ...entity fields... }} or null,
  "amount": number or null,
  "payment_method": "virement | especes | cheque | carte | autre or null",
  "description": "string or null",
  "red_flags": ["string"],
{flag_lines}
}}"""


_JSON_FALLBACK_CONTRACT: str = _build_json_fallback_contract()

_ENTITY_FORMAT_BLOCK: str = """{
  "name": "string",
  "name_arabic": "string or null",
  "entity_type": "person | company",
  "id_number": "string or null",
  "nationality": "ISO-2 or null",
  "country": "ISO-2 or country name or null",
  "address": "string or null",
  "is_pep": false
}"""

# ---------------------------------------------------------------------------
# Module-level prompt constants -- never constructed inside functions
# ---------------------------------------------------------------------------

INSURANCE_EXTRACTION_SYSTEM: str = (
    """
Tu es un expert en conformite assurance tunisienne specialise dans la lutte
contre le blanchiment d'argent (LBA) applique au secteur de l'assurance vie
et non-vie. Tu analyses des descriptions d'operations d'assurance suspectes
redigees par des analystes de conformite.

Ta tache est d'extraire de maniere structuree :
1. Les caracteristiques du contrat (type de produit, classe de risque du
   produit, capital assure, type d'operation, moyen de paiement)
2. Toutes les parties impliquees (souscripteur, assure, beneficiaires,
   payeur, intermediaire)
3. Les indicateurs de risque structurels ci-dessous

Pour chacun des indicateurs structurels suivants, renseigne le champ
booleen correspondant. Mets true uniquement si l'indicateur est
explicitement ou implicitement etabli par le texte de l'analyste ; sinon,
mets false.

"""
    + _FLAG_DEFINITIONS
    + """

Le souscripteur est obligatoire. L'assure, le payeur et l'intermediaire ne
doivent etre renseignes que s'ils sont distincts du souscripteur ou
explicitement mentionnes dans le texte. La liste des beneficiaires peut
etre vide.

Utilise l'outil extract_insurance_case pour retourner les donnees extraites.

Si l'outil n'est pas disponible, reponds UNIQUEMENT en JSON valide
respectant exactement ce format -- aucun texte avant ou apres le JSON,
aucune balise markdown :
"""
    + _JSON_FALLBACK_CONTRACT
    + """

Le format de chaque entite (souscripteur, assure, chaque beneficiaire,
payeur, intermediaire) est le suivant :
"""
    + _ENTITY_FORMAT_BLOCK
)

INSURANCE_EXTRACTION_USER: str = """
Analyse la description suivante et extrait le contrat, les parties et les
indicateurs de risque structurels.

Description de l'analyste :
{analyst_input}

Compagnie d'assurance declarante : {reporting_institution}

Extrait :
- Le type d'operation (souscription, paiement de prime, avenant, avance,
  rachat partiel ou total, indemnisation, transfert)
- Le produit souscrit et sa classe de risque
- Le capital assure et le montant de l'operation
- Le souscripteur, l'assure (si different du souscripteur), les
  beneficiaires, le payeur (si different du souscripteur) et
  l'intermediaire eventuel
- Tout indicateur de risque structurel present dans le texte, en
  particulier concernant l'origine des fonds, le comportement du client,
  les beneficiaires et la coherence entre le profil du client et
  l'operation
"""

# ---------------------------------------------------------------------------
# Tool schema for structured extraction (Anthropic tool_use)
# ---------------------------------------------------------------------------

INSURANCE_EXTRACTION_TOOL: dict = {
    "name": "extract_insurance_case",
    "description": (
        "Extrait le contrat, les parties et les indicateurs de risque "
        "d'une description d'operation d'assurance suspecte AML."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "operation_type": {
                "type": "string",
                "enum": [e.value for e in OperationType],
            },
            "operation_date": {
                "type": ["string", "null"],
                "description": "Format YYYY-MM-DD",
            },
            "policy_reference": {"type": ["string", "null"]},
            "product_type": {
                "type": "string",
                "enum": [e.value for e in InsuranceProductType],
            },
            "product_risk_class": {
                "type": "string",
                "enum": [e.value for e in ProductRiskClass],
            },
            "sum_assured": {"type": ["number", "null"]},
            "currency": {"type": "string", "default": "TND"},
            "souscripteur": _ENTITY_SCHEMA,
            "assure": _ENTITY_SCHEMA,
            "beneficiaires": {"type": "array", "items": _ENTITY_SCHEMA},
            "payeur": _ENTITY_SCHEMA,
            "intermediaire": _ENTITY_SCHEMA,
            "amount": {"type": ["number", "null"]},
            "payment_method": {
                "type": ["string", "null"],
                "enum": [e.value for e in PaymentMethod],
            },
            "description": {"type": ["string", "null"]},
            "red_flags": {"type": "array", "items": {"type": "string"}},
            **{trigger: {"type": "boolean"} for trigger in LLM_EXTRACTED_TRIGGERS},
        },
        "required": ["operation_type", "souscripteur"],
    },
}

# ---------------------------------------------------------------------------
# Parsing -- validated dict (tool_use or JSON fallback) -> InsuranceCase
# ---------------------------------------------------------------------------

_OPERATION_TYPE_MAP: dict = {e.value: e for e in OperationType}
_PRODUCT_TYPE_MAP: dict = {e.value: e for e in InsuranceProductType}
_RISK_CLASS_MAP: dict = {e.value: e for e in ProductRiskClass}
_PAYMENT_METHOD_MAP: dict = {e.value: e for e in PaymentMethod}


def _parse_optional_entity(raw: Optional[dict]) -> Optional[Entity]:
    return parse_entity(raw) if raw and raw.get("name") else None


def parse_insurance_case(data: dict, case_id: str) -> Optional[InsuranceCase]:
    """Parse the validated dict returned by call_llm_structured into an InsuranceCase.

    Args:
        data: Raw dict matching INSURANCE_EXTRACTION_TOOL's input_schema.
        case_id: Case ID for structured logging and the InsuranceCase itself.

    Returns:
        Validated InsuranceCase, or None on parse failure.
    """
    log = logger.bind(case_id=case_id)

    try:
        souscripteur_raw = data.get("souscripteur") or {}
        souscripteur = (
            parse_entity(souscripteur_raw)
            if souscripteur_raw.get("name")
            else Entity(name="UNKNOWN", entity_type="company")
        )

        operation_date_raw = data.get("operation_date")
        sum_assured_raw = data.get("sum_assured")
        amount_raw = data.get("amount")
        payment_method_raw = (data.get("payment_method") or "").lower()

        flags = {trigger: bool(data.get(trigger, False)) for trigger in RULES_BY_TRIGGER}

        case = InsuranceCase(
            case_id=case_id,
            operation_type=_OPERATION_TYPE_MAP.get(
                (data.get("operation_type") or "").lower(), OperationType.SOUSCRIPTION
            ),
            operation_date=_parse_date(operation_date_raw) if operation_date_raw else None,
            policy_reference=data.get("policy_reference"),
            product_type=_PRODUCT_TYPE_MAP.get(
                (data.get("product_type") or "").lower(), InsuranceProductType.AUTRE
            ),
            product_risk_class=_RISK_CLASS_MAP.get(
                (data.get("product_risk_class") or "").lower(), ProductRiskClass.FAIBLE
            ),
            sum_assured=_parse_amount(sum_assured_raw) if sum_assured_raw is not None else None,
            currency=(data.get("currency") or "TND").upper(),
            souscripteur=souscripteur,
            assure=_parse_optional_entity(data.get("assure")),
            beneficiaires=[parse_entity(b) for b in (data.get("beneficiaires") or []) if b],
            payeur=_parse_optional_entity(data.get("payeur")),
            intermediaire=_parse_optional_entity(data.get("intermediaire")),
            amount=_parse_amount(amount_raw) if amount_raw is not None else None,
            payment_method=_PAYMENT_METHOD_MAP.get(payment_method_raw),
            description=data.get("description"),
            red_flags=data.get("red_flags", []) or [],
            **flags,
        )
        log.info("insurance_case_parsed", flags_set=sum(flags.values()))
        return case

    except Exception as exc:
        log.error("insurance_case_parse_failed", error=str(exc))
        return None
