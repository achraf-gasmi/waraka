"""FastAPI application -- Waraka STR Drafting API v1."""

import hmac
import os
import uuid
import time
from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import FastAPI, HTTPException, Depends, Header, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_session
from graph.str_graph import run_str_graph
from models.schemas import (
    STRDraftRequest,
    STRDraftResult,
    CaseRecord,
    Entity,
    Transaction,
    RiskLevel,
)

logger = structlog.get_logger()

app = FastAPI(
    title="Waraka STR Drafting API",
    description="AI-powered Suspicious Transaction Report drafting for Tunisian banks",
    version="1.0.0",
)

_DEFAULT_WARAKA_API_KEY: str = "waraka-dev-key-change-in-prod"

ENVIRONMENT: str = os.environ.get("ENVIRONMENT", "")
WARAKA_API_KEY: str = os.environ.get("WARAKA_API_KEY", _DEFAULT_WARAKA_API_KEY)


# ---------------------------------------------------------------------------
# Startup safety check
# ---------------------------------------------------------------------------

def _check_production_key_safety(environment: str, api_key: str) -> None:
    """Refuse to run with the default API key unless explicitly in development.

    ENVIRONMENT is treated as "not development" whenever it isn't literally
    "development" -- including when it's unset. A deployment that forgot to
    set ENVIRONMENT is much more likely to be a mis-configured production box
    than an intentional local sandbox, so an unset value must fail closed
    rather than silently allow the well-known default key to keep working.
    """
    if environment != "development" and api_key == _DEFAULT_WARAKA_API_KEY:
        raise RuntimeError(
            "WARAKA_API_KEY is still the default value "
            f"'{_DEFAULT_WARAKA_API_KEY}' and ENVIRONMENT={environment!r} is not "
            "'development'. Refusing to start. Set WARAKA_API_KEY to a real "
            "secret, or set ENVIRONMENT=development for local use."
        )


@app.on_event("startup")
async def _startup_security_check() -> None:
    _check_production_key_safety(ENVIRONMENT, WARAKA_API_KEY)


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

def _compute_sanctions_status(entities: list[Entity]) -> str:
    """Summarize per-entity sanctions_status into an API-level signal.

    Returns "all_screened" only if every entity was actually screened;
    otherwise "partial" or "none_screened" so callers can't mistake an
    incomplete check for a clean one.
    """
    if not entities:
        return "none_screened"
    screened = sum(1 for e in entities if e.sanctions_status == "screened")
    if screened == len(entities):
        return "all_screened"
    if screened == 0:
        return "none_screened"
    return "partial"


def verify_api_key(authorization: Optional[str] = Header(default=None)) -> None:
    """Verify Bearer token matches WARAKA_API_KEY."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing or malformed",
        )
    token = authorization.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(token, WARAKA_API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "1.0.0"}


@app.post(
    "/v1/str/draft",
    response_model=STRDraftResult,
    dependencies=[Depends(verify_api_key)],
    summary="Draft a Suspicious Transaction Report",
)
async def draft_str(
    request: STRDraftRequest,
    session: AsyncSession = Depends(get_session),
) -> STRDraftResult:
    """Accept a French-language description and return a goAML STR draft."""
    case_id = str(uuid.uuid4())
    log = logger.bind(case_id=case_id, analyst_id=request.analyst_id)
    log.info(
        "str_draft_request_received",
        institution=request.reporting_institution,
        sector=request.sector,
    )

    start_ms = int(time.time() * 1000)

    request_dict = request.model_dump()
    request_dict["case_id"] = case_id

    try:
        final_state = await run_str_graph(request_dict)
    except Exception as exc:
        log.error("graph_execution_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Graph execution failed: {exc}",
        )

    latency_ms = int(time.time() * 1000) - start_ms

    entities_raw = final_state.get("extracted_entities", [])
    tx_raw = final_state.get("extracted_transaction", {})

    entities: list[Entity] = []
    for e in entities_raw:
        try:
            entities.append(Entity(**e))
        except Exception:
            pass

    transaction: Optional[Transaction] = None
    if tx_raw:
        try:
            transaction = Transaction(**tx_raw)
        except Exception:
            pass

    risk_score = final_state.get("risk_score", 0.0)
    risk_level_str = final_state.get("risk_level", RiskLevel.LOW.value)

    errors = final_state.get("errors", [])
    status_str = "error" if errors else ("draft" if risk_score >= 0.4 else "needs_review")

    result = STRDraftResult(
        case_id=case_id,
        status=status_str,
        risk_score=risk_score,
        extracted_entities=entities,
        extracted_transaction=transaction,
        risk_indicators=final_state.get("risk_indicators", []),
        narrative_fr=final_state.get("narrative_fr", ""),
        goaml_xml=final_state.get("goaml_xml", ""),
        sanctions_checked=bool(final_state.get("sanctions_results")),
        sanctions_status=_compute_sanctions_status(entities),
        analyst_notes=final_state.get("analyst_notes", []),
        latency_ms=latency_ms,
        created_at=datetime.now(timezone.utc),
    )

    # Persist to DB -- only api/main.py writes to DB
    try:
        await session.execute(
            text("""
                INSERT INTO war_cases
                    (case_id, analyst_id, institution, input_text, status,
                     confidence, goaml_xml, narrative_fr, risk_level, submitted,
                     created_at, updated_at)
                VALUES
                    (:case_id, :analyst_id, :institution, :input_text, :status,
                     :confidence, :goaml_xml, :narrative_fr, :risk_level, false,
                     NOW(), NOW())
            """),
            {
                "case_id": case_id,
                "analyst_id": request.analyst_id,
                "institution": request.reporting_institution,
                "input_text": request.analyst_input,
                "status": status_str,
                "confidence": risk_score,
                "goaml_xml": result.goaml_xml,
                "narrative_fr": result.narrative_fr,
                "risk_level": risk_level_str,
            },
        )

        for entity in entities:
            await session.execute(
                text("""
                    INSERT INTO war_entities
                        (case_id, name, name_arabic, entity_type, is_pep,
                         sanctions_hit, sanctions_data)
                    VALUES
                        (:case_id, :name, :name_arabic, :entity_type, :is_pep,
                         :sanctions_hit, :sanctions_data::jsonb)
                """),
                {
                    "case_id": case_id,
                    "name": entity.name,
                    "name_arabic": entity.name_arabic,
                    "entity_type": entity.entity_type,
                    "is_pep": entity.is_pep,
                    "sanctions_hit": entity.sanctions_hit,
                    "sanctions_data": (
                        f'{{"detail": "{entity.sanctions_detail}"}}'
                        if entity.sanctions_detail
                        else "null"
                    ),
                },
            )

        await session.commit()
        log.info("case_persisted")
    except Exception as exc:
        log.error("db_write_failed", error=str(exc))
        # Do not raise -- return result even if DB write fails

    log.info("str_draft_complete", latency_ms=latency_ms, status=status_str)
    return result


@app.get(
    "/v1/str/{case_id}",
    response_model=dict,
    dependencies=[Depends(verify_api_key)],
    summary="Get a case record by case ID",
)
async def get_case(
    case_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Retrieve a case record from the database."""
    log = logger.bind(case_id=case_id)

    try:
        row = await session.execute(
            text("SELECT * FROM war_cases WHERE case_id = :case_id"),
            {"case_id": case_id},
        )
        record = row.mappings().first()
    except Exception as exc:
        log.error("db_read_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Database error")

    if not record:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    return dict(record)


@app.post(
    "/v1/str/{case_id}/approve",
    dependencies=[Depends(verify_api_key)],
    summary="Approve or correct a draft STR",
)
async def approve_case(
    case_id: str,
    body: dict,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Record analyst approval or corrections for a draft."""
    log = logger.bind(case_id=case_id)

    approved: bool = bool(body.get("approved", False))
    corrections: Optional[str] = body.get("corrections")
    analyst_id: str = body.get("analyst_id", "unknown")

    try:
        await session.execute(
            text("""
                INSERT INTO war_corrections (case_id, analyst_id, approved, corrections)
                VALUES (:case_id, :analyst_id, :approved, :corrections)
            """),
            {
                "case_id": case_id,
                "analyst_id": analyst_id,
                "approved": approved,
                "corrections": corrections,
            },
        )
        new_status = "approved" if approved else "needs_review"
        await session.execute(
            text("""
                UPDATE war_cases
                SET status = :status, updated_at = NOW()
                WHERE case_id = :case_id
            """),
            {"case_id": case_id, "status": new_status},
        )
        await session.commit()
        log.info("case_approved", approved=approved)
    except Exception as exc:
        log.error("approval_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Approval write failed")

    return {"case_id": case_id, "approved": approved, "status": new_status}
