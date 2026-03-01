from app.services.auth import AuthService
from app.core import settings
from urllib.parse import urlparse, parse_qs


def test_ms_authority_defaults_to_organizations(monkeypatch):
    monkeypatch.setattr(settings, "ms_client_id", "client-id")
    monkeypatch.setattr(settings, "ms_client_secret", "client-secret")
    monkeypatch.setattr(settings, "jwt_secret", "jwt-secret")
    monkeypatch.setattr(settings, "ms_authority_tenant", None)
    monkeypatch.setattr(settings, "ms_tenant_id", None)

    svc = AuthService()

    assert svc.ms_configured is True
    assert svc.ms_auth_base == "https://login.microsoftonline.com/organizations"
    assert svc.ms_authorize_url.endswith("/organizations/oauth2/v2.0/authorize")
    assert svc.ms_token_url.endswith("/organizations/oauth2/v2.0/token")


def test_ms_authority_falls_back_to_legacy_ms_tenant_id(monkeypatch):
    monkeypatch.setattr(settings, "ms_client_id", "client-id")
    monkeypatch.setattr(settings, "ms_client_secret", "client-secret")
    monkeypatch.setattr(settings, "jwt_secret", "jwt-secret")
    monkeypatch.setattr(settings, "ms_authority_tenant", None)
    monkeypatch.setattr(settings, "ms_tenant_id", "common")

    svc = AuthService()

    assert svc.ms_auth_base == "https://login.microsoftonline.com/common"


def test_ms_issuer_validation_accepts_tenant_placeholder_pattern():
    expected = "https://login.microsoftonline.com/{tenantid}/v2.0"
    token_issuer = "https://login.microsoftonline.com/6d0f195d-eea2-442d-acdc-8094258019d6/v2.0"

    assert AuthService._is_valid_ms_issuer(expected_issuer=expected, token_issuer=token_issuer) is True


def test_ms_issuer_validation_rejects_mismatched_issuer():
    expected = "https://login.microsoftonline.com/{tenantid}/v2.0"
    token_issuer = "https://evil.example.com/6d0f195d-eea2-442d-acdc-8094258019d6/v2.0"

    assert AuthService._is_valid_ms_issuer(expected_issuer=expected, token_issuer=token_issuer) is False


def test_ms_authorization_url_forces_account_picker(monkeypatch):
    monkeypatch.setattr(settings, "ms_client_id", "client-id")
    monkeypatch.setattr(settings, "ms_client_secret", "client-secret")
    monkeypatch.setattr(settings, "jwt_secret", "jwt-secret")
    monkeypatch.setattr(settings, "ms_authority_tenant", "organizations")
    monkeypatch.setattr(settings, "ms_redirect_uri", "http://localhost:8000/auth/ms/callback")

    svc = AuthService()
    url, _ = svc.get_ms_authorization_url(state="state-123")
    parsed = parse_qs(urlparse(url).query)

    assert parsed.get("prompt") == ["select_account"]
