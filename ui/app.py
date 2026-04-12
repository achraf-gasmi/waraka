"""Waraka -- Interface analyste Streamlit (francais uniquement)."""

import os
import json
import httpx
import streamlit as st

API_BASE_URL: str = os.environ.get("WARAKA_API_URL", "http://localhost:8080")
API_KEY: str = os.environ.get("WARAKA_API_KEY", "waraka-dev-key-change-in-prod")

HEADERS: dict = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

RISK_COLORS: dict = {
    "critical": "#d32f2f",
    "high": "#f57c00",
    "medium": "#fbc02d",
    "low": "#388e3c",
}

RISK_LABELS: dict = {
    "critical": "CRITIQUE",
    "high": "ELEVE",
    "medium": "MOYEN",
    "low": "FAIBLE",
}

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Waraka -- Declaration de Soupcon",
    page_icon="📄",
    layout="wide",
)

st.title("Waraka -- Redaction de Declaration de Soupcon")
st.caption("Systeme d'aide a la redaction de declarations de soupcon goAML pour la CTAF")

# ---------------------------------------------------------------------------
# Sidebar -- institution info
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Informations de la declaration")

    institution = st.text_input(
        "Nom de l'institution",
        value="",
        placeholder="Ex: BH Bank",
    )
    analyst_id = st.text_input(
        "Identifiant analyste",
        value="",
        placeholder="Ex: ANA-001",
    )
    case_reference = st.text_input(
        "Reference interne (optionnel)",
        value="",
        placeholder="Ex: CAS-2026-001",
    )

    st.divider()
    analyse_btn = st.button(
        "Analyser la transaction",
        type="primary",
        use_container_width=True,
        disabled=not (institution and analyst_id),
    )

    if not institution or not analyst_id:
        st.warning("Renseignez l'institution et l'identifiant analyste avant d'analyser.")

# ---------------------------------------------------------------------------
# Main area -- top: text input
# ---------------------------------------------------------------------------

analyst_input = st.text_area(
    "Decrivez la transaction suspecte en francais",
    height=200,
    placeholder=(
        "Ex: Un client de la banque a effectue un virement de 850 000 TND "
        "vers une societe aux Emirats Arabes Unis via deux intermediaires au Luxembourg..."
    ),
)

# ---------------------------------------------------------------------------
# Analysis -- call API and store result in session state
# ---------------------------------------------------------------------------

if analyse_btn:
    if not analyst_input.strip():
        st.error("Veuillez saisir une description de la transaction.")
    else:
        with st.spinner("Analyse en cours... (30 secondes maximum)"):
            try:
                payload = {
                    "analyst_input": analyst_input,
                    "reporting_institution": institution,
                    "analyst_id": analyst_id,
                    "case_reference": case_reference or None,
                }
                response = httpx.post(
                    f"{API_BASE_URL}/v1/str/draft",
                    json=payload,
                    headers=HEADERS,
                    timeout=60.0,
                )
                response.raise_for_status()
                result = response.json()
                st.session_state["result"] = result
                st.session_state["corrections_submitted"] = False
            except httpx.TimeoutException:
                st.error("Delai d'attente depasse. Reessayez dans quelques instants.")
            except httpx.HTTPStatusError as exc:
                st.error(f"Erreur API ({exc.response.status_code}): {exc.response.text}")
            except Exception as exc:
                st.error(f"Erreur inattendue: {exc}")

# ---------------------------------------------------------------------------
# Results -- shown after analysis
# ---------------------------------------------------------------------------

if "result" in st.session_state:
    result: dict = st.session_state["result"]

    st.divider()
    tab1, tab2, tab3, tab4 = st.tabs(
        ["Résumé", "Récit", "XML goAML", "Validation"]
    )

    # ---- Tab 1: Summary ----
    with tab1:
        risk_raw = result.get("risk_level", "low")
        risk_label = RISK_LABELS.get(risk_raw, risk_raw.upper())
        risk_color = RISK_COLORS.get(risk_raw, "#757575")
        confidence = result.get("confidence", 0.0)

        col1, col2 = st.columns(2)
        with col1:
            st.markdown(
                f"**Niveau de risque:** "
                f'<span style="color:{risk_color};font-weight:bold;font-size:1.2em">'
                f"{risk_label}</span>",
                unsafe_allow_html=True,
            )
        with col2:
            st.metric("Score de confiance", f"{confidence:.0%}")

        st.subheader("Entites detectees")
        entities = result.get("extracted_entities", [])
        if entities:
            rows = []
            for e in entities:
                pep = "Oui" if e.get("is_pep") else "Non"
                sanc = "OUI" if e.get("sanctions_hit") else "Non"
                rows.append(
                    {
                        "Nom": e.get("name", ""),
                        "Type": e.get("entity_type", ""),
                        "Pays": e.get("country", ""),
                        "PPE": pep,
                        "Sanctions": sanc,
                    }
                )
            st.dataframe(rows, use_container_width=True)
        else:
            st.info("Aucune entite detectee.")

        st.subheader("Indicateurs de risque")
        indicators = result.get("risk_indicators", [])
        if indicators:
            for indicator in indicators:
                st.markdown(f"- {indicator}")
        else:
            st.info("Aucun indicateur de risque identifie.")

        sanctions_hit_entities = [
            e for e in entities if e.get("sanctions_hit")
        ]
        if sanctions_hit_entities:
            st.error("Entites sur liste de sanctions:")
            for e in sanctions_hit_entities:
                st.markdown(f"- **{e['name']}**: {e.get('sanctions_detail', 'Detail indisponible')}")

        if result.get("analyst_notes"):
            st.subheader("Notes pour l'analyste")
            for note in result["analyst_notes"]:
                st.warning(note)

    # ---- Tab 2: Narrative ----
    with tab2:
        st.subheader("Recit de la declaration de soupcon")
        narrative = result.get("narrative_fr", "")
        edited_narrative = st.text_area(
            "Recit (modifiable avant soumission)",
            value=narrative,
            height=400,
            key="narrative_edit",
        )
        if edited_narrative != narrative:
            st.session_state["result"]["narrative_fr"] = edited_narrative
            st.info("Recit modifie -- la modification sera prise en compte lors de la validation.")

    # ---- Tab 3: XML goAML ----
    with tab3:
        st.subheader("Fichier XML goAML")
        goaml_xml = result.get("goaml_xml", "")
        st.code(goaml_xml, language="xml")

        case_id = result.get("case_id", "case")
        st.download_button(
            label="Telecharger le fichier XML",
            data=goaml_xml.encode("utf-8"),
            file_name=f"STR_{case_id}.xml",
            mime="application/xml",
        )

    # ---- Tab 4: Validation ----
    with tab4:
        st.subheader("Validation par l'analyste")
        case_id = result.get("case_id", "")

        if st.session_state.get("corrections_submitted"):
            st.success("Votre validation a ete enregistree.")
        else:
            col_approve, col_correct = st.columns(2)

            with col_approve:
                if st.button("Approuver", type="primary", use_container_width=True):
                    _submit_approval(case_id, analyst_id, approved=True, corrections=None)

            with col_correct:
                show_corrections = st.button(
                    "Corriger", use_container_width=True
                )

            if show_corrections or st.session_state.get("show_corrections_form"):
                st.session_state["show_corrections_form"] = True
                corrections_text = st.text_area(
                    "Decrivez les corrections necessaires",
                    height=150,
                    placeholder="Ex: Le montant doit etre 750 000 TND, non 850 000 TND.",
                )
                if st.button("Soumettre les corrections"):
                    _submit_approval(
                        case_id, analyst_id, approved=False, corrections=corrections_text
                    )


def _submit_approval(
    case_id: str,
    analyst_id: str,
    approved: bool,
    corrections: str | None,
) -> None:
    """Call the API to record analyst approval or corrections."""
    try:
        payload = {
            "approved": approved,
            "analyst_id": analyst_id,
            "corrections": corrections,
        }
        response = httpx.post(
            f"{API_BASE_URL}/v1/str/{case_id}/approve",
            json=payload,
            headers=HEADERS,
            timeout=10.0,
        )
        response.raise_for_status()
        st.session_state["corrections_submitted"] = True
        st.session_state["show_corrections_form"] = False
        st.rerun()
    except Exception as exc:
        st.error(f"Erreur lors de la soumission: {exc}")
