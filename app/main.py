import asyncio
import logging
from collections.abc import Callable
from contextlib import asynccontextmanager, suppress
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.database import SessionRepository
from app.models import (
    ApiError,
    CreateSessionRequest,
    SessionInfo,
    UpdateSessionRequest,
)
from app.nef_client import NefClient, NefClientError
from app.profiles import UnknownQosProfileError
from app.service import (
    SessionNotFoundError,
    SessionProvisioningError,
    SessionService,
)


ClientFactory = Callable[[Settings], NefClient]

logger = logging.getLogger("open_qod_gateway.cleanup")


def create_app(
    *,
    settings: Settings | None = None,
    client_factory: ClientFactory = NefClient,
) -> FastAPI:
    resolved_settings = settings or get_settings()

    repository = SessionRepository(
        resolved_settings.database_path
    )

    service = SessionService(
        repository=repository,
        settings=resolved_settings,
        client_factory=client_factory,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        repository.initialize()
        app.state.session_service = service

        async def cleanup_expired_sessions() -> None:
            while True:
                try:
                    expired_ids = await service.expire_sessions()

                    if expired_ids:
                        logger.info(
                            "Sessões QoD expiradas removidas: %s",
                            ", ".join(map(str, expired_ids)),
                        )
                except Exception:
                    logger.exception(
                        "Falha na limpeza de sessões expiradas."
                    )

                await asyncio.sleep(
                    resolved_settings
                    .session_cleanup_interval_seconds
                )

        cleanup_task = asyncio.create_task(
            cleanup_expired_sessions()
        )

        try:
            yield
        finally:
            cleanup_task.cancel()

            with suppress(asyncio.CancelledError):
                await cleanup_task

    app = FastAPI(
        title="Open QoD Gateway",
        version="0.1.0",
        lifespan=lifespan,
    )

    def get_service(request: Request) -> SessionService:
        return request.app.state.session_service

    ServiceDependency = Annotated[
        SessionService,
        Depends(get_service),
    ]

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        details = [
            {
                "location": list(error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
            for error in exc.errors()
        ]

        body = ApiError(
            status=400,
            code="INVALID_ARGUMENT",
            message="A requisição contém dados inválidos.",
            details=details,
        )

        return JSONResponse(
            status_code=400,
            content=body.model_dump(
                by_alias=True,
                mode="json",
            ),
        )

    @app.exception_handler(UnknownQosProfileError)
    async def handle_unknown_profile(
        request: Request,
        exc: UnknownQosProfileError,
    ) -> JSONResponse:
        body = ApiError(
            status=400,
            code="INVALID_ARGUMENT",
            message=str(exc),
        )

        return JSONResponse(
            status_code=400,
            content=body.model_dump(
                by_alias=True,
                mode="json",
            ),
        )

    @app.exception_handler(SessionNotFoundError)
    async def handle_session_not_found(
        request: Request,
        exc: SessionNotFoundError,
    ) -> JSONResponse:
        body = ApiError(
            status=404,
            code="NOT_FOUND",
            message=str(exc),
        )

        return JSONResponse(
            status_code=404,
            content=body.model_dump(
                by_alias=True,
                mode="json",
            ),
        )

    @app.exception_handler(SessionProvisioningError)
    async def handle_provisioning_error(
        request: Request,
        exc: SessionProvisioningError,
    ) -> JSONResponse:
        body = ApiError(
            status=502,
            code="NEF_PROVISIONING_FAILED",
            message=str(exc),
            details=[
                {
                    "sessionId": str(exc.session_id),
                }
            ],
        )

        return JSONResponse(
            status_code=502,
            content=body.model_dump(
                by_alias=True,
                mode="json",
            ),
        )

    @app.exception_handler(NefClientError)
    async def handle_nef_error(
        request: Request,
        exc: NefClientError,
    ) -> JSONResponse:
        body = ApiError(
            status=502,
            code="NEF_COMMUNICATION_FAILED",
            message=str(exc),
        )

        return JSONResponse(
            status_code=502,
            content=body.model_dump(
                by_alias=True,
                mode="json",
            ),
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {
            "status": "ok",
        }

    @app.post(
        "/sessions",
        response_model=SessionInfo,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_session(
        payload: CreateSessionRequest,
        session_service: ServiceDependency,
    ) -> SessionInfo:
        return await session_service.create_session(payload)

    @app.get(
        "/sessions/{session_id}",
        response_model=SessionInfo,
    )
    async def get_session(
        session_id: UUID,
        session_service: ServiceDependency,
    ) -> SessionInfo:
        return session_service.get_session(session_id)

    @app.patch(
        "/sessions/{session_id}",
        response_model=SessionInfo,
    )
    async def update_session(
        session_id: UUID,
        payload: UpdateSessionRequest,
        session_service: ServiceDependency,
    ) -> SessionInfo:
        return await session_service.update_session(
            session_id,
            payload,
        )

    @app.delete(
        "/sessions/{session_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def delete_session(
        session_id: UUID,
        session_service: ServiceDependency,
    ) -> Response:
        await session_service.delete_session(session_id)

        return Response(
            status_code=status.HTTP_204_NO_CONTENT
        )

    return app


app = create_app()
