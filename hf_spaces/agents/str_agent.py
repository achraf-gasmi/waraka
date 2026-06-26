"""STR Drafting Agent -- prompts and LLM call helpers.

All prompts are module-level constants. Temperature is always 0.0.
LLM timeout is always 30 seconds.

LLM_PROVIDER selects the backend at call time (env var, "anthropic" or
"gemini"). Each provider's SDK is imported lazily inside its own call
functions so a deployment only needs the package for the provider it uses.
"""

import json
import os
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
3. Les indicateurs de risque apparents, y compris les indicateurs structurels suivants

Pour chacun des indicateurs structurels ci-dessous, renseigne le champ booleen
correspondant dans "transaction". Mets true uniquement si l'indicateur est
explicitement ou implicitement etabli par le texte de l'analyste ; sinon, mets false.

- structuring_below_threshold : la description mentionne des paiements fractionnes
  ou structures pour rester juste sous un seuil de declaration reglementaire
  (structuration / smurfing) -- par exemple plusieurs montants legerement
  inferieurs a un seuil connu, ou des versements repetes calibres pour eviter
  un controle.
- multiple_transactions_same_beneficiary : plusieurs transactions distinctes,
  rapprochees dans le temps, vers le meme beneficiaire.
- no_commercial_justification : aucune facture, contrat ou piece justificative
  commerciale n'accompagne la transaction.
- weak_aml_destination : le pays destinataire est reconnu pour des controles
  LBA/FT faibles ou une faible cooperation internationale (au-dela de la simple
  liste GAFI haut risque -- inclut juridictions offshore opaques, secret
  bancaire fort, faible transparence des beneficiaires effectifs).
- activity_inconsistency : incoherence entre l'activite commerciale declaree
  du client et la nature, le volume ou la frequence des transactions observees.

Utilise l'outil extract_entities pour retourner les donnees extraites.

Si l'outil n'est pas disponible, reponds UNIQUEMENT en JSON valide respectant
exactement ce format -- aucun texte avant ou apres le JSON, aucune balise
markdown :
{
  "entities": [
    {
      "name": "string",
      "name_arabic": "string or null",
      "entity_type": "person | company",
      "id_number": "string or null",
      "nationality": "ISO-2 or null",
      "country": "ISO-2 or country name or null",
      "address": "string or null",
      "is_pep": false
    }
  ],
  "transaction": {
    "transaction_id": "string or null",
    "date": "YYYY-MM-DD or null",
    "amount": number or null,
    "currency": "TND",
    "transaction_type": "virement | especes | cheque | crypto | autre",
    "sender": { ...entity fields... },
    "receiver": { ...entity fields... },
    "intermediaries": [ ...entity list... ],
    "description": "string or null",
    "red_flags": ["string"],
    "no_prior_relationship": true,
    "structuring_below_threshold": false,
    "multiple_transactions_same_beneficiary": false,
    "no_commercial_justification": false,
    "weak_aml_destination": false,
    "activity_inconsistency": false
  },
  "initial_red_flags": ["string"]
}
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
- En particulier, examine si la description revele une structuration de
  paiements sous un seuil de declaration, des transactions repetees vers le
  meme beneficiaire, une absence de facture ou de contrat, une destination a
  controles LBA/FT faibles, ou une incoherence entre l'activite declaree du
  client et la transaction observee.
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
# Tool schema for structured entity extraction (Anthropic tool_use)
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
                    "structuring_below_threshold": {"type": "boolean"},
                    "multiple_transactions_same_beneficiary": {"type": "boolean"},
                    "no_commercial_justification": {"type": "boolean"},
                    "weak_aml_destination": {"type": "boolean"},
                    "activity_inconsistency": {"type": "boolean"},
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
GEMINI_MODEL: str = "gemini-2.5-flash"
LLM_TEMPERATURE: float = 0.0
LLM_TIMEOUT: float = 30.0
LLM_MAX_TOKENS: int = 4096


def _strip_json_fence(text: str) -> str:
    """Strip markdown code fences if the LLM wrapped JSON in them."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        cleaned = "\n".join(inner)
    return cleaned


# ---------------------------------------------------------------------------
# Anthropic backend
# ---------------------------------------------------------------------------

def get_anthropic_client():
    """Return a configured Anthropic client."""
    import anthropic

    return anthropic.Anthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        timeout=LLM_TIMEOUT,
    )


def _call_llm_anthropic(system: str, user: str, case_id: str) -> Optional[str]:
    import anthropic

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
        log.info("llm_call_success", model=LLM_MODEL, provider="anthropic", tokens=message.usage.output_tokens)
        return content

    except anthropic.APITimeoutError:
        log.error("llm_timeout", model=LLM_MODEL, provider="anthropic", timeout=LLM_TIMEOUT)
        return None
    except anthropic.APIError as exc:
        log.error("llm_api_error", provider="anthropic", error=str(exc))
        return None


def _call_llm_structured_anthropic(system: str, user: str, case_id: str) -> Optional[dict]:
    import anthropic

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
            log.error("no_tool_use_block_in_response", provider="anthropic")
            return None
        log.info(
            "llm_structured_call_success",
            model=LLM_MODEL,
            provider="anthropic",
            tokens=message.usage.output_tokens,
        )
        return tool_block.input

    except anthropic.APITimeoutError:
        log.error("llm_timeout", model=LLM_MODEL, provider="anthropic", timeout=LLM_TIMEOUT)
        return None
    except anthropic.APIError as exc:
        log.error("llm_api_error", provider="anthropic", error=str(exc))
        return None


# ---------------------------------------------------------------------------
# Gemini backend
# ---------------------------------------------------------------------------

def _get_gemini_model(system: str):
    import google.generativeai as genai

    genai.configure(api_key=os.environ.get("GEMINI_API_KEY", ""))
    return genai.GenerativeModel(model_name=GEMINI_MODEL, system_instruction=system)


def _call_llm_gemini(system: str, user: str, case_id: str) -> Optional[str]:
    import google.generativeai as genai

    log = logger.bind(case_id=case_id)

    try:
        model = _get_gemini_model(system)
        response = model.generate_content(
            user,
            generation_config=genai.types.GenerationConfig(
                temperature=LLM_TEMPERATURE,
                max_output_tokens=LLM_MAX_TOKENS,
            ),
            request_options={"timeout": LLM_TIMEOUT},
        )
        content = response.text if response and response.text else None
        log.info("llm_call_success", model=GEMINI_MODEL, provider="gemini")
        return content
    except Exception as exc:
        log.error("llm_api_error", provider="gemini", error=str(exc))
        return None


def _call_llm_structured_gemini(system: str, user: str, case_id: str) -> Optional[dict]:
    import google.generativeai as genai

    log = logger.bind(case_id=case_id)

    try:
        model = _get_gemini_model(system)
        response = model.generate_content(
            user,
            generation_config=genai.types.GenerationConfig(
                temperature=LLM_TEMPERATURE,
                max_output_tokens=LLM_MAX_TOKENS,
                response_mime_type="application/json",
            ),
            request_options={"timeout": LLM_TIMEOUT},
        )
        text = response.text if response and response.text else None
        if not text:
            log.error("empty_gemini_response", provider="gemini")
            return None

        data = json.loads(_strip_json_fence(text))
        log.info("llm_structured_call_success", model=GEMINI_MODEL, provider="gemini")
        return data

    except json.JSONDecodeError as exc:
        log.error("llm_json_parse_failed", provider="gemini", error=str(exc))
        return None
    except Exception as exc:
        log.error("llm_api_error", provider="gemini", error=str(exc))
        return None


# ---------------------------------------------------------------------------
# Public dispatch -- selects backend from LLM_PROVIDER at call time
# ---------------------------------------------------------------------------

def call_llm(
    system: str,
    user: str,
    case_id: str,
) -> Optional[str]:
    """Text-only LLM call -- used for narrative generation.

    Backend is selected by the LLM_PROVIDER env var ("anthropic" or "gemini"),
    read fresh on every call so it can be set per-deployment without import
    order concerns.

    Returns:
        LLM response text, or None on failure.
    """
    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    if provider == "gemini":
        return _call_llm_gemini(system, user, case_id)
    return _call_llm_anthropic(system, user, case_id)


def call_llm_structured(
    system: str,
    user: str,
    case_id: str,
) -> Optional[dict]:
    """Structured LLM call -- guarantees schema-validated output.

    Anthropic: forces tool_use via tool_choice, returns the validated tool
    input dict. Gemini: forces JSON-mime output and parses it.

    Returns:
        Parsed dict matching EXTRACTION_TOOL's input_schema, or None on failure.
    """
    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    if provider == "gemini":
        return _call_llm_structured_gemini(system, user, case_id)
    return _call_llm_structured_anthropic(system, user, case_id)
