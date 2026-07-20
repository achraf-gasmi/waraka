"""Insurance-sector AML/CFT risk rule registry for Waraka.

Jurisdiction-agnostic indicator taxonomy for life & non-life insurance,
derived from PUBLIC international typologies:

  - FATF, "Guidance for a Risk-Based Approach: Life Insurance Sector" (2018)
  - FATF, "Money Laundering & Terrorist Financing Typologies -- Insurance"
  - IAIS, Insurance Core Principle 22 (AML/CFT)
  - CTAF published typologies (Tunisia) for local threshold defaults

Design principles:
  * Every rule carries: phase, category, detection owner, weight (0-1),
    and the boolean extraction field that triggers it.
  * Monetary thresholds are NEVER hardcoded in rules -- they live in
    JurisdictionConfig so the same registry serves any insurer in any
    market (TND, EUR, MAD, ...).
  * Weights express relative severity on a 0-1 scale. Scoring is a
    capped weight sum, consistent with the banking-mode scorer in
    graph/str_graph.py (>=0.6 CRITICAL, >=0.4 HIGH, >=0.2 MEDIUM).
"""

from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------------------
# Jurisdiction / institution configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class JurisdictionConfig:
    """Market-specific parameters. Defaults calibrated for Tunisia (CTAF).

    Any insurer adopts the registry by instantiating its own config --
    no rule changes required.
    """
    currency: str = "TND"
    cash_premium_threshold: float = 5_000.0        # cash payment reporting trigger
    high_risk_product_threshold: float = 5_000.0   # ops on high-risk products
    high_capital_threshold: float = 100_000.0      # sum assured alert level
    surrender_threshold: float = 5_000.0           # surrender / claim payout
    early_surrender_days: int = 365                # "rapid surrender" window


TUNISIA = JurisdictionConfig()
EU_DEFAULT = JurisdictionConfig(
    currency="EUR",
    cash_premium_threshold=10_000.0,
    high_risk_product_threshold=10_000.0,
    high_capital_threshold=250_000.0,
    surrender_threshold=10_000.0,
)


# ---------------------------------------------------------------------------
# Taxonomy axes
# ---------------------------------------------------------------------------

class Phase(str, Enum):
    KYC_ONBOARDING = "kyc_onboarding"        # verification / screening / updates
    SOUSCRIPTION = "souscription"            # underwriting / policy purchase
    PAIEMENT_PRIME = "paiement_prime"        # premium payment
    VIE_CONTRAT = "vie_contrat"              # endorsements, loans, transfers
    RACHAT_INDEMNISATION = "rachat_indemnisation"  # surrender / claims payout
    CONTROLE = "controle"                    # ongoing monitoring


class Category(str, Enum):
    PROFIL_CLIENT = "profil_client_kyc"
    ORIGINE_FONDS = "origine_flux_financiers"
    COMPORTEMENT = "comportement_contractuel"
    BENEFICIAIRES = "beneficiaires_tiers"
    CANAL_GEO = "canal_zone_geographique"
    SURVEILLANCE = "surveillance_liens"


class Owner(str, Enum):
    FRONT_OFFICE = "front_office"
    DIRECTION_TECHNIQUE = "direction_technique"
    DIRECTION_FINANCIERE = "direction_financiere"
    DIRECTION_PRODUCTION = "direction_production"
    CONFORMITE = "conformite"


@dataclass(frozen=True)
class InsuranceRiskRule:
    id: str
    name: str
    label_fr: str                    # goes into the STR narrative
    phase: Phase
    category: Category
    weight: float                    # 0-1 relative severity
    trigger_field: str               # boolean on InsuranceCase set by extraction
    detected_by: tuple[Owner, ...] = field(default_factory=tuple)
    source: str = "FATF RBA Life Insurance 2018"


# ---------------------------------------------------------------------------
# Registry -- 29 indicators across the full policy lifecycle
# Weight anchors: sanctions=1.0 > PEP/shell=0.75-0.8 > early surrender=0.7
# > high-risk jurisdiction=0.7 > cash/unexplained funds=0.6 > behavioural=0.35-0.5
# ---------------------------------------------------------------------------

INSURANCE_RISK_RULES: list[InsuranceRiskRule] = [

    # ---- Phase 1: KYC / onboarding ------------------------------------
    InsuranceRiskRule(
        id="I001", name="Hit liste de sanctions", weight=1.00,
        label_fr="Client ou beneficiaire effectif figurant sur une liste de "
                 "sanctions nationale ou internationale (ONU, listes locales)",
        phase=Phase.KYC_ONBOARDING, category=Category.PROFIL_CLIENT,
        trigger_field="sanctions_list_hit",
        detected_by=(Owner.FRONT_OFFICE, Owner.CONFORMITE),
    ),
    InsuranceRiskRule(
        id="I002", name="Client ou BE personne politiquement exposee", weight=0.80,
        label_fr="Le souscripteur, le beneficiaire du contrat ou le beneficiaire "
                 "effectif d'une personne morale est une personne politiquement exposee",
        phase=Phase.KYC_ONBOARDING, category=Category.PROFIL_CLIENT,
        trigger_field="pep_involved",
        detected_by=(Owner.FRONT_OFFICE, Owner.CONFORMITE),
    ),
    InsuranceRiskRule(
        id="I003", name="Societe ecran", weight=0.75,
        label_fr="Le souscripteur ou le beneficiaire du contrat presente les "
                 "caracteristiques d'une societe fictive ou ecran",
        phase=Phase.KYC_ONBOARDING, category=Category.PROFIL_CLIENT,
        trigger_field="shell_company_involved",
        detected_by=(Owner.FRONT_OFFICE, Owner.CONFORMITE),
    ),
    InsuranceRiskRule(
        id="I004", name="Juridiction a haut risque", weight=0.70,
        label_fr="Client lie a un pays ou territoire identifie par le GAFI comme "
                 "presentant un risque eleve de blanchiment ou de financement du terrorisme",
        phase=Phase.KYC_ONBOARDING, category=Category.CANAL_GEO,
        trigger_field="high_risk_jurisdiction",
        detected_by=(Owner.FRONT_OFFICE, Owner.CONFORMITE),
    ),
    InsuranceRiskRule(
        id="I005", name="Documentation KYC insuffisante ou falsifiee", weight=0.50,
        label_fr="Absence, insuffisance ou incoherence des pieces d'identification "
                 "et de la documentation KYC, ou suspicion de falsification",
        phase=Phase.KYC_ONBOARDING, category=Category.PROFIL_CLIENT,
        trigger_field="kyc_documentation_deficient",
        detected_by=(Owner.FRONT_OFFICE, Owner.CONFORMITE),
    ),
    InsuranceRiskRule(
        id="I006", name="Beneficiaire effectif opaque", weight=0.40,
        label_fr="Structure de propriete complexe rendant difficile "
                 "l'identification du beneficiaire effectif",
        phase=Phase.KYC_ONBOARDING, category=Category.PROFIL_CLIENT,
        trigger_field="opaque_beneficial_ownership",
        detected_by=(Owner.CONFORMITE,),
    ),
    InsuranceRiskRule(
        id="I007", name="Changements frequents de coordonnees", weight=0.40,
        label_fr="Modifications repetees de l'adresse ou du domicile pouvant "
                 "indiquer une volonte de dissimuler la localisation reelle",
        phase=Phase.KYC_ONBOARDING, category=Category.PROFIL_CLIENT,
        trigger_field="frequent_address_changes",
        detected_by=(Owner.FRONT_OFFICE,),
    ),

    # ---- Phase 2: souscription ----------------------------------------
    InsuranceRiskRule(
        id="I008", name="Incoherence primes / revenus", weight=0.50,
        label_fr="Niveau de primes souscrites incompatible avec les revenus ou "
                 "la situation financiere declaree du client",
        phase=Phase.SOUSCRIPTION, category=Category.ORIGINE_FONDS,
        trigger_field="premium_income_mismatch",
        detected_by=(Owner.FRONT_OFFICE, Owner.DIRECTION_TECHNIQUE, Owner.CONFORMITE),
    ),
    InsuranceRiskRule(
        id="I009", name="Inadequation produit / profil", weight=0.40,
        label_fr="Produit d'assurance souscrit sans correspondance avec le "
                 "profil, le patrimoine ou les besoins du client",
        phase=Phase.SOUSCRIPTION, category=Category.COMPORTEMENT,
        trigger_field="product_profile_mismatch",
        detected_by=(Owner.FRONT_OFFICE, Owner.DIRECTION_TECHNIQUE),
    ),
    InsuranceRiskRule(
        id="I010", name="Capital assure anormalement eleve", weight=0.45,
        label_fr="Montant souscrit ou capital assure nettement superieur a la "
                 "moyenne observee pour des contrats similaires",
        phase=Phase.SOUSCRIPTION, category=Category.ORIGINE_FONDS,
        trigger_field="unusually_high_capital",
        detected_by=(Owner.DIRECTION_TECHNIQUE, Owner.CONFORMITE),
    ),
    InsuranceRiskRule(
        id="I011", name="Indifference aux conditions contractuelles", weight=0.35,
        label_fr="Desinteret manifeste pour le cout, le rendement ou les "
                 "conditions generales du contrat",
        phase=Phase.SOUSCRIPTION, category=Category.COMPORTEMENT,
        trigger_field="indifferent_to_terms",
        detected_by=(Owner.FRONT_OFFICE,),
    ),
    InsuranceRiskRule(
        id="I012", name="Focalisation sur les modalites de sortie", weight=0.50,
        label_fr="Interet exclusif pour les conditions de rachat ou de retrait "
                 "rapide plutot que pour la couverture offerte",
        phase=Phase.SOUSCRIPTION, category=Category.COMPORTEMENT,
        trigger_field="exit_focused_behaviour",
        detected_by=(Owner.FRONT_OFFICE,),
    ),
    InsuranceRiskRule(
        id="I013", name="Client sous controle d'un tiers", weight=0.40,
        label_fr="Client constamment dirige ou assiste par un tiers, suggerant "
                 "une situation de controle ou d'usurpation d'identite",
        phase=Phase.SOUSCRIPTION, category=Category.COMPORTEMENT,
        trigger_field="third_party_controlled",
        detected_by=(Owner.FRONT_OFFICE,),
    ),
    InsuranceRiskRule(
        id="I014", name="Intermediaire sans lien geographique", weight=0.35,
        label_fr="Souscription via un intermediaire sans lien geographique ou "
                 "economique avec le client, notamment en zone instable",
        phase=Phase.SOUSCRIPTION, category=Category.CANAL_GEO,
        trigger_field="unrelated_intermediary",
        detected_by=(Owner.FRONT_OFFICE, Owner.CONFORMITE),
    ),

    # ---- Phase 3: paiement de la prime --------------------------------
    InsuranceRiskRule(
        id="I015", name="Prime en especes au-dela du seuil", weight=0.60,
        label_fr="Paiement de primes en especes depassant le seuil reglementaire "
                 "applicable, notamment sur des produits classes a risque eleve",
        phase=Phase.PAIEMENT_PRIME, category=Category.ORIGINE_FONDS,
        trigger_field="cash_premium_above_threshold",
        detected_by=(Owner.FRONT_OFFICE, Owner.DIRECTION_FINANCIERE),
    ),
    InsuranceRiskRule(
        id="I016", name="Origine des fonds non justifiee", weight=0.60,
        label_fr="Aucune explication ni piece justificative ne permet d'etablir "
                 "la provenance licite des fonds",
        phase=Phase.PAIEMENT_PRIME, category=Category.ORIGINE_FONDS,
        trigger_field="unexplained_source_of_funds",
        detected_by=(Owner.CONFORMITE,),
    ),
    InsuranceRiskRule(
        id="I017", name="Paiement par un tiers sans lien", weight=0.55,
        label_fr="Primes versees par une personne physique ou morale etrangere "
                 "au contrat, sans lien familial ou commercial etabli",
        phase=Phase.PAIEMENT_PRIME, category=Category.BENEFICIAIRES,
        trigger_field="unrelated_third_party_payer",
        detected_by=(Owner.FRONT_OFFICE, Owner.DIRECTION_FINANCIERE, Owner.CONFORMITE),
    ),
    InsuranceRiskRule(
        id="I018", name="Paiements multi-devises en especes", weight=0.55,
        label_fr="Paiement de la prime ou de l'indemnisation en especes via "
                 "plusieurs devises differentes",
        phase=Phase.PAIEMENT_PRIME, category=Category.ORIGINE_FONDS,
        trigger_field="multi_currency_cash",
        detected_by=(Owner.FRONT_OFFICE, Owner.DIRECTION_FINANCIERE),
    ),
    InsuranceRiskRule(
        id="I019", name="Comptes ou sources multiples", weight=0.45,
        label_fr="Primes reglees depuis plusieurs comptes ou sources de fonds "
                 "differentes sans justification economique",
        phase=Phase.PAIEMENT_PRIME, category=Category.ORIGINE_FONDS,
        trigger_field="multiple_payment_sources",
        detected_by=(Owner.DIRECTION_FINANCIERE, Owner.CONFORMITE),
    ),
    InsuranceRiskRule(
        id="I020", name="Financement etranger sans justification", weight=0.50,
        label_fr="Paiements provenant d'un compte etranger sans lien documente "
                 "avec le souscripteur",
        phase=Phase.PAIEMENT_PRIME, category=Category.CANAL_GEO,
        trigger_field="unjustified_foreign_funding",
        detected_by=(Owner.DIRECTION_FINANCIERE, Owner.CONFORMITE),
    ),

    # ---- Phase 4: vie du contrat (avenants, avances, transferts) -------
    InsuranceRiskRule(
        id="I021", name="Modifications frequentes des beneficiaires", weight=0.50,
        label_fr="Clauses beneficiaires modifiees de maniere repetee sans "
                 "justification valable",
        phase=Phase.VIE_CONTRAT, category=Category.BENEFICIAIRES,
        trigger_field="frequent_beneficiary_changes",
        detected_by=(Owner.DIRECTION_PRODUCTION, Owner.CONFORMITE),
    ),
    InsuranceRiskRule(
        id="I022", name="Beneficiaire hors cercle proche", weight=0.50,
        label_fr="Substitution du beneficiaire ou transfert d'indemnites vers "
                 "une personne sans lien familial ou economique etabli",
        phase=Phase.VIE_CONTRAT, category=Category.BENEFICIAIRES,
        trigger_field="beneficiary_outside_close_circle",
        detected_by=(Owner.DIRECTION_PRODUCTION, Owner.CONFORMITE),
    ),
    InsuranceRiskRule(
        id="I023", name="Avances sur contrat repetees", weight=0.40,
        label_fr="Demandes repetees d'avances sur contrats vie ou capitalisation, "
                 "utilisant le contrat comme instrument de tresorerie",
        phase=Phase.VIE_CONTRAT, category=Category.COMPORTEMENT,
        trigger_field="repeated_policy_advances",
        detected_by=(Owner.DIRECTION_TECHNIQUE, Owner.CONFORMITE),
    ),
    InsuranceRiskRule(
        id="I024", name="Transfert vers un autre assureur malgre penalites", weight=0.45,
        label_fr="Transfert du contrat vers une autre compagnie apres une courte "
                 "periode, en acceptant des frais ou penalites eleves",
        phase=Phase.VIE_CONTRAT, category=Category.COMPORTEMENT,
        trigger_field="costly_early_transfer",
        detected_by=(Owner.DIRECTION_TECHNIQUE, Owner.CONFORMITE),
    ),

    # ---- Phase 5: rachat / indemnisation -------------------------------
    InsuranceRiskRule(
        id="I025", name="Rachat precoce malgre penalites", weight=0.70,
        label_fr="Rachat total ou partiel peu apres la souscription, le client "
                 "acceptant les penalites de sortie anticipee",
        phase=Phase.RACHAT_INDEMNISATION, category=Category.COMPORTEMENT,
        trigger_field="early_surrender",
        detected_by=(Owner.DIRECTION_PRODUCTION, Owner.CONFORMITE),
    ),
    InsuranceRiskRule(
        id="I026", name="Rachat au-dela du seuil sur produit a risque", weight=0.60,
        label_fr="Operation de rachat sur un produit classe a risque eleve "
                 "depassant le seuil reglementaire applicable",
        phase=Phase.RACHAT_INDEMNISATION, category=Category.ORIGINE_FONDS,
        trigger_field="surrender_above_threshold",
        detected_by=(Owner.DIRECTION_PRODUCTION, Owner.CONFORMITE),
    ),
    InsuranceRiskRule(
        id="I027", name="Indemnisation versee a un tiers sans lien", weight=0.55,
        label_fr="Prestation ou indemnisation versee a une personne exterieure "
                 "au contrat sans lien etabli avec l'assure",
        phase=Phase.RACHAT_INDEMNISATION, category=Category.BENEFICIAIRES,
        trigger_field="claim_paid_to_unrelated_party",
        detected_by=(Owner.DIRECTION_PRODUCTION, Owner.DIRECTION_FINANCIERE, Owner.CONFORMITE),
    ),

    # ---- Phase 6: controle / surveillance ------------------------------
    InsuranceRiskRule(
        id="I028", name="Contrats multiples lies", weight=0.30,
        label_fr="Plusieurs contrats ouverts par un meme client ou des clients "
                 "lies (meme adresse, meme beneficiaire) sans justification",
        phase=Phase.CONTROLE, category=Category.SURVEILLANCE,
        trigger_field="linked_multiple_contracts",
        detected_by=(Owner.CONFORMITE,),
    ),
    InsuranceRiskRule(
        id="I029", name="Meme beneficiaire effectif sur plusieurs contrats", weight=0.30,
        label_fr="Le meme beneficiaire effectif apparait sur plusieurs contrats "
                 "distincts sans justification economique",
        phase=Phase.CONTROLE, category=Category.SURVEILLANCE,
        trigger_field="same_beneficial_owner_across_contracts",
        detected_by=(Owner.CONFORMITE,),
    ),
]


# ---------------------------------------------------------------------------
# Scoring -- same capped-sum contract as banking mode
# ---------------------------------------------------------------------------

RULES_BY_TRIGGER: dict[str, InsuranceRiskRule] = {
    r.trigger_field: r for r in INSURANCE_RISK_RULES
}


def score_insurance_case(flags: dict) -> tuple[list[str], float, str]:
    """Score an insurance case from its extraction booleans.

    Args:
        flags: dict of trigger_field -> bool (from InsuranceCase model dump).

    Returns:
        (matched French labels, severity 0-1 capped, risk level string)
        Risk levels match RiskLevel enum values used in banking mode.
    """
    matched: list[str] = []
    total: float = 0.0

    for trigger, rule in RULES_BY_TRIGGER.items():
        if flags.get(trigger):
            matched.append(rule.label_fr)
            total += rule.weight

    severity = min(total, 1.0)

    if severity >= 0.6:
        level = "critical"
    elif severity >= 0.4:
        level = "high"
    elif severity >= 0.2:
        level = "medium"
    else:
        level = "low"

    return matched, severity, level
