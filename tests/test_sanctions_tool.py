"""Tests for tools/sanctions_tool.py"""

import pytest
from unittest.mock import patch, MagicMock
import httpx
from tools.sanctions_tool import screen_entity, screen_entities, SanctionsResult


CASE_ID = "TEST-CASE-001"


def test_screen_entity_no_api_key():
    """Without API key, returns clean result and does not call API."""
    with patch("tools.sanctions_tool.OPENSANCTIONS_API_KEY", ""):
        result = screen_entity("Gulf Properties FZE", CASE_ID)
    assert isinstance(result, SanctionsResult)
    assert result.hit is False
    assert result.detail is None


def test_screen_entity_hit(mocker):
    """Returns hit=True when API returns a high-score match."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "responses": {
            "q1": {
                "results": [
                    {
                        "score": 0.95,
                        "caption": "Gulf Properties FZE",
                        "datasets": ["ofac_sdn"],
                        "schema": "Company",
                    }
                ]
            }
        }
    }
    mock_response.raise_for_status = MagicMock()

    mocker.patch("tools.sanctions_tool.OPENSANCTIONS_API_KEY", "test-key")
    mocker.patch("httpx.Client.__enter__", return_value=MagicMock(post=lambda *a, **k: mock_response))
    mocker.patch("httpx.Client.__exit__", return_value=False)

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value.__enter__.return_value = mock_client

        result = screen_entity("Gulf Properties FZE", CASE_ID)

    assert result.hit is True
    assert result.detail is not None
    assert "ofac_sdn" in result.detail


def test_screen_entity_clear(mocker):
    """Returns hit=False when no high-score match found."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"responses": {"q1": {"results": []}}}
    mock_response.raise_for_status = MagicMock()

    mocker.patch("tools.sanctions_tool.OPENSANCTIONS_API_KEY", "test-key")

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value.__enter__.return_value = mock_client

        result = screen_entity("Immobiliere Carthage SARL", CASE_ID)

    assert result.hit is False


def test_screen_entity_timeout(mocker):
    """On timeout, returns clean result without raising."""
    mocker.patch("tools.sanctions_tool.OPENSANCTIONS_API_KEY", "test-key")

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.TimeoutException("timeout")
        mock_client_cls.return_value.__enter__.return_value = mock_client

        result = screen_entity("Some Entity", CASE_ID)

    assert result.hit is False


def test_screen_entity_http_error(mocker):
    """On HTTP error, returns clean result without raising."""
    mocker.patch("tools.sanctions_tool.OPENSANCTIONS_API_KEY", "test-key")

    mock_response = MagicMock()
    mock_response.status_code = 429

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.HTTPStatusError(
            "rate limited", request=MagicMock(), response=mock_response
        )
        mock_client_cls.return_value.__enter__.return_value = mock_client

        result = screen_entity("Some Entity", CASE_ID)

    assert result.hit is False


def test_screen_entities_returns_dict():
    """screen_entities returns a dict keyed by entity name."""
    with patch("tools.sanctions_tool.OPENSANCTIONS_API_KEY", ""):
        results = screen_entities(
            ["Immobiliere Carthage SARL", "Gulf Properties FZE"], CASE_ID
        )
    assert isinstance(results, dict)
    assert "Immobiliere Carthage SARL" in results
    assert "Gulf Properties FZE" in results
    for val in results.values():
        assert "hit" in val
        assert "detail" in val


def test_sanctions_result_to_dict():
    r = SanctionsResult("Test Corp", hit=True, detail="OFAC SDN match")
    d = r.to_dict()
    assert d == {"hit": True, "detail": "OFAC SDN match"}
