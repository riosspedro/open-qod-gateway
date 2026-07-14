from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.config import Settings
from app.database import SessionRepository
from app.models import CreateSessionRequest, QosStatus
from app.nef_client import NefClientError, NefSubscription
from app.service import (
    SessionNotFoundError,
    SessionProvisioningError,
    SessionService,
)


REQUEST = CreateSessionRequest.model_validate(
    {
        "device": {
            "ipv4Address": "10.61.0.1",
        },
        "applicationServer": {
            "ipv4Address": "10.100.200.1/32",
        },
        "qosProfile": "QOS_M",
        "duration": 300,
    }
)


class FakeNefClient:
    def __init__(self, fail_create: bool = False) -> None:
        self.fail_create = fail_create
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
        if self.fail_create:
            raise NefClientError("falha simulada")

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


@pytest.mark.asyncio
async def test_service_creates_available_session(tmp_path) -> None:
    settings = make_settings(tmp_path)
    repository = SessionRepository(settings.database_path)
    repository.initialize()

    fake = FakeNefClient()

    service = SessionService(
        repository=repository,
        settings=settings,
        client_factory=lambda _: fake,
    )

    session = await service.create_session(REQUEST)

    assert session.qos_status == QosStatus.AVAILABLE
    assert session.nef_subscription_id == "42"
    assert session.started_at is not None
    assert session.expires_at is not None
    assert fake.created_payload == {
        "ueIpv4Addr": "10.61.0.1",
        "guaranteed": "10 Mbps",
        "maximum": "20 Mbps",
    }

    stored = service.get_session(session.session_id)

    assert stored == session


@pytest.mark.asyncio
async def test_service_deletes_nef_and_local_session(tmp_path) -> None:
    settings = make_settings(tmp_path)
    repository = SessionRepository(settings.database_path)
    repository.initialize()

    fake = FakeNefClient()

    service = SessionService(
        repository=repository,
        settings=settings,
        client_factory=lambda _: fake,
    )

    session = await service.create_session(REQUEST)

    await service.delete_session(session.session_id)

    assert fake.deleted_subscription_id == "42"

    with pytest.raises(SessionNotFoundError):
        service.get_session(session.session_id)


@pytest.mark.asyncio
async def test_failed_provisioning_is_stored_as_unavailable(
    tmp_path,
) -> None:
    settings = make_settings(tmp_path)
    repository = SessionRepository(settings.database_path)
    repository.initialize()

    fake = FakeNefClient(fail_create=True)

    service = SessionService(
        repository=repository,
        settings=settings,
        client_factory=lambda _: fake,
    )

    with pytest.raises(SessionProvisioningError) as error:
        await service.create_session(REQUEST)

    stored = repository.get(error.value.session_id)

    assert stored is not None
    assert stored.qos_status == QosStatus.UNAVAILABLE
    assert stored.nef_subscription_id is None


@pytest.mark.asyncio
async def test_deleting_unknown_session_fails(tmp_path) -> None:
    settings = make_settings(tmp_path)
    repository = SessionRepository(settings.database_path)
    repository.initialize()

    service = SessionService(
        repository=repository,
        settings=settings,
        client_factory=lambda _: FakeNefClient(),
    )

    with pytest.raises(SessionNotFoundError):
        await service.delete_session(uuid4())


def test_getting_unknown_session_fails(tmp_path) -> None:
    settings = make_settings(tmp_path)
    repository = SessionRepository(settings.database_path)
    repository.initialize()

    service = SessionService(
        repository=repository,
        settings=settings,
        client_factory=lambda _: FakeNefClient(),
    )

    with pytest.raises(SessionNotFoundError):
        service.get_session(UUID(int=0))


@pytest.mark.asyncio
async def test_service_removes_expired_nef_session(
    tmp_path,
) -> None:
    settings = make_settings(tmp_path)
    repository = SessionRepository(settings.database_path)
    repository.initialize()

    fake = FakeNefClient()

    service = SessionService(
        repository=repository,
        settings=settings,
        client_factory=lambda _: fake,
    )

    session = await service.create_session(REQUEST)
    now = datetime.now(timezone.utc)

    repository.update_activation(
        session_id=session.session_id,
        qos_status=QosStatus.AVAILABLE,
        started_at=now - timedelta(seconds=10),
        expires_at=now - timedelta(seconds=1),
        nef_subscription_id="42",
    )

    expired_ids = await service.expire_sessions(now)

    assert expired_ids == [session.session_id]
    assert fake.deleted_subscription_id == "42"
    assert repository.get(session.session_id) is None
