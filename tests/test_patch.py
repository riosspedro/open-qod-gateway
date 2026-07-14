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
    )


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
        created = client.post(
            "/sessions",
            json=CREATE_PAYLOAD,
        )

        assert created.status_code == 201

        session_id = created.json()["sessionId"]

        patched = client.patch(
            f"/sessions/{session_id}",
            json={
                "qosProfile": "QOS_HIGH",
                "duration": 600,
            },
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
        created = client.post(
            "/sessions",
            json=CREATE_PAYLOAD,
        )

        session_id = created.json()["sessionId"]

        patched = client.patch(
            f"/sessions/{session_id}",
            json={
                "qosProfile": "QOS_INVALID",
            },
        )

    assert patched.status_code == 400
    assert patched.json()["code"] == "INVALID_ARGUMENT"
