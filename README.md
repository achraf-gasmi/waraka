# Waraka v1 -- STR Drafting Agent

AI-powered Suspicious Transaction Report drafting assistant for Tunisian bank compliance officers.

Takes plain French descriptions of suspicious transactions and produces goAML-compatible STR XML drafts, ready for human review and submission to CTAF.

**Owner:** Achraf Gasmi | **Version:** 1.0.0 | **Date:** 2026-04-12

---

## What it does

1. Analyst describes a suspicious transaction in plain French
2. Waraka extracts entities and transaction details via Claude
3. Screens all entities against OpenSanctions
4. Applies rule-based risk scoring (6 FATF-aligned rules)
5. Generates a formal French compliance narrative
6. Produces a valid goAML STR-T XML file
7. Analyst reviews, corrects if needed, and approves

---

## Stack

| Component | Technology |
|---|---|
| Agent framework | LangGraph 1.0 |
| LLM | Claude Sonnet 4.6 (temperature=0.0) |
| API | FastAPI |
| UI | Streamlit (French only) |
| Database | PostgreSQL 16 |
| Vector DB | ChromaDB |
| Cache | Redis 7 |
| Sanctions | OpenSanctions API |

---

## Project structure

```
waraka/
├── agents/str_agent.py       # Prompts (module-level constants) + LLM helper
├── tools/
│   ├── goaml_tool.py         # goAML XML builder (xml.etree.ElementTree only)
│   ├── sanctions_tool.py     # OpenSanctions API wrapper
│   └── ner_tool.py           # Entity extraction / JSON parsing helper
├── graph/str_graph.py        # LangGraph StateGraph -- 5 nodes, linear
├── models/schemas.py         # All Pydantic models (source of truth)
├── api/main.py               # FastAPI -- 3 endpoints
├── ui/app.py                 # Streamlit analyst interface
├── db/
│   ├── init.sql              # PostgreSQL schema
│   └── session.py            # SQLAlchemy async session
├── tests/
│   ├── conftest.py           # Fixtures and mock data
│   ├── test_str_agent.py     # Agent + graph tests
│   ├── test_goaml_tool.py    # XML builder tests
│   ├── test_ner_tool.py      # Entity parsing tests
│   └── test_sanctions_tool.py# Sanctions wrapper tests
├── docker-compose.yml
├── pyproject.toml
└── .env.example
```

---

## Quick start

### 1. Prerequisites

- Python 3.11+
- Docker Desktop
- Anthropic API key

### 2. Start infrastructure

```bash
docker compose up -d
```

This starts PostgreSQL (port 5432), ChromaDB (port 8000), and Redis (port 6379).

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY
```

### 4. Install dependencies

```bash
pip install -e ".[dev]"
```

### 5. Run tests

```bash
pytest tests/
# 38 tests pass without API key (1 live test skipped)
# Set ANTHROPIC_API_KEY to run live integration test
```

### 6. Start the API

```bash
uvicorn api.main:app --port 8080 --reload
```

### 7. Start the UI

```bash
streamlit run ui/app.py
```

---

## API reference

### POST /v1/str/draft

Draft a Suspicious Transaction Report.

**Headers:** `Authorization: Bearer {WARAKA_API_KEY}`

**Request body:**
```json
{
  "analyst_input": "Description en francais de la transaction suspecte...",
  "reporting_institution": "BH Bank",
  "analyst_id": "ANA-001",
  "case_reference": "CAS-2026-001"
}
```

**Response:** `STRDraftResult` with risk level, entities, narrative, and goAML XML.

### GET /v1/str/{case_id}

Retrieve a case record.

### POST /v1/str/{case_id}/approve

Record analyst approval or corrections.

```json
{"approved": true, "analyst_id": "ANA-001", "corrections": null}
```

### GET /health

Returns `{"status": "ok", "version": "1.0.0"}`.

---

## Demo scenario

**Input (paste into the UI):**

```
Notre client, la societe Immobiliere Carthage SARL (RC: B123456789, Tunis),
a effectue le 15 mars 2026 un virement de 850 000 TND vers une societe
denommee Gulf Properties FZE, domiciliee aux Emirats Arabes Unis (Abu Dhabi),
via deux intermediaires : Mediterranean Holdings Ltd (Malte) et
Atlantic Capital SA (Luxembourg). Le client invoque un investissement
immobilier mais n'a fourni aucun contrat ni justificatif economique.
Aucune relation commerciale anterieure n'existe avec les beneficiaires.
```

**Expected output:**

| Field | Expected |
|---|---|
| Risk level | CRITIQUE |
| Confidence | 0.85 -- 0.92 |
| Risk indicators | >= 4 |
| Entities | 4 |
| goAML XML | Valid STR-T structure |
| Narrative | 300 -- 500 mots en francais formel |

**Risk indicators detected:**
1. Transaction vers une juridiction a haut risque (EAU -- GAFI)
2. Recours a plusieurs intermediaires sans justification commerciale
3. Absence de relation commerciale anterieure avec les beneficiaires
4. Montant superieur a 500 000 TND sans justification economique apparente

---

## Risk scoring rules

| Rule | Condition | Weight |
|---|---|---|
| R001 | Destination country on FATF high-risk list | 0.30 |
| R002 | Amount > 500 000 TND | 0.20 |
| R003 | >= 2 intermediaries | 0.25 |
| R004 | Sanctions hit on any entity | 0.40 |
| R005 | Sender or receiver is PEP | 0.30 |
| R006 | No prior business relationship | 0.15 |

Confidence = sum of matched weights (capped at 1.0).
CRITICAL >= 0.6 | HIGH >= 0.4 | MEDIUM >= 0.2 | LOW < 0.2

---

## Non-negotiable implementation rules

1. Temperature = 0.0 for all LLM calls
2. All prompts are module-level constants
3. LLM timeout = 30 seconds
4. No DB writes inside agent functions
5. No raw dicts across module boundaries -- Pydantic only
6. All logging via structlog with case_id field
7. All UI text is French
8. goaml_tool.py uses xml.etree.ElementTree only

---

## Regulatory context

- **Primary law:** Loi organique n° 2015-26 (modifiee par 2019-9)
- **Key circulaire:** BCT n° 2025-17 (22 decembre 2025) -- mandate goAML filing
- **Regulator:** CTAF (Commission Tunisienne des Analyses Financieres)
- **FIU platform:** goAML (UNODC)

---

## Environment variables

| Variable | Description | Default |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude API key | required |
| `WARAKA_API_KEY` | API bearer token | `waraka-dev-key-change-in-prod` |
| `DATABASE_URL` | PostgreSQL connection | `postgresql+asyncpg://waraka:waraka@localhost:5432/waraka` |
| `OPENSANCTIONS_API_KEY` | OpenSanctions API key | optional (screening skipped if absent) |
| `LANGSMITH_API_KEY` | LangSmith tracing | optional |
| `LOG_LEVEL` | Structlog level | `INFO` |
