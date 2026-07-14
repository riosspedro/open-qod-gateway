from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app
from app.models import UpdateSessionRequest
from app.nef_client import NefSubscription


CREATE_PAYLOAD = {
    "device": {
        "ipv4Address": "10.61.0.1",
    },
    "applicationServer": {
        "ipv4Address": "10.100.200.1/32",
    },
    "qosProfile": "QOS_M",
    "duration": 300,
}


class FakePatchNefClient:
    def __init__(self) -> None:
        self.patch_payload: dict[str, Any] | None = None
        self.patched_subscription_id: str | None = None

    async def __aenter__(self) -> "FakePatchNefClient":
        return self

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        return None

    async def get_access_token(self) -> str:
        return "fake-token"

    def build_as_session_payload(
        self,
        *,
        ue_ipv4: str,
        guaranteed_bandwidth: str,
        maximum_bandwidth: str,
    ) -> dict[str, Any]:
        return {
            "ueIpv4Addr": ue_ipv4,
            "guaranteed": guaranteed_bandwidth,
            "maximum": maximum_bandwidth,
        }

    def build_as_session_patch_payload(
        self,
        *,
        ue_ipv4: str,
        guaranteed_bandwidth: str,
        maximum_bandwidth: str,
    ) -> dict[str, Any]:
        return {
            "ueIpv4Addr": ue_ipv4,
            "guaranteed": guaranteed_bandwidth,
            "maximum": maximum_bandwidth,
        }

    async def create_as_session(
        self,
        *,
        token: str,
        payload: dict[str, Any],
    ) -> NefSubscription:
        return NefSubscription(
            subscription_id="77",
            location="https://nef/subscriptions/77",
            body={},
        )

    async def patch_as_session(
        self,
        *,
        token: str,
        subscription_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self.patched_subscription_id = subscription_id
        self.patch_payload = payload

        return {
            "asSessionMediaComponent": {},
        }

    async def delete_as_session(
        self,
        *,
        token: str,
        subscription_id: str,
    ) -> None:
        return None


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        nef_client_id="client",
        nef_client_secret="secret",
        nef_notification_destination="http://callback",
        database_path=str(tmp_path / "gateway.db"),
        gateway_oauth_client_id="test-client",
        gateway_oauth_client_secret="test-secret",
        gateway_oauth_signing_secret="test-signing-secret",
    )


def authorization_headers(
    client: TestClient,
) -> dict[str, str]:
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

    return {
        "Authorization": (
            f"Bearer {response.json()['access_token']}"
        )
    }


def test_empty_patch_is_rejected() -> None:
    with pytest.raises(ValidationError):
        UpdateSessionRequest.model_validate({})


def test_patch_updates_profile_and_duration(tmp_path) -> None:
    fake = FakePatchNefClient()

    app = create_app(
        settings=make_settings(tmp_path),
        client_factory=lambda _: fake,
    )

    with TestClient(app) as client:
        headers = authorization_headers(client)

        created = client.post(
            "/sessions",
            json=CREATE_PAYLOAD,
            headers=headers,
        )

        assert created.status_code == 201

        session_id = created.json()["sessionId"]

        patched = client.patch(
            f"/sessions/{session_id}",
            json={
                "qosProfile": "QOS_HIGH",
                "duration": 600,
            },
            headers=headers,
        )

        assert patched.status_code == 200

        body = patched.json()

        assert body["qosProfile"] == "QOS_HIGH"
        assert body["duration"] == 600
        assert body["qosStatus"] == "AVAILABLE"

    assert fake.patched_subscription_id == "77"
    assert fake.patch_payload == {
        "ueIpv4Addr": "10.61.0.1",
        "guaranteed": "12 Mbps",
        "maximum": "24 Mbps",
    }


def test_patch_unknown_profile_returns_400(tmp_path) -> None:
    fake = FakePatchNefClient()

    app = create_app(
        settings=make_settings(tmp_path),
        client_factory=lambda _: fake,
    )

    with TestClient(app) as client:
        headers = authorization_headers(client)

        created = client.post(
            "/sessions",
            json=CREATE_PAYLOAD,
            headers=headers,
        )

        session_id = created.json()["sessionId"]

        patched = client.patch(
            f"/sessions/{session_id}",
            json={
                "qosProfile": "QOS_INVALID",
            },
            headers=headers,
        )

    assert patched.status_code == 400
    assert patched.json()["code"] == "INVALID_ARGUMENT"
