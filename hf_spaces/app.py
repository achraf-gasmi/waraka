"""
Waraka -- Hugging Face Spaces interface
Declaration de Soupcon (STR) -- CTAF / goAML

This runs the real Waraka STR drafting pipeline (LangGraph agent in
graph/str_graph.py, vendored alongside this file) against the Google Gemini
API -- no FastAPI backend, no PostgreSQL, no Redis, no ChromaDB. Sanctions
screening (tools/sanctions_tool.py) is optional and no-ops gracefully without
OPENSANCTIONS_API_KEY. Requires GEMINI_API_KEY as an HF Space secret --
there is no demo/mock fallback.
"""

import asyncio
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import streamlit as st

# LLM_PROVIDER must be set before agents.str_agent is imported by graph.str_graph,
# since the dispatch functions read it fresh on every call but we want this
# deployment locked to Gemini regardless of any other env state.
os.environ.setdefault("LLM_PROVIDER", "gemini")

from graph.str_graph import run_str_graph  # noqa: E402

GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")

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


def run_analysis(
    analyst_input: str,
    institution: str,
    analyst_id: str,
    case_reference: str,
) -> Optional[dict]:
    """Run the real Waraka pipeline (run_str_graph) and adapt its output for the UI."""
    case_id = str(uuid.uuid4())
    full_case_ref = case_reference or f"CASE-{case_id[:8].upper()}"

    request_dict = {
        "analyst_input": analyst_input,
        "reporting_institution": institution,
        "analyst_id": analyst_id,
        "case_reference": full_case_ref,
        "case_id": case_id,
    }

    start = datetime.now(timezone.utc)
    try:
        final_state = asyncio.run(run_str_graph(request_dict))
    except Exception as exc:
        st.error(f"Erreur lors de l'execution du pipeline Waraka : {exc}")
        return None
    latency_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)

    if final_state.get("errors"):
        st.error("Erreur du pipeline : " + "; ".join(final_state["errors"]))
        return None

    return {
        "case_id": full_case_ref,
        "status": "draft",
        "confidence": final_state.get("confidence", 0.0),
        "risk_level": final_state.get("risk_level", "low"),
        "extracted_entities": final_state.get("extracted_entities", []),
        "risk_indicators": final_state.get("risk_indicators", []),
        "narrative_fr": final_state.get("narrative_fr", ""),
        "goaml_xml": final_state.get("goaml_xml", ""),
        "sanctions_checked": bool(final_state.get("sanctions_results")),
        "analyst_notes": final_state.get("analyst_notes", []),
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

st.success("Connecté à l'API Google Gemini · pipeline Waraka complet (LangGraph).")
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
        with st.spinner("Analyse par le pipeline Waraka en cours (30 à 45 secondes)..."):
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

        if not result.get("sanctions_checked"):
            st.caption(
                "ℹ️ Filtrage sanctions non effectué (OPENSANCTIONS_API_KEY non configurée)."
            )

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
