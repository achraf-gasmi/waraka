# CLAUDE.md — Waraka v1
# STR Drafting Agent — Claude Code Project Context

Read WARAKA_SPEC.md first. This file is a summary. WARAKA_SPEC.md is authoritative.

## What this project is

Waraka is an AI-powered Suspicious Transaction Report (STR) drafting assistant
for Tunisian bank compliance officers. It takes French-language descriptions of
suspicious transactions and produces goAML-compatible STR XML drafts.

v1 = one agent only: STR Drafting Agent. Nothing else.

## Stack

Python 3.11 | LangGraph 1.0 | FastAPI | Streamlit | Claude API (claude-sonnet-4-6)
PostgreSQL | ChromaDB | Redis | structlog | Pydantic v2

## File ownership

- agents/str_agent.py       → prompts and node functions only
- tools/goaml_tool.py       → XML builder, no LLM
- tools/sanctions_tool.py   → OpenSanctions API wrapper
- tools/ner_tool.py         → entity extraction helper
- graph/str_graph.py        → LangGraph StateGraph, 5 nodes, linear
- models/schemas.py         → all Pydantic models, source of truth
- api/main.py               → FastAPI endpoints
- ui/app.py                 → Streamlit UI, French only

## Non-negotiable rules

1. Temperature = 0.0 always
2. Prompts = module-level constants always
3. LLM timeout = 30 seconds always
4. No DB writes in agent functions
5. No raw dicts across module boundaries — Pydantic only
6. All logging via structlog with case_id field
7. All text in UI is French
8. goaml_tool.py uses xml.etree.ElementTree only

## Build order

schemas.py → db/init.sql → goaml_tool → sanctions_tool → ner_tool
→ str_agent (prompts) → str_graph (nodes) → api/main → ui/app → tests → README

## Demo scenario

Input: "Notre client, la société Immobilière Carthage SARL (RC: B123456789, Tunis),
a effectué le 15 mars 2026 un virement de 850 000 TND vers Gulf Properties FZE
(Émirats Arabes Unis) via deux intermédiaires : Mediterranean Holdings Ltd (Malte)
et Atlantic Capital SA (Luxembourg). Aucun contrat fourni, aucune relation antérieure."

Expected: risk=CRITICAL, confidence≈0.85, 4+ risk indicators, valid goAML XML

*Owner: Achraf Gasmi — 2026-04-12*
