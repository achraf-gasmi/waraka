from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum
from typing import Optional


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TransactionType(str, Enum):
    WIRE = "virement"
    CASH = "especes"
    CHEQUE = "cheque"
    CRYPTO = "crypto"
    OTHER = "autre"


class Entity(BaseModel):
    name: str
    name_arabic: Optional[str] = None
    entity_type: str                    # "person" | "company"
    id_number: Optional[str] = None     # CIN, passeport, RC
    nationality: Optional[str] = None   # ISO 3166-1 alpha-2
    country: Optional[str] = None
    address: Optional[str] = None
    is_pep: bool = False
    sanctions_hit: bool = False
    sanctions_detail: Optional[str] = None


class Transaction(BaseModel):
    transaction_id: str
    date: datetime
    amount: float
    currency: str = "TND"
    transaction_type: TransactionType
    sender: Entity
    receiver: Entity
    intermediaries: list[Entity] = []
    description: Optional[str] = None
    red_flags: list[str] = []


class STRDraftRequest(BaseModel):
    analyst_input: str          # Free French text describing the suspicious case
    reporting_institution: str  # Bank name
    analyst_id: str
    case_reference: Optional[str] = None


class STRDraftResult(BaseModel):
    case_id: str
    status: str                         # "draft" | "needs_review" | "error"
    confidence: float                   # 0.0 - 1.0
    extracted_entities: list[Entity]
    extracted_transaction: Optional[Transaction]
    risk_indicators: list[str]
    narrative_fr: str                   # Human-readable French narrative
    goaml_xml: str                      # Valid goAML STR XML string
    sanctions_checked: bool
    analyst_notes: list[str]            # What the agent flagged for human review
    latency_ms: int
    created_at: datetime


class CaseRecord(BaseModel):
    case_id: str
    request: STRDraftRequest
    result: STRDraftResult
    analyst_approved: Optional[bool] = None
    analyst_corrections: Optional[str] = None
    submitted_to_ctaf: bool = False
    created_at: datetime
    updated_at: datetime
