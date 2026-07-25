"""Unit tests for API-key auth and the production-default-key startup guard."""

import pytest
from fastapi import HTTPException

from api.main import (
    _check_production_key_safety,
    _DEFAULT_WARAKA_API_KEY,
    verify_api_key,
    WARAKA_API_KEY,
)


class TestVerifyApiKey:
    def test_correct_key_is_accepted(self):
        verify_api_key(authorization=f"Bearer {WARAKA_API_KEY}")

    def test_wrong_case_key_is_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            verify_api_key(authorization=f"Bearer {WARAKA_API_KEY.upper()}")
        assert exc_info.value.status_code == 401

    def test_near_miss_key_is_rejected(self):
        near_miss = WARAKA_API_KEY[:-1] + ("x" if WARAKA_API_KEY[-1:] != "x" else "y")
        with pytest.raises(HTTPException) as exc_info:
            verify_api_key(authorization=f"Bearer {near_miss}")
        assert exc_info.value.status_code == 401

    def test_missing_header_is_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            verify_api_key(authorization=None)
        assert exc_info.value.status_code == 401


class TestProductionKeySafety:
    def test_raises_when_production_and_default_key(self):
        with pytest.raises(RuntimeError):
            _check_production_key_safety("production", _DEFAULT_WARAKA_API_KEY)

    def test_raises_when_unset_environment_and_default_key(self):
        """Unset ENVIRONMENT ("") must fail closed, same as "production"."""
        with pytest.raises(RuntimeError):
            _check_production_key_safety("", _DEFAULT_WARAKA_API_KEY)

    def test_does_not_raise_when_development_and_default_key(self):
        _check_production_key_safety("development", _DEFAULT_WARAKA_API_KEY)

    def test_does_not_raise_when_key_is_overridden(self):
        _check_production_key_safety("production", "a-real-secret-key")
