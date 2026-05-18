"""OpenSanctions API wrapper for entity sanctions screening."""

import asyncio
import os
import structlog
import httpx
from typing import Optional

logger = structlog.get_logger()

OPENSANCTIONS_API_KEY: str = os.environ.get("OPENSANCTIONS_API_KEY", "")
OPENSANCTIONS_BASE_URL: str = "https://api.opensanctions.org"
MATCH_ENDPOINT: str = f"{OPENSANCTIONS_BASE_URL}/match/default"
REQUEST_TIMEOUT: float = 10.0


class SanctionsResult:
    """Result of a sanctions check for a single entity."""

    def __init__(self, entity_name: str, hit: bool, detail: Optional[str] = None) -> None:
        self.entity_name: str = entity_name
        self.hit: bool = hit
        self.detail: Optional[str] = detail

    def to_dict(self) -> dict:
        return {"hit": self.hit, "detail": self.detail}


def screen_entity(entity_name: str, case_id: str) -> SanctionsResult:
    """Screen a single entity name against OpenSanctions.

    Args:
        entity_name: Name of person or company to screen.
        case_id: Case ID for structured logging.

    Returns:
        SanctionsResult with hit status and detail if matched.
    """
    log = logger.bind(case_id=case_id, entity=entity_name)

    if not OPENSANCTIONS_API_KEY:
        log.warning("sanctions_api_key_missing", action="skipping_screen")
        return SanctionsResult(entity_name=entity_name, hit=False, detail=None)

    payload = {
        "queries": {
            "q1": {
                "schema": "Thing",
                "properties": {"name": [entity_name]},
            }
        }
    }

    headers = {
        "Authorization": f"ApiKey {OPENSANCTIONS_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            response = client.post(MATCH_ENDPOINT, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        results = data.get("responses", {}).get("q1", {}).get("results", [])
        if results:
            top = results[0]
            score = top.get("score", 0.0)
            if score >= 0.7:
                datasets = ", ".join(
                    top.get("datasets", [top.get("schema", "unknown")])
                )
                caption = top.get("caption", entity_name)
                detail = (
                    f"Match on {datasets} -- caption: {caption} "
                    f"(score: {score:.2f})"
                )
                log.info("sanctions_hit", score=score, datasets=datasets)
                return SanctionsResult(entity_name=entity_name, hit=True, detail=detail)

        log.info("sanctions_clear")
        return SanctionsResult(entity_name=entity_name, hit=False, detail=None)

    except httpx.TimeoutException:
        log.error("sanctions_timeout")
        return SanctionsResult(entity_name=entity_name, hit=False, detail=None)
    except httpx.HTTPStatusError as exc:
        log.error("sanctions_http_error", status=exc.response.status_code)
        return SanctionsResult(entity_name=entity_name, hit=False, detail=None)
    except Exception as exc:
        log.error("sanctions_unexpected_error", error=str(exc))
        return SanctionsResult(entity_name=entity_name, hit=False, detail=None)


def screen_entities(
    entity_names: list[str], case_id: str
) -> dict[str, dict]:
    """Screen multiple entity names against OpenSanctions (sequential, sync).

    Returns:
        Dict mapping entity_name -> {"hit": bool, "detail": str | None}
    """
    results: dict[str, dict] = {}
    for name in entity_names:
        result = screen_entity(name, case_id)
        results[name] = result.to_dict()
    return results


async def screen_entity_async(entity_name: str, case_id: str) -> SanctionsResult:
    """Async version of screen_entity using httpx.AsyncClient."""
    log = logger.bind(case_id=case_id, entity=entity_name)

    if not OPENSANCTIONS_API_KEY:
        log.warning("sanctions_api_key_missing", action="skipping_screen")
        return SanctionsResult(entity_name=entity_name, hit=False, detail=None)

    payload = {
        "queries": {
            "q1": {
                "schema": "Thing",
                "properties": {"name": [entity_name]},
            }
        }
    }
    headers = {
        "Authorization": f"ApiKey {OPENSANCTIONS_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.post(MATCH_ENDPOINT, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        results = data.get("responses", {}).get("q1", {}).get("results", [])
        if results:
            top = results[0]
            score = top.get("score", 0.0)
            if score >= 0.7:
                datasets = ", ".join(
                    top.get("datasets", [top.get("schema", "unknown")])
                )
                caption = top.get("caption", entity_name)
                detail = (
                    f"Match on {datasets} -- caption: {caption} "
                    f"(score: {score:.2f})"
                )
                log.info("sanctions_hit", score=score, datasets=datasets)
                return SanctionsResult(entity_name=entity_name, hit=True, detail=detail)

        log.info("sanctions_clear")
        return SanctionsResult(entity_name=entity_name, hit=False, detail=None)

    except httpx.TimeoutException:
        log.error("sanctions_timeout")
        return SanctionsResult(entity_name=entity_name, hit=False, detail=None)
    except httpx.HTTPStatusError as exc:
        log.error("sanctions_http_error", status=exc.response.status_code)
        return SanctionsResult(entity_name=entity_name, hit=False, detail=None)
    except Exception as exc:
        log.error("sanctions_unexpected_error", error=str(exc))
        return SanctionsResult(entity_name=entity_name, hit=False, detail=None)


async def screen_entities_async(
    entity_names: list[str], case_id: str
) -> dict[str, dict]:
    """Screen all entities in parallel using asyncio.gather.

    Returns:
        Dict mapping entity_name -> {"hit": bool, "detail": str | None}
    """
    results_list: list[SanctionsResult] = await asyncio.gather(
        *[screen_entity_async(name, case_id) for name in entity_names]
    )
    return {r.entity_name: r.to_dict() for r in results_list}
