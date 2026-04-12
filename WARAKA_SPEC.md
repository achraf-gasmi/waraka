# WARAKA v1 — Implementation Specification
# STR Drafting Agent — Complete Build Spec for Claude Code

**Read this entire file before writing a single line of code.**
**Every decision in this file is final. Do not deviate without explicit instruction.**

---

## What you are building

A single-agent system that helps Tunisian bank compliance officers draft
goAML-compatible Suspicious Transaction Reports (STRs) in French.

The analyst describes a suspicious transaction in plain French text.
The system produces a structured STR draft in goAML XML format, ready for
human review and submission to CTAF via the goAML platform.

This is v1. Nothing else. No media screening. No regulatory monitoring.
No risk scoring model. Just the STR drafting agent.

---

## Project structure

```
waraka/
├── agents/
│   └── str_agent.py          # The single agent — all STR logic lives here
├── tools/
│   ├── sanctions_tool.py     # OpenSanctions API wrapper
│   ├── goaml_tool.py         # goAML XML builder + validator
│   └── ner_tool.py           # Entity extraction from French text
├── graph/
│   └── str_graph.py          # LangGraph StateGraph definition
├── models/
│   └── schemas.py            # All Pydantic models — source of truth
├── api/
│   └── main.py               # FastAPI — single POST /v1/str/draft endpoint
├── ui/
│   └── app.py                # Streamlit analyst interface
├── db/
│   ├── init.sql              # PostgreSQL schema
│   └── session.py            # SQLAlchemy async session
├── tests/
│   ├── conftest.py           # Fixtures and mock factories
│   ├── test_str_agent.py     # Agent unit tests
│   └── test_goaml_tool.py    # XML generation tests
├── docker-compose.yml        # PostgreSQL + ChromaDB + Redis
├── pyproject.toml
├── .env.example
└── CLAUDE.md                 # Claude Code project context
```

---

## Pydantic models — define these first, build everything else around them

```python
# models/schemas.py

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
```

---

## LangGraph graph — str_graph.py

```python
# graph/str_graph.py
# The StateGraph has exactly 5 nodes, executed in sequence.
# No cycles. No conditional branching in v1. Linear flow only.

from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END

class STRState(TypedDict):
    request: dict                   # STRDraftRequest as dict
    extracted_entities: list        # List of Entity dicts
    extracted_transaction: dict     # Transaction dict
    sanctions_results: dict         # {entity_name: {hit: bool, detail: str}}
    risk_indicators: list[str]
    narrative_fr: str
    goaml_xml: str
    confidence: float
    analyst_notes: list[str]
    errors: list[str]

# Node 1: extract_entities
# Input: state["request"]["analyst_input"]
# Output: state["extracted_entities"], state["extracted_transaction"]
# Uses: Claude API to extract structured entities and transaction from French text
# Prompt: MODULE-LEVEL CONSTANT (see agents/str_agent.py)

# Node 2: screen_sanctions
# Input: state["extracted_entities"]
# Output: state["sanctions_results"]
# Uses: sanctions_tool.py → OpenSanctions API
# If API fails: log error, continue with sanctions_checked=False

# Node 3: assess_risk
# Input: state["extracted_transaction"], state["sanctions_results"]
# Output: state["risk_indicators"], state["confidence"]
# Uses: Rule-based scoring (no ML in v1) — see RISK RULES below

# Node 4: generate_narrative
# Input: all state so far
# Output: state["narrative_fr"]
# Uses: Claude API to write a formal French compliance narrative
# Prompt: MODULE-LEVEL CONSTANT (see agents/str_agent.py)

# Node 5: build_goaml_xml
# Input: state["extracted_transaction"], state["narrative_fr"], state["risk_indicators"]
# Output: state["goaml_xml"]
# Uses: goaml_tool.py — deterministic XML builder, no LLM

graph = StateGraph(STRState)
graph.add_node("extract_entities", extract_entities_node)
graph.add_node("screen_sanctions", screen_sanctions_node)
graph.add_node("assess_risk", assess_risk_node)
graph.add_node("generate_narrative", generate_narrative_node)
graph.add_node("build_goaml_xml", build_goaml_xml_node)

graph.set_entry_point("extract_entities")
graph.add_edge("extract_entities", "screen_sanctions")
graph.add_edge("screen_sanctions", "assess_risk")
graph.add_edge("assess_risk", "generate_narrative")
graph.add_edge("generate_narrative", "build_goaml_xml")
graph.add_edge("build_goaml_xml", END)

str_graph = graph.compile()
```

---

## Agent prompts — all MODULE-LEVEL CONSTANTS in agents/str_agent.py

```python
# agents/str_agent.py

ENTITY_EXTRACTION_SYSTEM = """
Tu es un expert en conformité bancaire tunisienne spécialisé dans la lutte contre
le blanchiment d'argent (LBA). Tu analyses des descriptions de transactions
suspectes rédigées par des analystes de conformité.

Ta tâche est d'extraire de manière structurée :
1. Toutes les entités mentionnées (personnes physiques et morales)
2. Les détails de la ou des transactions
3. Les indicateurs de risque apparents

Réponds UNIQUEMENT en JSON valide. Aucun texte avant ou après le JSON.
Aucune balise markdown. Uniquement le JSON brut.

Format de réponse requis :
{
  "entities": [...],
  "transaction": {...},
  "initial_red_flags": [...]
}
"""

ENTITY_EXTRACTION_USER = """
Analyse la description suivante et extrait toutes les entités et transactions.

Description de l'analyste :
{analyst_input}

Institution déclarante : {reporting_institution}

Extrait :
- Toutes les personnes physiques et morales mentionnées
- Les montants, devises, dates
- Le type de transaction
- Les pays et juridictions impliqués
- Les intermédiaires éventuels
- Tout indicateur de risque apparent (structuration, pays à risque, PPE, etc.)
"""

NARRATIVE_GENERATION_SYSTEM = """
Tu es un expert en conformité bancaire tunisienne. Tu rédiges des déclarations
de soupçon formelles destinées à la Commission Tunisienne des Analyses
Financières (CTAF) via la plateforme goAML.

Le texte que tu produis doit :
- Être rédigé en français formel et juridique
- Respecter les standards de la CTAF (loi organique 2015-26 modifiée par 2019-9)
- Décrire objectivement les faits sans jugement définitif
- Mentionner explicitement les indicateurs de risque identifiés
- Être concis (300-500 mots maximum)
- Ne jamais inclure d'informations non mentionnées dans les données fournies

Commence directement le récit. Pas d'introduction comme "Voici le récit...".
"""

NARRATIVE_GENERATION_USER = """
Rédige le récit de la déclaration de soupçon à partir des éléments suivants :

Entités impliquées :
{entities_summary}

Transaction :
{transaction_summary}

Indicateurs de risque identifiés :
{risk_indicators}

Résultats de filtrage sanctions :
{sanctions_summary}

Institution déclarante : {reporting_institution}
Date de la déclaration : {declaration_date}
"""
```

---

## Risk rules — assess_risk_node (no ML in v1, pure rules)

```python
# In graph/str_graph.py — assess_risk_node function

HIGH_RISK_COUNTRIES = [
    "AE", "IR", "KP", "SY", "YE", "LY", "SD", "AF",  # FATF high-risk
    "VE", "MM", "NI", "PA", "UG",                       # FATF grey list
]

RISK_RULES = [
    {
        "id": "R001",
        "name": "Juridiction à haut risque",
        "check": lambda t: t["receiver"]["country"] in HIGH_RISK_COUNTRIES,
        "weight": 0.3,
        "label": "Transaction vers une juridiction à haut risque selon le GAFI"
    },
    {
        "id": "R002",
        "name": "Montant élevé non habituel",
        "check": lambda t: t["amount"] > 500_000,
        "weight": 0.2,
        "label": "Montant supérieur à 500 000 TND sans justification économique apparente"
    },
    {
        "id": "R003",
        "name": "Intermédiaires multiples",
        "check": lambda t: len(t.get("intermediaries", [])) >= 2,
        "weight": 0.25,
        "label": "Recours à plusieurs intermédiaires sans justification commerciale"
    },
    {
        "id": "R004",
        "name": "Hit sanctions",
        "check": lambda t, sanctions: any(v["hit"] for v in sanctions.values()),
        "weight": 0.4,
        "label": "Entité figurant sur une liste de sanctions internationale"
    },
    {
        "id": "R005",
        "name": "PPE impliqué",
        "check": lambda t: any(e.get("is_pep") for e in [t["sender"], t["receiver"]]),
        "weight": 0.3,
        "label": "Personne politiquement exposée impliquée dans la transaction"
    },
    {
        "id": "R006",
        "name": "Absence de relation antérieure",
        "check": lambda t: t.get("no_prior_relationship", False),
        "weight": 0.15,
        "label": "Aucune relation commerciale antérieure avec le bénéficiaire"
    },
]

# Confidence = sum of matched rule weights, capped at 1.0
# If confidence >= 0.6: risk_level = CRITICAL
# If confidence >= 0.4: risk_level = HIGH
# If confidence >= 0.2: risk_level = MEDIUM
# Else: risk_level = LOW
```

---

## goAML XML structure — goaml_tool.py

```python
# tools/goaml_tool.py
# Deterministic XML builder. No LLM. No randomness.
# Output must be valid goAML STR XML.

# The goAML STR XML structure (simplified for v1):
"""
<?xml version="1.0" encoding="UTF-8"?>
<report>
  <rentity_id>{reporting_entity_id}</rentity_id>
  <rentity_branch>{branch_id}</rentity_branch>
  <submission_code>E</submission_code>
  <report_code>STR</report_code>
  <entity_reference>{case_reference}</entity_reference>
  <fiu_ref_number/>
  <submission_date>{date}</submission_date>
  <currency_code_local>TND</currency_code_local>
  <reporting_person>
    <role>R</role>
    <occupation>COMPLIANCE_OFFICER</occupation>
  </reporting_person>
  <location>
    <address_type>B</address_type>
    <country>TN</country>
  </location>
  <transaction>
    <transactionnumber>{tx_id}</transactionnumber>
    <transaction_location>TN</transaction_location>
    <date_transaction>{tx_date}</date_transaction>
    <teller/>
    <authorized/>
    <amount_local>{amount}</amount_local>
    <t_from_my_client>
      <!-- sender details -->
    </t_from_my_client>
    <t_to_my_client>
      <!-- receiver details -->
    </t_to_my_client>
  </transaction>
  <narrative>{narrative_fr}</narrative>
</report>
"""

def build_str_xml(transaction: dict, narrative: str, case_ref: str) -> str:
    """Build goAML-compatible STR XML from structured data."""
    # Use xml.etree.ElementTree — no external dependencies
    # Validate against basic schema rules before returning
    # Return XML string
    pass

def validate_str_xml(xml_string: str) -> tuple[bool, list[str]]:
    """Validate XML structure. Returns (is_valid, list_of_errors)."""
    pass
```

---

## FastAPI endpoint — api/main.py

```python
# Single endpoint for v1

POST /v1/str/draft
Content-Type: application/json
Authorization: Bearer {WARAKA_API_KEY}

# Request body: STRDraftRequest
# Response body: STRDraftResult
# Response time target: < 30 seconds (LLM calls take time)
# On timeout: return 202 Accepted with case_id, poll /v1/str/{case_id}

GET /v1/str/{case_id}
# Returns CaseRecord

POST /v1/str/{case_id}/approve
# Analyst approves or corrects the draft
# Body: {"approved": bool, "corrections": str | null}
# Writes to ciq_corrections table

GET /health
# Returns {"status": "ok", "version": "1.0.0"}
```

---

## PostgreSQL schema — db/init.sql

```sql
CREATE TABLE war_cases (
    case_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analyst_id    VARCHAR(100) NOT NULL,
    institution   VARCHAR(200) NOT NULL,
    input_text    TEXT NOT NULL,
    status        VARCHAR(20) NOT NULL DEFAULT 'draft',
    confidence    NUMERIC(4,3),
    goaml_xml     TEXT,
    narrative_fr  TEXT,
    risk_level    VARCHAR(20),
    submitted     BOOLEAN DEFAULT FALSE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE war_entities (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id       UUID REFERENCES war_cases(case_id),
    name          VARCHAR(500) NOT NULL,
    name_arabic   VARCHAR(500),
    entity_type   VARCHAR(20) NOT NULL,
    is_pep        BOOLEAN DEFAULT FALSE,
    sanctions_hit BOOLEAN DEFAULT FALSE,
    sanctions_data JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE war_corrections (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id       UUID REFERENCES war_cases(case_id),
    analyst_id    VARCHAR(100) NOT NULL,
    approved      BOOLEAN NOT NULL,
    corrections   TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_cases_analyst ON war_cases(analyst_id);
CREATE INDEX idx_cases_status ON war_cases(status);
CREATE INDEX idx_entities_case ON war_entities(case_id);
```

---

## Streamlit UI — ui/app.py

```
Three sections only:

[LEFT SIDEBAR]
- Institution name (text input)
- Analyst ID (text input)
- Case reference (optional text input)
- "Analyser la transaction" button

[MAIN AREA — TOP]
- Large textarea: "Décrivez la transaction suspecte en français"
  Placeholder: "Ex: Un client de la banque a effectué un virement de 850 000 TND
  vers une société aux Émirats Arabes Unis via deux intermédiaires au Luxembourg..."

[MAIN AREA — BOTTOM, shown after analysis]
Tab 1: Résumé
  - Risk level badge (color-coded)
  - Confidence score
  - Entities detected (table)
  - Risk indicators (bulleted list)
  - Sanctions hits (highlighted if any)

Tab 2: Récit
  - Generated French narrative (editable text area)

Tab 3: XML goAML
  - Generated XML (read-only code block)
  - Download button

Tab 4: Validation
  - "Approuver" button (green)
  - "Corriger" button (opens text area for corrections)
  - Correction text area
  - "Soumettre les corrections" button
```

---

## Environment variables — .env.example

```
ANTHROPIC_API_KEY=
WARAKA_API_KEY=waraka-dev-key-change-in-prod
DATABASE_URL=postgresql+asyncpg://waraka:waraka@localhost:5432/waraka
OPENSANCTIONS_API_KEY=
LANGSMITH_API_KEY=
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=waraka-v1
LOG_LEVEL=INFO
ENVIRONMENT=development
```

---

## docker-compose.yml

```yaml
version: "3.9"
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: waraka
      POSTGRES_PASSWORD: waraka
      POSTGRES_DB: waraka
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./db/init.sql:/docker-entrypoint-initdb.d/init.sql

  chromadb:
    image: chromadb/chroma:latest
    ports:
      - "8000:8000"
    volumes:
      - chroma_data:/chroma/chroma

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

volumes:
  postgres_data:
  chroma_data:
```

---

## Hard rules for Claude Code

1. Temperature is ALWAYS 0.0 for all LLM calls. Non-negotiable.
2. All prompts are MODULE-LEVEL CONSTANTS. Never construct prompts inside functions.
3. All LLM calls have timeout=30.0. Handle anthropic.APITimeoutError explicitly.
4. All agent outputs are Pydantic-validated. No raw dicts cross module boundaries.
5. No database writes inside agent functions. Only api/main.py writes to DB.
6. Use structlog for all logging. Every log entry includes case_id.
7. The goaml_tool.py uses xml.etree.ElementTree only. No lxml, no external XML libs.
8. Use asyncpg + SQLAlchemy async for all DB operations. No synchronous DB calls.
9. French is the default language for all user-facing text. No English in the UI.
10. Every function has type hints. No untyped code.

---

## Test fixtures — conftest.py

```python
# tests/conftest.py

MOCK_ANALYST_INPUT = """
Notre client, la société Immobilière Carthage SARL (RC: B123456789, Tunis),
a effectué le 15 mars 2026 un virement de 850 000 TND vers une société
dénommée Gulf Properties FZE, domiciliée aux Émirats Arabes Unis (Abu Dhabi),
via deux sociétés intermédiaires : une à Malte (Mediterranean Holdings Ltd)
et une au Luxembourg (Atlantic Capital SA). Le client affirme qu'il s'agit
d'un investissement immobilier, mais aucun contrat n'a été fourni. Aucune
relation commerciale antérieure avec les bénéficiaires n'existe dans nos
systèmes. Le profil risque du client est classé moyen.
"""

EXPECTED_RISK_LEVEL = "critical"
EXPECTED_RISK_INDICATORS_MIN = 3  # At minimum: high-risk jurisdiction + intermediaries + no prior relationship
EXPECTED_ENTITY_COUNT = 4  # Carthage SARL, Gulf Properties, Mediterranean Holdings, Atlantic Capital

MOCK_SANCTIONS_RESPONSE_CLEAN = {
    "Immobilière Carthage SARL": {"hit": False, "detail": None},
    "Gulf Properties FZE": {"hit": False, "detail": None},
    "Mediterranean Holdings Ltd": {"hit": False, "detail": None},
    "Atlantic Capital SA": {"hit": False, "detail": None},
}

MOCK_SANCTIONS_RESPONSE_HIT = {
    "Gulf Properties FZE": {
        "hit": True,
        "detail": "Listed on OFAC SDN list — designation date 2024-03-15"
    },
}
```

---

## Build order — follow this exactly

```
Step 1: docker-compose up -d
Step 2: models/schemas.py
Step 3: db/init.sql + db/session.py
Step 4: tools/goaml_tool.py (+ tests)
Step 5: tools/sanctions_tool.py (+ tests)
Step 6: tools/ner_tool.py (+ tests)
Step 7: agents/str_agent.py (prompts only — no logic yet)
Step 8: graph/str_graph.py (nodes + graph)
Step 9: api/main.py
Step 10: ui/app.py
Step 11: Full integration test with MOCK_ANALYST_INPUT
Step 12: README.md
```

---

## Demo scenario — use this for the README and Streamlit demo

Input text (paste this into the UI):
"Notre client, la société Immobilière Carthage SARL (RC: B123456789, Tunis),
a effectué le 15 mars 2026 un virement de 850 000 TND vers une société dénommée
Gulf Properties FZE, domiciliée aux Émirats Arabes Unis, via deux intermédiaires :
Mediterranean Holdings Ltd (Malte) et Atlantic Capital SA (Luxembourg). Le client
invoque un investissement immobilier mais n'a fourni aucun contrat. Aucune relation
commerciale antérieure n'existe avec les bénéficiaires."

Expected outputs:
- Risk level: CRITICAL
- Confidence: ~0.85
- Risk indicators: juridiction à haut risque, intermédiaires multiples,
  absence de relation antérieure, montant élevé
- Narrative: formal French compliance text
- XML: valid goAML STR-T structure

*Last updated: 2026-04-12. Owner: Achraf Gasmi.*
