from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.database import SessionRecord, SessionRepository
from app.models import QosStatus


def make_record() -> SessionRecord:
    return SessionRecord(
        session_id=uuid4(),
        device_ipv4="10.61.0.1",
        application_server_ipv4="10.100.200.1/32",
        qos_profile="QOS_M",
        duration=300,
        qos_status=QosStatus.REQUESTED,
        started_at=None,
        expires_at=None,
        nef_subscription_id=None,
    )


def test_repository_creates_and_reads_session(tmp_path) -> None:
    repository = SessionRepository(tmp_path / "gateway.db")
    repository.initialize()

    record = make_record()
    repository.create(record)

    assert repository.get(record.session_id) == record


def test_repository_updates_activation(tmp_path) -> None:
    repository = SessionRepository(tmp_path / "gateway.db")
    repository.initialize()

    record = make_record()
    repository.create(record)

    started_at = datetime.now(timezone.utc)
    expires_at = started_at + timedelta(seconds=record.duration)

    updated = repository.update_activation(
        session_id=record.session_id,
        qos_status=QosStatus.AVAILABLE,
        started_at=started_at,
        expires_at=expires_at,
        nef_subscription_id="123",
    )

    stored = repository.get(record.session_id)

    assert updated is True
    assert stored is not None
    assert stored.qos_status == QosStatus.AVAILABLE
    assert stored.started_at == started_at
    assert stored.expires_at == expires_at
    assert stored.nef_subscription_id == "123"


def test_repository_returns_none_for_unknown_session(tmp_path) -> None:
    repository = SessionRepository(tmp_path / "gateway.db")
    repository.initialize()

    assert repository.get(uuid4()) is None


def test_repository_deletes_session(tmp_path) -> None:
    repository = SessionRepository(tmp_path / "gateway.db")
    repository.initialize()

    record = make_record()
    repository.create(record)

    assert repository.delete(record.session_id) is True
    assert repository.get(record.session_id) is None
    assert repository.delete(record.session_id) is False


def test_repository_lists_only_expired_available_sessions(
    tmp_path,
) -> None:
    repository = SessionRepository(tmp_path / "gateway.db")
    repository.initialize()

    record = make_record()
    repository.create(record)

    now = datetime.now(timezone.utc)

    repository.update_activation(
        session_id=record.session_id,
        qos_status=QosStatus.AVAILABLE,
        started_at=now - timedelta(seconds=10),
        expires_at=now - timedelta(seconds=1),
        nef_subscription_id="expired-subscription",
    )

    expired = repository.list_expired(now)

    assert len(expired) == 1
    assert expired[0].session_id == record.session_id
