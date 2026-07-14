from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


SESSION_PAYLOAD = {
    "device": {
        "ipv4Address": "10.61.0.1",
    },
    "applicationServer": {
        "ipv4Address": "10.100.200.1/32",
    },
    "qosProfile": "QOS_M",
    "duration": 300,
}


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        nef_client_id="nef-client",
        nef_client_secret="nef-secret",
        nef_notification_destination="http://callback",
        database_path=str(tmp_path / "gateway.db"),
        gateway_oauth_client_id="test-client",
        gateway_oauth_client_secret="test-secret",
        gateway_oauth_signing_secret="test-signing-secret",
    )


def get_token(
    client: TestClient,
    scope: str,
) -> str:
    response = client.post(
        "/oauth2/token",
        data={
            "grant_type": "client_credentials",
            "client_id": "test-client",
            "client_secret": "test-secret",
            "scope": scope,
        },
    )

    assert response.status_code == 200

    return response.json()["access_token"]


def test_sessions_reject_missing_token(tmp_path) -> None:
    app = create_app(settings=make_settings(tmp_path))

    with TestClient(app) as client:
        response = client.post(
            "/sessions",
            json=SESSION_PAYLOAD,
        )

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"
    assert "invalid_token" in response.headers["www-authenticate"]


def test_write_rejects_read_only_token(tmp_path) -> None:
    app = create_app(settings=make_settings(tmp_path))

    with TestClient(app) as client:
        token = get_token(client, "qod:read")

        response = client.post(
            "/sessions",
            json=SESSION_PAYLOAD,
            headers={
                "Authorization": f"Bearer {token}",
            },
        )

    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"
    assert (
        "insufficient_scope"
        in response.headers["www-authenticate"]
    )


def test_read_scope_passes_authorization_layer(tmp_path) -> None:
    app = create_app(settings=make_settings(tmp_path))

    with TestClient(app) as client:
        token = get_token(client, "qod:read")

        response = client.get(
            "/sessions/00000000-0000-0000-0000-000000000000",
            headers={
                "Authorization": f"Bearer {token}",
            },
        )

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_invalid_bearer_token_returns_401(tmp_path) -> None:
    app = create_app(settings=make_settings(tmp_path))

    with TestClient(app) as client:
        response = client.get(
            "/sessions/00000000-0000-0000-0000-000000000000",
            headers={
                "Authorization": "Bearer token-invalido",
            },
        )

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"
