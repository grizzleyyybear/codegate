import pytest
from app.auth import require_api_key
from fastapi import HTTPException


def test_auth_disabled_when_key_unset(monkeypatch):
    monkeypatch.delenv("GATEWAY_API_KEY", raising=False)
    assert require_api_key(None) is None
    assert require_api_key("anything") is None


def test_auth_rejects_missing_header(monkeypatch):
    monkeypatch.setenv("GATEWAY_API_KEY", "sekret")
    with pytest.raises(HTTPException) as exc:
        require_api_key(None)
    assert exc.value.status_code == 401


def test_auth_rejects_wrong_key(monkeypatch):
    monkeypatch.setenv("GATEWAY_API_KEY", "sekret")
    with pytest.raises(HTTPException):
        require_api_key("wrong")


def test_auth_accepts_correct_key(monkeypatch):
    monkeypatch.setenv("GATEWAY_API_KEY", "sekret")
    assert require_api_key("sekret") is None
