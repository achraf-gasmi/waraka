"""
Waraka -- Hugging Face Spaces interface
Declaration de Soupcon (STR) -- CTAF / goAML

This app calls the real Google Gemini API directly (no FastAPI backend, no
database, no LangGraph). It requires GEMINI_API_KEY to be configured
as a secret in the HF Space settings -- there is no demo/mock fallback.
"""

import os
import json
import uuid
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional

import streamlit as st

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")

LLM_MODEL: str = "gemini-1.5-flash"
LLM_TEMPERATURE: float = 0.0
LLM_TIMEOUT: float = 45.0
LLM_MAX_TOKENS: int = 4096

RISK_COLORS: dict = {
    "critical": "#ff6b6b",
    "high":     "#ffa94d",
    "medium":   "#ffd43b",
    "low":      "#69db7c",
}
RISK_BG: dict = {
    "critical": "#3a1c1c",
    "high":     "#3a2a14",
    "medium":   "#3a3414",
    "low":      "#1c3a22",
}
RISK_LABELS: dict = {
    "critical": "CRITIQUE",
    "high":     "ELEVE",
    "medium":   "MOYEN",
    "low":      "FAIBLE",
}

HIGH_RISK_COUNTRIES: list = [
    "AE", "IR", "KP", "SY", "YE", "LY", "SD", "AF",
    "VE", "MM", "NI", "PA", "UG",
]

# ---------------------------------------------------------------------------
# Prompts (module-level constants)
# ---------------------------------------------------------------------------

ENTITY_EXTRACTION_SYSTEM: str = """
Tu es un expert en conformite bancaire tunisienne specialise dans la lutte contre
le blanchiment d'argent (LBA). Tu analyses des descriptions de transactions
suspectes redigees par des analystes de conformite.

Ta tache est d'extraire de maniere structuree :
1. Toutes les entites mentionnees (personnes physiques et morales)
2. Les details de la ou des transactions
3. Les indicateurs de risque apparents

Reponds UNIQUEMENT en JSON valide. Aucun texte avant ou apres le JSON.
Aucune balise markdown. Uniquement le JSON brut.

Format de reponse requis :
{
  "entities": [
    {
      "name": "string",
      "entity_type": "person | company",
      "id_number": "string or null",
      "country": "ISO-2 or country name or null",
      "is_pep": false
    }
  ],
  "transaction": {
    "transaction_id": "string or null",
    "date": "YYYY-MM-DD or null",
    "amount": number or null,
    "currency": "TND",
    "transaction_type": "virement | especes | cheque | crypto | autre",
    "sender": { "name": "string", "entity_type": "company", "country": "string or null" },
    "receiver": { "name": "string", "entity_type": "company", "country": "string or null" },
    "intermediaries": [],
    "no_prior_relationship": true,
    "red_flags": ["string"]
  },
  "initial_red_flags": ["string"]
}
"""

ENTITY_EXTRACTION_USER: str = """Analyse la description suivante et extrait toutes les entites et transactions.

Description de l'analyste :
{analyst_input}

Institution declarante : {reporting_institution}

Extrait toutes les personnes, societes, montants, dates, pays, intermediaires et indicateurs de risque."""

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

NARRATIVE_GENERATION_USER: str = """Redige le recit de la declaration de soupcon a partir des elements suivants :

Entites impliquees :
{entities_summary}

Transaction :
{transaction_summary}

Indicateurs de risque identifies :
{risk_indicators}

Institution declarante : {reporting_institution}
Date de la declaration : {declaration_date}"""

# ---------------------------------------------------------------------------
# Inline pipeline -- direct Gemini calls, no DB, no LangGraph
# ---------------------------------------------------------------------------

def _call_gemini(system: str, user: str) -> Optional[str]:
    try:
        import google.generativeai as genai

        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(
            model_name=LLM_MODEL,
            system_instruction=system,
            generation_config=genai.types.GenerationConfig(
                temperature=LLM_TEMPERATURE,
                max_output_tokens=LLM_MAX_TOKENS,
            ),
        )
        response = model.generate_content(
            user,
            request_options={"timeout": LLM_TIMEOUT},
        )
        return response.text if response and response.text else None
    except Exception as exc:
        st.error(f"Erreur lors de l'appel a l'API Gemini : {exc}")
        return None


def _parse_amount(raw) -> float:
    if isinstance(raw, (int, float)):
        return float(raw)
    cleaned = re.sub(r"[\s,]", "", str(raw))
    cleaned = re.sub(r"[A-Za-z]+$", "", cleaned)
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _normalize_country(c: Optional[str]) -> Optional[str]:
    if not c:
        return None
    c = c.strip().upper()
    MAP = {
        "EMIRATS ARABES UNIS": "AE", "UNITED ARAB EMIRATES": "AE", "UAE": "AE",
        "MALTE": "MT", "MALTA": "MT",
        "LUXEMBOURG": "LU",
        "TUNISIE": "TN", "TUNISIA": "TN",
        "FRANCE": "FR", "MAROC": "MA", "MOROCCO": "MA",
    }
    return MAP.get(c, c[:2] if len(c) >= 2 else c)


def _assess_risk(tx: dict, sanctions: dict) -> tuple[list[str], float, str]:
    indicators, weight = [], 0.0

    receiver_country = (tx.get("receiver") or {}).get("country", "")
    if receiver_country in HIGH_RISK_COUNTRIES:
        indicators.append("Transaction vers une juridiction a haut risque selon le GAFI")
        weight += 0.30

    amount = _parse_amount(tx.get("amount", 0))
    if amount > 500_000:
        indicators.append(
            f"Montant superieur a 500 000 TND sans justification economique apparente "
            f"({int(amount):,} TND)".replace(",", " ")
        )
        weight += 0.20

    intermediaries = tx.get("intermediaries", []) or []
    if len(intermediaries) >= 2:
        indicators.append(
            f"Recours a plusieurs intermediaires sans justification commerciale "
            f"({len(intermediaries)} intermediaires)"
        )
        weight += 0.25

    if any(v.get("hit") for v in sanctions.values()):
        indicators.append("Entite figurant sur une liste de sanctions internationale")
        weight += 0.40

    sender = tx.get("sender") or {}
    receiver = tx.get("receiver") or {}
    if sender.get("is_pep") or receiver.get("is_pep"):
        indicators.append("Personne politiquement exposee impliquee dans la transaction")
        weight += 0.30

    if tx.get("no_prior_relationship"):
        indicators.append("Aucune relation commerciale anterieure avec le beneficiaire")
        weight += 0.15

    confidence = min(weight, 1.0)
    if confidence >= 0.6:
        level = "critical"
    elif confidence >= 0.4:
        level = "high"
    elif confidence >= 0.2:
        level = "medium"
    else:
        level = "low"

    return indicators, confidence, level


def _build_xml(tx: dict, narrative: str, case_ref: str, institution: str) -> str:
    report = ET.Element("report")
    ET.SubElement(report, "rentity_id").text = institution
    ET.SubElement(report, "rentity_branch").text = "HQ"
    ET.SubElement(report, "submission_code").text = "E"
    ET.SubElement(report, "report_code").text = "STR"
    ET.SubElement(report, "entity_reference").text = case_ref
    ET.SubElement(report, "fiu_ref_number")
    ET.SubElement(report, "submission_date").text = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ET.SubElement(report, "currency_code_local").text = tx.get("currency", "TND")

    rp = ET.SubElement(report, "reporting_person")
    ET.SubElement(rp, "role").text = "R"
    ET.SubElement(rp, "occupation").text = "COMPLIANCE_OFFICER"

    loc = ET.SubElement(report, "location")
    ET.SubElement(loc, "address_type").text = "B"
    ET.SubElement(loc, "country").text = "TN"

    txe = ET.SubElement(report, "transaction")
    ET.SubElement(txe, "transactionnumber").text = tx.get("transaction_id") or case_ref
    ET.SubElement(txe, "transaction_location").text = "TN"
    date_val = tx.get("date", "")
    if isinstance(date_val, datetime):
        date_val = date_val.strftime("%Y-%m-%d")
    ET.SubElement(txe, "date_transaction").text = str(date_val)[:10] if date_val else ""
    ET.SubElement(txe, "teller")
    ET.SubElement(txe, "authorized")
    ET.SubElement(txe, "amount_local").text = str(tx.get("amount", 0))

    def add_entity(parent, entity: dict):
        if entity.get("entity_type") == "person":
            parts = entity.get("name", "").split()
            ET.SubElement(parent, "first_name").text = parts[0] if parts else ""
            ET.SubElement(parent, "last_name").text = " ".join(parts[1:]) if len(parts) > 1 else ""
        else:
            ET.SubElement(parent, "name").text = entity.get("name", "")
            if entity.get("id_number"):
                ET.SubElement(parent, "registration_number").text = entity["id_number"]
        if entity.get("country"):
            ET.SubElement(parent, "country").text = entity["country"]

    from_e = ET.SubElement(txe, "t_from_my_client")
    add_entity(from_e, tx.get("sender") or {})

    to_e = ET.SubElement(txe, "t_to_my_client")
    add_entity(to_e, tx.get("receiver") or {})

    for idx, inter in enumerate(tx.get("intermediaries", []) or [], start=1):
        ie = ET.SubElement(txe, "t_intermediary")
        ie.set("sequence", str(idx))
        add_entity(ie, inter)

    ET.SubElement(report, "narrative").text = narrative

    ET.indent(report, space="  ")
    xml_str = ET.tostring(report, encoding="unicode", xml_declaration=False)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str


def run_analysis(
    analyst_input: str,
    institution: str,
    analyst_id: str,
    case_reference: str,
) -> Optional[dict]:
    """Run the full pipeline against the real Gemini API. Returns None on failure."""
    case_id = str(uuid.uuid4())[:8].upper()
    full_case_ref = case_reference or f"CASE-{case_id}"
    start = datetime.now(timezone.utc)

    # Step 1 -- entity extraction
    user_msg = ENTITY_EXTRACTION_USER.format(
        analyst_input=analyst_input,
        reporting_institution=institution,
    )
    raw_json = _call_gemini(ENTITY_EXTRACTION_SYSTEM, user_msg)
    if raw_json is None:
        return None

    tx: dict = {}
    entities: list = []
    red_flags: list = []

    try:
        cleaned = raw_json.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        data = json.loads(cleaned)
        entities = data.get("entities", [])
        tx = data.get("transaction", {})
        red_flags = data.get("initial_red_flags", [])
        for e in entities:
            e["country"] = _normalize_country(e.get("country"))
            e.setdefault("is_pep", False)
            e.setdefault("sanctions_hit", False)
        for key in ("sender", "receiver"):
            if tx.get(key):
                tx[key]["country"] = _normalize_country(tx[key].get("country"))
                tx[key].setdefault("is_pep", False)
        for inter in tx.get("intermediaries", []) or []:
            inter["country"] = _normalize_country(inter.get("country"))
    except Exception as exc:
        st.error(f"Erreur lors de l'analyse de la reponse de Gemini : {exc}")
        return None

    # Step 2 -- risk assessment (rule-based)
    indicators, confidence, risk_level = _assess_risk(tx, {})

    # Step 3 -- narrative generation
    entities_lines = "\n".join(
        f"- {e.get('name', 'N/A')} ({e.get('entity_type', '')}, {e.get('country', 'N/A')})"
        for e in entities
    ) or "Non disponible"

    tx_lines = (
        f"Type: {tx.get('transaction_type', 'N/A')}\n"
        f"Montant: {tx.get('amount', 'N/A')} {tx.get('currency', 'TND')}\n"
        f"Date: {tx.get('date', 'N/A')}\n"
        f"Emetteur: {(tx.get('sender') or {}).get('name', 'N/A')}\n"
        f"Beneficiaire: {(tx.get('receiver') or {}).get('name', 'N/A')}"
    )

    narrative_user = NARRATIVE_GENERATION_USER.format(
        entities_summary=entities_lines,
        transaction_summary=tx_lines,
        risk_indicators="\n".join(f"- {r}" for r in indicators) or "Aucun",
        reporting_institution=institution,
        declaration_date=datetime.now(timezone.utc).strftime("%d/%m/%Y"),
    )
    narrative = _call_gemini(NARRATIVE_GENERATION_SYSTEM, narrative_user)
    if narrative is None:
        return None

    # Step 4 -- XML
    xml = _build_xml(tx, narrative, full_case_ref, institution)

    latency_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)

    analyst_notes = [f"Indicateur initial : {f}" for f in red_flags]

    return {
        "case_id": full_case_ref,
        "status": "draft",
        "confidence": confidence,
        "risk_level": risk_level,
        "extracted_entities": entities,
        "risk_indicators": indicators,
        "narrative_fr": narrative,
        "goaml_xml": xml,
        "sanctions_checked": False,
        "analyst_notes": analyst_notes,
        "latency_ms": latency_ms,
    }


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

def _risk_badge(risk_level: str) -> str:
    color = RISK_COLORS.get(risk_level, "#757575")
    bg = RISK_BG.get(risk_level, "#f5f5f5")
    label = RISK_LABELS.get(risk_level, risk_level.upper())
    return (
        f'<span style="background:{bg};color:{color};border:2px solid {color};'
        f'border-radius:6px;padding:6px 18px;font-weight:700;font-size:1.1em;'
        f'letter-spacing:1px">{label}</span>'
    )


# ---------------------------------------------------------------------------
# Streamlit page
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Waraka -- Declaration de Soupcon",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Minimal custom CSS -- dark theme throughout, all text colors explicit.
# !important is required because Streamlit/HF Spaces inject their own
# sidebar background rule after this block, which otherwise wins.
st.markdown("""
<style>
    [data-testid="stSidebar"],
    [data-testid="stSidebarContent"],
    section[data-testid="stSidebar"] > div {
        background-color: #161a23 !important;
        border-right: 1px solid #2a2f3a;
    }
    [data-testid="stSidebar"] * { color: #fafafa !important; }
    [data-testid="stSidebar"] input,
    [data-testid="stSidebar"] textarea {
        background-color: #0e1117 !important;
        color: #fafafa !important;
    }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        font-weight: 600;
        padding: 8px 20px;
        border-radius: 6px 6px 0 0;
        color: #c9d1d9;
    }
    .stTabs [aria-selected="true"] { color: #fafafa; }
    .indicator-item {
        background: #2a2410;
        border-left: 4px solid #ffd43b;
        border-radius: 0 6px 6px 0;
        padding: 8px 14px;
        margin: 4px 0;
        font-size: 0.95em;
        color: #f5e6b8;
    }
</style>
""", unsafe_allow_html=True)

# Header
col_logo, col_title = st.columns([1, 8])
with col_logo:
    st.markdown("## 🏦")
with col_title:
    st.markdown("## Waraka — Déclaration de Soupçon")
    st.caption("Système d'aide à la rédaction de déclarations de soupçon (STR) conforme goAML / CTAF")

st.divider()

# ---------------------------------------------------------------------------
# Hard gate -- no demo mode, no mock fallback. Stop here if no API key.
# ---------------------------------------------------------------------------

if not GEMINI_API_KEY:
    st.error(
        "**Clé API manquante.** Cette application nécessite une clé Google Gemini valide "
        "pour fonctionner — il n'existe pas de mode démonstration.\n\n"
        "**Pour configurer la clé sur Hugging Face Spaces :**\n"
        "1. Ouvrez les **Settings** de ce Space\n"
        "2. Allez dans la section **Variables and secrets**\n"
        "3. Ajoutez un secret nommé `GEMINI_API_KEY` avec votre clé Gemini "
        "(obtenue sur [aistudio.google.com](https://aistudio.google.com/app/apikey))\n"
        "4. Redémarrez le Space (Factory reboot)"
    )
    st.stop()

st.success("Connecté à l'API Google Gemini (gemini-1.5-flash).")
st.divider()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### 📋 Informations de la déclaration")
    st.markdown("")

    institution = st.text_input(
        "Institution déclarante *",
        value="",
        placeholder="Ex : BH Bank",
    )
    analyst_id = st.text_input(
        "Identifiant analyste *",
        value="",
        placeholder="Ex : ANA-001",
    )
    case_reference = st.text_input(
        "Référence interne",
        value="",
        placeholder="Ex : CAS-2026-001 (optionnel)",
    )

    st.divider()

    generer_btn = st.button(
        "🔍 Générer le rapport",
        type="primary",
        use_container_width=True,
        disabled=not (institution.strip() and analyst_id.strip()),
    )

    if not institution.strip() or not analyst_id.strip():
        st.caption("⚠️ Renseignez l'institution et l'identifiant analyste.")

    st.divider()
    st.markdown("**À propos**")
    st.caption(
        "Waraka est un agent IA d'aide à la rédaction de déclarations de soupçon "
        "pour les banques tunisiennes, conforme à la circulaire BCT n° 2025-17 "
        "et à la loi organique 2015-26."
    )

# ---------------------------------------------------------------------------
# Main input area
# ---------------------------------------------------------------------------

analyst_input = st.text_area(
    "Description de la transaction suspecte (en français)",
    value="",
    height=180,
    placeholder=(
        "Décrivez la transaction suspecte : montants, entités, pays impliqués, "
        "justifications fournies, relations commerciales antérieures..."
    ),
)

# ---------------------------------------------------------------------------
# Trigger analysis
# ---------------------------------------------------------------------------

if generer_btn:
    if not analyst_input.strip():
        st.error("Veuillez saisir une description de la transaction.")
    else:
        with st.spinner("Analyse par Gemini en cours (30 à 45 secondes)..."):
            result = run_analysis(
                analyst_input.strip(),
                institution.strip(),
                analyst_id.strip(),
                case_reference.strip(),
            )
        if result is not None:
            st.session_state["result"] = result
            st.session_state["validation_done"] = False
            st.session_state["show_corrections"] = False
            st.rerun()

# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

if "result" in st.session_state:
    result: dict = st.session_state["result"]
    st.divider()

    tab_resume, tab_recit, tab_xml, tab_validation = st.tabs(
        ["📊 Résumé", "📝 Récit", "📄 XML goAML", "✅ Validation"]
    )

    # ------------------------------------------------------------------
    # Tab 1 : Résumé
    # ------------------------------------------------------------------
    with tab_resume:
        risk_level = result.get("risk_level", "low")
        confidence = result.get("confidence", 0.0)
        latency = result.get("latency_ms", 0)

        # Top metrics row
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown("**Niveau de risque**")
            st.markdown(_risk_badge(risk_level), unsafe_allow_html=True)
        with c2:
            st.metric("Score de confiance", f"{confidence:.0%}")
        with c3:
            st.metric("Entités détectées", len(result.get("extracted_entities", [])))
        with c4:
            st.metric("Indicateurs", len(result.get("risk_indicators", [])))

        st.markdown("")

        # Entities
        st.markdown("#### Entités identifiées")
        entities = result.get("extracted_entities", [])
        if entities:
            rows = []
            for e in entities:
                rows.append({
                    "Nom": e.get("name", ""),
                    "Type": "Personne" if e.get("entity_type") == "person" else "Société",
                    "Pays": e.get("country") or "—",
                    "N° identification": e.get("id_number") or "—",
                    "PPE": "⚠️ Oui" if e.get("is_pep") else "Non",
                    "Sanctions": "🔴 OUI" if e.get("sanctions_hit") else "Non",
                })
            st.dataframe(rows, use_container_width=True, hide_index=True)

            sanctions_hits = [e for e in entities if e.get("sanctions_hit")]
            if sanctions_hits:
                st.error(
                    "🔴 **Entités sur liste de sanctions internationale :**\n"
                    + "\n".join(f"- **{e['name']}** : {e.get('sanctions_detail', 'Détail indisponible')}"
                                for e in sanctions_hits)
                )
        else:
            st.info("Aucune entité détectée.")

        # Risk indicators
        st.markdown("#### Indicateurs de risque détectés")
        indicators = result.get("risk_indicators", [])
        if indicators:
            for ind in indicators:
                st.markdown(
                    f'<div class="indicator-item">⚠️ {ind}</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.success("Aucun indicateur de risque identifié.")

        # Analyst notes
        notes = result.get("analyst_notes", [])
        if notes:
            st.markdown("")
            st.markdown("#### Notes pour l'analyste")
            for note in notes:
                if "SANCTIONS" in note.upper():
                    st.error(f"🔴 {note}")
                else:
                    st.info(f"📌 {note}")

        if latency:
            st.caption(f"Temps d'analyse : {latency / 1000:.1f}s | Réf. : {result.get('case_id', '—')}")

    # ------------------------------------------------------------------
    # Tab 2 : Récit
    # ------------------------------------------------------------------
    with tab_recit:
        st.markdown("#### Récit de la déclaration de soupçon")
        st.caption(
            "Ce récit a été généré conformément aux standards de la CTAF "
            "(loi organique 2015-26 modifiée par 2019-9). "
            "Vous pouvez le modifier avant validation."
        )
        narrative = result.get("narrative_fr", "")
        edited = st.text_area(
            "Récit (modifiable)",
            value=narrative,
            height=420,
            key="narrative_edit",
            label_visibility="collapsed",
        )
        if edited != narrative:
            st.session_state["result"]["narrative_fr"] = edited
            st.caption("✏️ Récit modifié — la version corrigée sera utilisée lors de la validation.")

        word_count = len(edited.split()) if edited else 0
        st.caption(f"Nombre de mots : {word_count} (recommandé : 300–500)")

    # ------------------------------------------------------------------
    # Tab 3 : XML goAML
    # ------------------------------------------------------------------
    with tab_xml:
        st.markdown("#### Fichier XML goAML — Format STR-T")
        st.caption(
            "Fichier conforme au schéma UNODC goAML pour soumission à la CTAF. "
            "Vérifiez les champs avant téléchargement."
        )
        goaml_xml = result.get("goaml_xml", "")

        with st.expander("Afficher le XML complet", expanded=True):
            st.code(goaml_xml, language="xml")

        case_id_dl = result.get("case_id", "case").replace("/", "-")
        st.download_button(
            label="⬇️ Télécharger STR_{}.xml".format(case_id_dl),
            data=goaml_xml.encode("utf-8"),
            file_name=f"STR_{case_id_dl}.xml",
            mime="application/xml",
            use_container_width=True,
        )

    # ------------------------------------------------------------------
    # Tab 4 : Validation
    # ------------------------------------------------------------------
    with tab_validation:
        st.markdown("#### Validation par l'analyste")
        st.caption(
            "Conformément à la circulaire BCT n° 2025-17 et à l'article 107 de la "
            "loi organique 2015-26, chaque déclaration doit faire l'objet d'une "
            "validation humaine avant soumission à la CTAF."
        )
        st.markdown("")

        if st.session_state.get("validation_done"):
            action = st.session_state.get("validation_action", "approuve")
            if action == "approuve":
                st.success(
                    "✅ **Déclaration approuvée.** Elle peut être soumise à la CTAF via goAML."
                )
            else:
                st.warning(
                    "✏️ **Corrections enregistrées.** La déclaration est retournée pour révision."
                )
            if st.button("Nouvelle analyse", use_container_width=False):
                for key in ("result", "validation_done", "show_corrections", "validation_action"):
                    st.session_state.pop(key, None)
                st.rerun()
        else:
            col_app, col_rej = st.columns(2)

            with col_app:
                if st.button(
                    "✅ Approuver la déclaration",
                    type="primary",
                    use_container_width=True,
                ):
                    st.session_state["validation_done"] = True
                    st.session_state["validation_action"] = "approuve"
                    st.rerun()

            with col_rej:
                if st.button(
                    "✏️ Demander des corrections",
                    use_container_width=True,
                ):
                    st.session_state["show_corrections"] = True

            if st.session_state.get("show_corrections"):
                st.markdown("")
                corrections_text = st.text_area(
                    "Corrections requises",
                    height=140,
                    placeholder=(
                        "Décrivez les corrections nécessaires :\n"
                        "Ex. : Le montant indiqué est inexact — vérifier le relevé du 15/03/2026."
                    ),
                )
                if st.button("Soumettre les corrections", use_container_width=False):
                    if corrections_text.strip():
                        st.session_state["validation_done"] = True
                        st.session_state["validation_action"] = "corrige"
                        st.session_state["corrections_text"] = corrections_text
                        st.rerun()
                    else:
                        st.error("Veuillez saisir le texte des corrections avant de soumettre.")

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.divider()
st.caption(
    "Waraka v1 · Conforme BCT circulaire n° 2025-17 · "
    "Loi organique 2015-26 modifiée par 2019-9 · "
    "goAML UNODC · © 2026 Achraf Gasmi"
)
