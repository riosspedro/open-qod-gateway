from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.oauth import OAuthTokenService


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        nef_client_id="nef-client",
        nef_client_secret="nef-secret",
        nef_notification_destination="http://callback",
        database_path=str(tmp_path / "gateway.db"),
        gateway_oauth_client_id="test-client",
        gateway_oauth_client_secret="test-secret",
        gateway_oauth_signing_secret="test-signing-secret",
        gateway_oauth_token_ttl_seconds=600,
    )


def test_token_endpoint_issues_valid_token(tmp_path) -> None:
    settings = make_settings(tmp_path)
    app = create_app(settings=settings)

    with TestClient(app) as client:
        response = client.post(
            "/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": "test-client",
                "client_secret": "test-secret",
                "scope": "qod:read qod:write",
            },
        )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"

    body = response.json()

    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == 600
    assert body["scope"] == "qod:read qod:write"
    assert body["access_token"]

    payload = OAuthTokenService(settings).verify_token(
        body["access_token"],
        required_scope="qod:write",
    )

    assert payload["client_id"] == "test-client"


def test_invalid_client_returns_oauth_error(tmp_path) -> None:
    app = create_app(settings=make_settings(tmp_path))

    with TestClient(app) as client:
        response = client.post(
            "/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": "test-client",
                "client_secret": "wrong-secret",
            },
        )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Basic"
    assert response.json()["error"] == "invalid_client"


def test_unsupported_grant_type_returns_400(tmp_path) -> None:
    app = create_app(settings=make_settings(tmp_path))

    with TestClient(app) as client:
        response = client.post(
            "/oauth2/token",
            data={
                "grant_type": "password",
                "client_id": "test-client",
                "client_secret": "test-secret",
            },
        )

    assert response.status_code == 400
    assert response.json()["error"] == "unsupported_grant_type"


def test_missing_form_field_returns_400(tmp_path) -> None:
    app = create_app(settings=make_settings(tmp_path))

    with TestClient(app) as client:
        response = client.post(
            "/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": "test-client",
            },
        )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_ARGUMENT"
