from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from app.config import Settings
from app.database import SessionRecord, SessionRepository
from app.models import (
    CreateSessionRequest,
    QosStatus,
    SessionInfo,
    UpdateSessionRequest,
)
from app.nef_client import NefClient, NefClientError
from app.profiles import get_qos_profile


class SessionNotFoundError(LookupError):
    pass


class SessionProvisioningError(RuntimeError):
    def __init__(self, session_id: UUID, message: str) -> None:
        super().__init__(message)
        self.session_id = session_id


class SessionService:
    def __init__(
        self,
        *,
        repository: SessionRepository,
        settings: Settings,
        client_factory: Callable[[Settings], NefClient] = NefClient,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.client_factory = client_factory

    async def create_session(
        self,
        request: CreateSessionRequest,
    ) -> SessionInfo:
        profile = get_qos_profile(request.qos_profile)
        session_id = uuid4()

        record = SessionRecord(
            session_id=session_id,
            device_ipv4=str(request.device.ipv4_address),
            application_server_ipv4=(
                request.application_server.ipv4_address
            ),
            qos_profile=request.qos_profile,
            duration=request.duration,
            qos_status=QosStatus.REQUESTED,
            started_at=None,
            expires_at=None,
            nef_subscription_id=None,
        )

        self.repository.create(record)

        try:
            async with self.client_factory(self.settings) as client:
                token = await client.get_access_token()

                payload = client.build_as_session_payload(
                    ue_ipv4=record.device_ipv4,
                    guaranteed_bandwidth=(
                        profile.guaranteed_bandwidth
                    ),
                    maximum_bandwidth=profile.maximum_bandwidth,
                )

                subscription = await client.create_as_session(
                    token=token,
                    payload=payload,
                )
        except NefClientError as exc:
            self.repository.update_status(
                session_id=session_id,
                qos_status=QosStatus.UNAVAILABLE,
            )

            raise SessionProvisioningError(
                session_id,
                str(exc),
            ) from exc

        started_at = datetime.now(timezone.utc)
        expires_at = started_at + timedelta(
            seconds=request.duration
        )

        self.repository.update_activation(
            session_id=session_id,
            qos_status=QosStatus.AVAILABLE,
            started_at=started_at,
            expires_at=expires_at,
            nef_subscription_id=subscription.subscription_id,
        )

        stored = self.repository.get(session_id)

        if stored is None:
            raise RuntimeError(
                "A sessão foi criada, mas não foi encontrada no banco."
            )

        return self._to_session_info(stored)

    async def update_session(
        self,
        session_id: UUID,
        request: UpdateSessionRequest,
    ) -> SessionInfo:
        record = self.repository.get(session_id)

        if record is None:
            raise SessionNotFoundError(
                f"Sessão não encontrada: {session_id}"
            )

        new_qos_profile = (
            request.qos_profile
            if request.qos_profile is not None
            else record.qos_profile
        )

        new_duration = (
            request.duration
            if request.duration is not None
            else record.duration
        )

        if (
            request.qos_profile is not None
            and request.qos_profile != record.qos_profile
        ):
            profile = get_qos_profile(new_qos_profile)

            if record.nef_subscription_id is None:
                raise SessionProvisioningError(
                    session_id,
                    "A sessão não possui assinatura ativa no NEF.",
                )

            try:
                async with self.client_factory(
                    self.settings
                ) as client:
                    token = await client.get_access_token()

                    payload = (
                        client.build_as_session_patch_payload(
                            ue_ipv4=record.device_ipv4,
                            guaranteed_bandwidth=(
                                profile.guaranteed_bandwidth
                            ),
                            maximum_bandwidth=(
                                profile.maximum_bandwidth
                            ),
                        )
                    )

                    await client.patch_as_session(
                        token=token,
                        subscription_id=(
                            record.nef_subscription_id
                        ),
                        payload=payload,
                    )
            except NefClientError as exc:
                raise SessionProvisioningError(
                    session_id,
                    str(exc),
                ) from exc

        expires_at = record.expires_at

        if request.duration is not None:
            if record.started_at is not None:
                expires_at = record.started_at + timedelta(
                    seconds=new_duration
                )
            else:
                expires_at = None

        self.repository.update_session(
            session_id=session_id,
            qos_profile=new_qos_profile,
            duration=new_duration,
            expires_at=expires_at,
        )

        updated = self.repository.get(session_id)

        if updated is None:
            raise RuntimeError(
                "A sessão atualizada não foi encontrada no banco."
            )

        return self._to_session_info(updated)

    async def expire_sessions(
        self,
        now: datetime | None = None,
    ) -> list[UUID]:
        current_time = now or datetime.now(timezone.utc)
        expired_session_ids: list[UUID] = []

        for record in self.repository.list_expired(current_time):
            try:
                if record.nef_subscription_id is not None:
                    async with self.client_factory(
                        self.settings
                    ) as client:
                        token = await client.get_access_token()

                        await client.delete_as_session(
                            token=token,
                            subscription_id=(
                                record.nef_subscription_id
                            ),
                        )
            except NefClientError:
                # Mantém o registro para uma nova tentativa.
                continue

            if self.repository.delete(record.session_id):
                expired_session_ids.append(record.session_id)

        return expired_session_ids

    def get_session(self, session_id: UUID) -> SessionInfo:
        record = self.repository.get(session_id)

        if record is None:
            raise SessionNotFoundError(
                f"Sessão não encontrada: {session_id}"
            )

        return self._to_session_info(record)

    async def delete_session(self, session_id: UUID) -> None:
        record = self.repository.get(session_id)

        if record is None:
            raise SessionNotFoundError(
                f"Sessão não encontrada: {session_id}"
            )

        if record.nef_subscription_id is not None:
            async with self.client_factory(self.settings) as client:
                token = await client.get_access_token()

                await client.delete_as_session(
                    token=token,
                    subscription_id=record.nef_subscription_id,
                )

        self.repository.delete(session_id)

    @staticmethod
    def _to_session_info(record: SessionRecord) -> SessionInfo:
        return SessionInfo(
            sessionId=record.session_id,
            device={
                "ipv4Address": record.device_ipv4,
            },
            applicationServer={
                "ipv4Address": record.application_server_ipv4,
            },
            qosProfile=record.qos_profile,
            duration=record.duration,
            qosStatus=record.qos_status,
            startedAt=record.started_at,
            expiresAt=record.expires_at,
            nefSubscriptionId=record.nef_subscription_id,
        )
