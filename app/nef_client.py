from dataclasses import dataclass
import ssl
from typing import Any

import httpx

from app.config import Settings


class NefClientError(RuntimeError):
    pass


def build_nef_ssl_context(
    settings: Settings,
) -> bool | ssl.SSLContext:
    client_certificate = settings.nef_client_cert
    client_key = settings.nef_client_key

    if (
        not settings.nef_verify_tls
        and client_certificate is None
    ):
        return False

    try:
        context = ssl.create_default_context(
            cafile=(
                settings.nef_ca_bundle
                if settings.nef_verify_tls
                else None
            )
        )

        if not settings.nef_verify_tls:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE

        if client_certificate is not None and client_key is not None:
            context.load_cert_chain(
                certfile=client_certificate,
                keyfile=client_key,
            )
    except (OSError, ssl.SSLError) as exc:
        raise NefClientError(
            f"Falha ao configurar TLS do cliente NEF: {exc}"
        ) from exc

    return context


@dataclass(frozen=True)
class NefSubscription:
    subscription_id: str
    location: str
    body: dict[str, Any]


class NefClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.http = httpx.AsyncClient(
            base_url=settings.nef_base_url.rstrip("/"),
            verify=build_nef_ssl_context(settings),
            timeout=settings.nef_timeout_seconds,
        )

    def _subscription_path(
        self,
        subscription_id: str | None = None,
    ) -> str:
        path = (
            "/3gpp-as-session-with-qos/v1/"
            f"{self.settings.nef_scs_as_id}/subscriptions"
        )

        if subscription_id is not None:
            path += f"/{subscription_id}"

        return path

    async def get_access_token(self) -> str:
        try:
            response = await self.http.post(
                "/oauth2/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.settings.nef_client_id,
                    "client_secret": self.settings.nef_client_secret,
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise NefClientError(
                f"Falha ao obter token do NEF: {exc}"
            ) from exc

        try:
            payload: dict[str, Any] = response.json()
        except ValueError as exc:
            raise NefClientError(
                "O NEF retornou uma resposta OAuth2 que não é JSON."
            ) from exc

        token = payload.get("access_token")

        if not isinstance(token, str) or not token:
            raise NefClientError(
                f"Resposta OAuth2 sem access_token: {payload}"
            )

        return token

    def build_as_session_payload(
        self,
        *,
        ue_ipv4: str,
        guaranteed_bandwidth: str,
        maximum_bandwidth: str,
    ) -> dict[str, Any]:
        return {
            "notificationDestination":
                self.settings.nef_notification_destination,
            "ueIpv4Addr": ue_ipv4,
            "dnn": "internet",
            "snssai": {
                "sst": 1,
                "sd": "112233",
            },
            "asSessionMediaComponent": {
                "1": self._build_media_component(
                    ue_ipv4=ue_ipv4,
                    guaranteed_bandwidth=guaranteed_bandwidth,
                    maximum_bandwidth=maximum_bandwidth,
                )
            },
            "supportedFeatures": "1",
        }

    def build_as_session_patch_payload(
        self,
        *,
        ue_ipv4: str,
        guaranteed_bandwidth: str,
        maximum_bandwidth: str,
    ) -> dict[str, Any]:
        return {
            "notificationDestination":
                self.settings.nef_notification_destination,
            "asSessionMediaComponent": {
                "1": self._build_media_component(
                    ue_ipv4=ue_ipv4,
                    guaranteed_bandwidth=guaranteed_bandwidth,
                    maximum_bandwidth=maximum_bandwidth,
                )
            },
        }

    @staticmethod
    def _build_media_component(
        *,
        ue_ipv4: str,
        guaranteed_bandwidth: str,
        maximum_bandwidth: str,
    ) -> dict[str, Any]:
        return {
            "medCompN": 1,
            "medType": "VIDEO",
            "flowInfos": [
                {
                    "flowId": 1,
                    "flowDescriptions": [
                        f"permit out ip from any to {ue_ipv4}"
                    ],
                }
            ],
            "mirBwUl": guaranteed_bandwidth,
            "mirBwDl": guaranteed_bandwidth,
            "marBwUl": maximum_bandwidth,
            "marBwDl": maximum_bandwidth,
        }

    async def create_as_session(
        self,
        *,
        token: str,
        payload: dict[str, Any],
    ) -> NefSubscription:
        try:
            response = await self.http.post(
                self._subscription_path(),
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise NefClientError(
                "Falha ao criar assinatura no NEF: "
                f"HTTP {exc.response.status_code} "
                f"{exc.response.text}"
            ) from exc
        except httpx.HTTPError as exc:
            raise NefClientError(
                f"Falha de comunicação ao criar assinatura: {exc}"
            ) from exc

        if response.status_code != 201:
            raise NefClientError(
                f"NEF retornou HTTP {response.status_code}, esperado 201."
            )

        location = response.headers.get("location", "").strip()

        if not location:
            raise NefClientError(
                "Resposta de criação sem cabeçalho Location."
            )

        subscription_id = location.rstrip("/").rsplit("/", 1)[-1]

        try:
            body: dict[str, Any] = response.json()
        except ValueError as exc:
            raise NefClientError(
                "Resposta de criação do NEF não é JSON."
            ) from exc

        return NefSubscription(
            subscription_id=subscription_id,
            location=location,
            body=body,
        )

    async def patch_as_session(
        self,
        *,
        token: str,
        subscription_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            response = await self.http.patch(
                self._subscription_path(subscription_id),
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise NefClientError(
                "Falha ao atualizar assinatura no NEF: "
                f"HTTP {exc.response.status_code} "
                f"{exc.response.text}"
            ) from exc
        except httpx.HTTPError as exc:
            raise NefClientError(
                f"Falha de comunicação ao atualizar assinatura: {exc}"
            ) from exc

        if response.status_code != 200:
            raise NefClientError(
                f"NEF retornou HTTP {response.status_code}, esperado 200."
            )

        try:
            body: dict[str, Any] = response.json()
        except ValueError as exc:
            raise NefClientError(
                "Resposta de atualização do NEF não é JSON."
            ) from exc

        return body

    async def delete_as_session(
        self,
        *,
        token: str,
        subscription_id: str,
    ) -> None:
        try:
            response = await self.http.delete(
                self._subscription_path(subscription_id),
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise NefClientError(
                "Falha ao apagar assinatura no NEF: "
                f"HTTP {exc.response.status_code} "
                f"{exc.response.text}"
            ) from exc
        except httpx.HTTPError as exc:
            raise NefClientError(
                f"Falha de comunicação ao apagar assinatura: {exc}"
            ) from exc

        if response.status_code != 204:
            raise NefClientError(
                f"NEF retornou HTTP {response.status_code}, esperado 204."
            )

    async def close(self) -> None:
        await self.http.aclose()

    async def __aenter__(self) -> "NefClient":
        return self

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        await self.close()
