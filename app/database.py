import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import UUID

from app.models import QosStatus


@dataclass(frozen=True)
class SessionRecord:
    session_id: UUID
    device_ipv4: str
    application_server_ipv4: str
    qos_profile: str
    duration: int
    qos_status: QosStatus
    started_at: datetime | None
    expires_at: datetime | None
    nef_subscription_id: str | None


class SessionRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    device_ipv4 TEXT NOT NULL,
                    application_server_ipv4 TEXT NOT NULL,
                    qos_profile TEXT NOT NULL,
                    duration INTEGER NOT NULL,
                    qos_status TEXT NOT NULL,
                    started_at TEXT,
                    expires_at TEXT,
                    nef_subscription_id TEXT
                )
                """
            )

    def create(self, record: SessionRecord) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sessions (
                    session_id,
                    device_ipv4,
                    application_server_ipv4,
                    qos_profile,
                    duration,
                    qos_status,
                    started_at,
                    expires_at,
                    nef_subscription_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(record.session_id),
                    record.device_ipv4,
                    record.application_server_ipv4,
                    record.qos_profile,
                    record.duration,
                    record.qos_status.value,
                    self._serialize_datetime(record.started_at),
                    self._serialize_datetime(record.expires_at),
                    record.nef_subscription_id,
                ),
            )

    def get(self, session_id: UUID) -> SessionRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    session_id,
                    device_ipv4,
                    application_server_ipv4,
                    qos_profile,
                    duration,
                    qos_status,
                    started_at,
                    expires_at,
                    nef_subscription_id
                FROM sessions
                WHERE session_id = ?
                """,
                (str(session_id),),
            ).fetchone()

        if row is None:
            return None

        return self._row_to_record(row)

    def update_activation(
        self,
        *,
        session_id: UUID,
        qos_status: QosStatus,
        started_at: datetime,
        expires_at: datetime,
        nef_subscription_id: str,
    ) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE sessions
                SET
                    qos_status = ?,
                    started_at = ?,
                    expires_at = ?,
                    nef_subscription_id = ?
                WHERE session_id = ?
                """,
                (
                    qos_status.value,
                    self._serialize_datetime(started_at),
                    self._serialize_datetime(expires_at),
                    nef_subscription_id,
                    str(session_id),
                ),
            )

        return cursor.rowcount == 1

    def list_expired(
        self,
        now: datetime,
    ) -> list[SessionRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    session_id,
                    device_ipv4,
                    application_server_ipv4,
                    qos_profile,
                    duration,
                    qos_status,
                    started_at,
                    expires_at,
                    nef_subscription_id
                FROM sessions
                WHERE
                    qos_status = ?
                    AND expires_at IS NOT NULL
                    AND expires_at <= ?
                ORDER BY expires_at
                """,
                (
                    QosStatus.AVAILABLE.value,
                    self._serialize_datetime(now),
                ),
            ).fetchall()

        return [
            self._row_to_record(row)
            for row in rows
        ]

    def update_session(
        self,
        *,
        session_id: UUID,
        qos_profile: str,
        duration: int,
        expires_at: datetime | None,
    ) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE sessions
                SET
                    qos_profile = ?,
                    duration = ?,
                    expires_at = ?
                WHERE session_id = ?
                """,
                (
                    qos_profile,
                    duration,
                    self._serialize_datetime(expires_at),
                    str(session_id),
                ),
            )

        return cursor.rowcount == 1

    def update_status(
        self,
        *,
        session_id: UUID,
        qos_status: QosStatus,
    ) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE sessions
                SET qos_status = ?
                WHERE session_id = ?
                """,
                (
                    qos_status.value,
                    str(session_id),
                ),
            )

        return cursor.rowcount == 1

    def delete(self, session_id: UUID) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM sessions WHERE session_id = ?",
                (str(session_id),),
            )

        return cursor.rowcount == 1

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _serialize_datetime(value: datetime | None) -> str | None:
        if value is None:
            return None

        return value.isoformat()

    @staticmethod
    def _deserialize_datetime(value: str | None) -> datetime | None:
        if value is None:
            return None

        return datetime.fromisoformat(value)

    def _row_to_record(self, row: sqlite3.Row) -> SessionRecord:
        return SessionRecord(
            session_id=UUID(row["session_id"]),
            device_ipv4=row["device_ipv4"],
            application_server_ipv4=row["application_server_ipv4"],
            qos_profile=row["qos_profile"],
            duration=row["duration"],
            qos_status=QosStatus(row["qos_status"]),
            started_at=self._deserialize_datetime(row["started_at"]),
            expires_at=self._deserialize_datetime(row["expires_at"]),
            nef_subscription_id=row["nef_subscription_id"],
        )
