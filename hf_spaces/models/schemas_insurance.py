"""Insurance-mode Pydantic models for Waraka.

Mirrors the style of models/schemas.py (banking mode). An InsuranceCase
is to insurance mode what Transaction is to banking mode: the structured
object the LLM extraction node fills, whose boolean flags drive
rule-based scoring in rules_insurance.py.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from models.schemas import Entity  # reuse existing Entity model


class InsuranceProductType(str, Enum):
    VIE = "assurance_vie"
    CAPITALISATION = "capitalisation"
    TRANSPORT = "assurance_transport"
    AUTOMOBILE = "assurance_automobile"
    SANTE = "assurance_sante"
    MULTIRISQUE = "multirisque"
    AUTRE = "autre"


class ProductRiskClass(str, Enum):
    """Product-level AML risk class per the insurer's own risk mapping."""
    ELEVE = "eleve"
    MOYEN = "moyen"
    FAIBLE = "faible"


class OperationType(str, Enum):
    SOUSCRIPTION = "souscription"
    PAIEMENT_PRIME = "paiement_prime"
    AVENANT = "avenant"
    AVANCE = "avance_sur_contrat"
    RACHAT_PARTIEL = "rachat_partiel"
    RACHAT_TOTAL = "rachat_total"
    INDEMNISATION = "indemnisation"
    TRANSFERT = "transfert"


class PaymentMethod(str, Enum):
    VIREMENT = "virement"
    ESPECES = "especes"
    CHEQUE = "cheque"
    CARTE = "carte"
    AUTRE = "autre"


class InsuranceCase(BaseModel):
    """Structured representation of a suspicious insurance operation.

    Boolean flags map 1:1 to trigger_field values in
    rules_insurance.INSURANCE_RISK_RULES. The extraction prompt must set
    each flag true only when the analyst's text establishes it
    explicitly or implicitly -- except the jurisdiction_* flags below,
    which are never asked of the LLM (rule.llm_extracted=False) and are
    instead computed deterministically by
    rules_insurance.compute_jurisdiction_flags() from party countries.
    """

    case_id: str
    operation_type: OperationType
    operation_date: Optional[datetime] = None

    # ---- contract ------------------------------------------------------
    policy_reference: Optional[str] = None
    product_type: InsuranceProductType = InsuranceProductType.AUTRE
    product_risk_class: ProductRiskClass = ProductRiskClass.FAIBLE
    sum_assured: Optional[float] = None
    currency: str = "TND"

    # ---- parties -------------------------------------------------------
    souscripteur: Entity
    assure: Optional[Entity] = None            # insured person if != subscriber
    beneficiaires: list[Entity] = []
    payeur: Optional[Entity] = None            # premium payer if != subscriber
    intermediaire: Optional[Entity] = None     # broker / agent

    # ---- operation amounts --------------------------------------------
    amount: Optional[float] = None             # premium / surrender / claim amount
    payment_method: Optional[PaymentMethod] = None

    description: Optional[str] = None
    red_flags: list[str] = []

    # ---- KYC / onboarding flags (I001-I007) ---------------------------
    sanctions_list_hit: bool = False
    pep_involved: bool = False
    shell_company_involved: bool = False
    # Computed, not LLM-set -- see rules_insurance.compute_jurisdiction_flags()
    jurisdiction_call_for_action: bool = False
    jurisdiction_enhanced_dd: bool = False
    jurisdiction_greylist: bool = False
    kyc_documentation_deficient: bool = False
    opaque_beneficial_ownership: bool = False
    frequent_address_changes: bool = False

    # ---- souscription flags (I008-I014) -------------------------------
    premium_income_mismatch: bool = False
    product_profile_mismatch: bool = False
    unusually_high_capital: bool = False
    indifferent_to_terms: bool = False
    exit_focused_behaviour: bool = False
    third_party_controlled: bool = False
    unrelated_intermediary: bool = False

    # ---- paiement flags (I015-I020) -----------------------------------
    cash_premium_above_threshold: bool = False
    unexplained_source_of_funds: bool = False
    unrelated_third_party_payer: bool = False
    multi_currency_cash: bool = False
    multiple_payment_sources: bool = False
    unjustified_foreign_funding: bool = False

    # ---- vie du contrat flags (I021-I024) -----------------------------
    frequent_beneficiary_changes: bool = False
    beneficiary_outside_close_circle: bool = False
    repeated_policy_advances: bool = False
    costly_early_transfer: bool = False

    # ---- rachat / indemnisation flags (I025-I027) ---------------------
    early_surrender: bool = False
    surrender_above_threshold: bool = False
    claim_paid_to_unrelated_party: bool = False

    # ---- controle flags (I028-I029) -----------------------------------
    linked_multiple_contracts: bool = False
    same_beneficial_owner_across_contracts: bool = False

    def risk_flags(self) -> dict:
        """Return only the boolean trigger fields, for score_insurance_case()."""
        from graph.rules_insurance import RULES_BY_TRIGGER
        data = self.model_dump()
        return {k: data[k] for k in RULES_BY_TRIGGER if k in data}
