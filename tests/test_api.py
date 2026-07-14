from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.nef_client import NefSubscription


VALID_PAYLOAD = {
    "device": {
        "ipv4Address": "10.61.0.1",
    },
    "applicationServer": {
        "ipv4Address": "10.100.200.1/32",
    },
    "qosProfile": "QOS_M",
    "duration": 300,
}


class FakeNefClient:
    def __init__(self) -> None:
        self.created_payload: dict[str, Any] | None = None
        self.deleted_subscription_id: str | None = None

    async def __aenter__(self) -> "FakeNefClient":
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

    async def create_as_session(
        self,
        *,
        token: str,
        payload: dict[str, Any],
    ) -> NefSubscription:
        self.created_payload = payload

        return NefSubscription(
            subscription_id="42",
            location="https://nef/subscriptions/42",
            body={},
        )

    async def delete_as_session(
        self,
        *,
        token: str,
        subscription_id: str,
    ) -> None:
        self.deleted_subscription_id = subscription_id


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        nef_client_id="client",
        nef_client_secret="secret",
        nef_notification_destination="http://callback",
        database_path=str(tmp_path / "gateway.db"),
    )


def test_health_endpoint(tmp_path) -> None:
    app = create_app(
        settings=make_settings(tmp_path),
        client_factory=lambda _: FakeNefClient(),
    )

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
    }


def test_create_get_and_delete_session(tmp_path) -> None:
    fake = FakeNefClient()

    app = create_app(
        settings=make_settings(tmp_path),
        client_factory=lambda _: fake,
    )

    with TestClient(app) as client:
        create_response = client.post(
            "/sessions",
            json=VALID_PAYLOAD,
        )

        assert create_response.status_code == 201

        created = create_response.json()

        assert created["device"] == {
            "ipv4Address": "10.61.0.1",
        }
        assert created["applicationServer"] == {
            "ipv4Address": "10.100.200.1/32",
        }
        assert created["qosProfile"] == "QOS_M"
        assert created["duration"] == 300
        assert created["qosStatus"] == "AVAILABLE"
        assert created["startedAt"] is not None
        assert created["expiresAt"] is not None
        assert "nefSubscriptionId" not in created

        session_id = created["sessionId"]

        get_response = client.get(
            f"/sessions/{session_id}"
        )

        assert get_response.status_code == 200
        assert get_response.json() == created

        delete_response = client.delete(
            f"/sessions/{session_id}"
        )

        assert delete_response.status_code == 204
        assert delete_response.content == b""
        assert fake.deleted_subscription_id == "42"

        missing_response = client.get(
            f"/sessions/{session_id}"
        )

        assert missing_response.status_code == 404
        assert missing_response.json()["code"] == "NOT_FOUND"

    assert fake.created_payload == {
        "ueIpv4Addr": "10.61.0.1",
        "guaranteed": "10 Mbps",
        "maximum": "20 Mbps",
    }


def test_unknown_qos_profile_returns_400(tmp_path) -> None:
    payload = {
        **VALID_PAYLOAD,
        "qosProfile": "QOS_INEXISTENTE",
    }

    app = create_app(
        settings=make_settings(tmp_path),
        client_factory=lambda _: FakeNefClient(),
    )

    with TestClient(app) as client:
        response = client.post(
            "/sessions",
            json=payload,
        )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_ARGUMENT"


def test_invalid_request_returns_400(tmp_path) -> None:
    payload = dict(VALID_PAYLOAD)
    payload.pop("device")

    app = create_app(
        settings=make_settings(tmp_path),
        client_factory=lambda _: FakeNefClient(),
    )

    with TestClient(app) as client:
        response = client.post(
            "/sessions",
            json=payload,
        )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_ARGUMENT"
    assert response.json()["details"]


def test_unknown_session_returns_404(tmp_path) -> None:
    app = create_app(
        settings=make_settings(tmp_path),
        client_factory=lambda _: FakeNefClient(),
    )

    with TestClient(app) as client:
        response = client.get(
            f"/sessions/{uuid4()}"
        )

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
