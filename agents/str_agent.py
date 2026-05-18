"""STR Drafting Agent -- prompts and LLM call helpers.

All prompts are module-level constants. Temperature is always 0.0.
LLM timeout is always 30 seconds.
"""

import os
import anthropic
import structlog
from typing import Optional

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Module-level prompt constants -- never constructed inside functions
# ---------------------------------------------------------------------------

ENTITY_EXTRACTION_SYSTEM: str = """
Tu es un expert en conformite bancaire tunisienne specialise dans la lutte contre
le blanchiment d'argent (LBA). Tu analyses des descriptions de transactions
suspectes redigees par des analystes de conformite.

Ta tache est d'extraire de maniere structuree :
1. Toutes les entites mentionnees (personnes physiques et morales)
2. Les details de la ou des transactions
3. Les indicateurs de risque apparents

Utilise l'outil extract_entities pour retourner les donnees extraites.
"""

ENTITY_EXTRACTION_USER: str = """
Analyse la description suivante et extrait toutes les entites et transactions.

Description de l'analyste :
{analyst_input}

Institution declarante : {reporting_institution}

Extrait :
- Toutes les personnes physiques et morales mentionnees
- Les montants, devises, dates
- Le type de transaction
- Les pays et juridictions impliques
- Les intermediaires eventuels
- Tout indicateur de risque apparent (structuration, pays a risque, PPE, etc.)
"""

NARRATIVE_GENERATION_SYSTEM: str = """
Tu es un expert en conformite bancaire tunisienne. Tu rediges des declarations
de soupcon formelles destinees a la Commission Tunisienne des Analyses
Financieres (CTAF) via la plateforme goAML.

Le texte que tu produis doit :
- Etre redige en francais formel et juridique
- Respecter les standards de la CTAF (loi organique 2015-26 modifiee par 2019-9)
- Decrire objectivement les faits sans jugement definitif
- Mentionner explicitement les indicateurs de risque identifies
- Etre concis (300-500 mots maximum)
- Ne jamais inclure d'informations non mentionnees dans les donnees fournies

Commence directement le recit. Pas d'introduction comme "Voici le recit...".
"""

NARRATIVE_GENERATION_USER: str = """
Redige le recit de la declaration de soupcon a partir des elements suivants :

Entites impliquees :
{entities_summary}

Transaction :
{transaction_summary}

Indicateurs de risque identifies :
{risk_indicators}

Resultats de filtrage sanctions :
{sanctions_summary}

Institution declarante : {reporting_institution}
Date de la declaration : {declaration_date}
"""

# ---------------------------------------------------------------------------
# Tool schema for structured entity extraction (tool_use)
# ---------------------------------------------------------------------------

_ENTITY_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "name_arabic": {"type": ["string", "null"]},
        "entity_type": {"type": "string", "enum": ["person", "company"]},
        "id_number": {"type": ["string", "null"]},
        "nationality": {"type": ["string", "null"]},
        "country": {"type": ["string", "null"]},
        "address": {"type": ["string", "null"]},
        "is_pep": {"type": "boolean"},
    },
    "required": ["name", "entity_type", "is_pep"],
}

EXTRACTION_TOOL: dict = {
    "name": "extract_entities",
    "description": (
        "Extrait les entites, la transaction et les indicateurs de risque "
        "d'une description de transaction suspecte AML."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "entities": {
                "type": "array",
                "description": "Toutes les personnes physiques et morales mentionnees",
                "items": _ENTITY_SCHEMA,
            },
            "transaction": {
                "type": "object",
                "description": "Details de la transaction suspecte",
                "properties": {
                    "transaction_id": {"type": ["string", "null"]},
                    "date": {
                        "type": ["string", "null"],
                        "description": "Format YYYY-MM-DD",
                    },
                    "amount": {"type": ["number", "null"]},
                    "currency": {"type": "string", "default": "TND"},
                    "transaction_type": {
                        "type": "string",
                        "enum": ["virement", "especes", "cheque", "crypto", "autre"],
                    },
                    "sender": _ENTITY_SCHEMA,
                    "receiver": _ENTITY_SCHEMA,
                    "intermediaries": {
                        "type": "array",
                        "items": _ENTITY_SCHEMA,
                    },
                    "description": {"type": ["string", "null"]},
                    "red_flags": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "no_prior_relationship": {"type": "boolean"},
                },
                "required": ["transaction_type", "sender", "receiver"],
            },
            "initial_red_flags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Indicateurs de risque initiaux identifies",
            },
        },
        "required": ["entities", "transaction", "initial_red_flags"],
    },
}

# ---------------------------------------------------------------------------
# LLM configuration constants
# ---------------------------------------------------------------------------

LLM_MODEL: str = "claude-sonnet-4-6"
LLM_TEMPERATURE: float = 0.0
LLM_TIMEOUT: float = 30.0
LLM_MAX_TOKENS: int = 4096


def get_anthropic_client() -> anthropic.Anthropic:
    """Return a configured Anthropic client."""
    return anthropic.Anthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        timeout=LLM_TIMEOUT,
    )


def call_llm(
    system: str,
    user: str,
    case_id: str,
) -> Optional[str]:
    """Text-only LLM call -- used for narrative generation.

    Returns:
        LLM response text, or None on failure.
    """
    log = logger.bind(case_id=case_id)
    client = get_anthropic_client()

    try:
        message = client.messages.create(
            model=LLM_MODEL,
            max_tokens=LLM_MAX_TOKENS,
            temperature=LLM_TEMPERATURE,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        content = message.content[0].text if message.content else None
        log.info("llm_call_success", model=LLM_MODEL, tokens=message.usage.output_tokens)
        return content

    except anthropic.APITimeoutError:
        log.error("llm_timeout", model=LLM_MODEL, timeout=LLM_TIMEOUT)
        return None
    except anthropic.APIError as exc:
        log.error("llm_api_error", error=str(exc))
        return None


def call_llm_structured(
    system: str,
    user: str,
    case_id: str,
) -> Optional[dict]:
    """Structured LLM call via tool_use -- guarantees schema-validated output.

    Forces Claude to respond using the extract_entities tool, so the response
    is always a validated dict matching EXTRACTION_TOOL's input_schema.

    Returns:
        Parsed tool input dict, or None on failure.
    """
    log = logger.bind(case_id=case_id)
    client = get_anthropic_client()

    try:
        message = client.messages.create(
            model=LLM_MODEL,
            max_tokens=LLM_MAX_TOKENS,
            temperature=LLM_TEMPERATURE,
            system=system,
            messages=[{"role": "user", "content": user}],
            tools=[EXTRACTION_TOOL],
            tool_choice={"type": "tool", "name": "extract_entities"},
        )
        tool_block = next(
            (b for b in message.content if b.type == "tool_use"),
            None,
        )
        if not tool_block:
            log.error("no_tool_use_block_in_response")
            return None
        log.info(
            "llm_structured_call_success",
            model=LLM_MODEL,
            tokens=message.usage.output_tokens,
        )
        return tool_block.input

    except anthropic.APITimeoutError:
        log.error("llm_timeout", model=LLM_MODEL, timeout=LLM_TIMEOUT)
        return None
    except anthropic.APIError as exc:
        log.error("llm_api_error", error=str(exc))
        return None
