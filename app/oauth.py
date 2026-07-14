import base64
import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.config import Settings


class OAuthError(ValueError):
    pass


class InvalidClientError(OAuthError):
    pass


class InvalidTokenError(OAuthError):
    pass


class InsufficientScopeError(OAuthError):
    pass


@dataclass(frozen=True)
class AccessToken:
    access_token: str
    token_type: str
    expires_in: int
    scope: str


class OAuthTokenService:
    def __init__(
        self,
        settings: Settings,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.settings = settings
        self.clock = clock

    def issue_token(
        self,
        *,
        client_id: str,
        client_secret: str,
        scope: str = "qod:read qod:write",
    ) -> AccessToken:
        self._authenticate_client(
            client_id=client_id,
            client_secret=client_secret,
        )

        issued_at = int(self.clock())
        expires_in = self.settings.gateway_oauth_token_ttl_seconds

        payload = {
            "client_id": client_id,
            "iat": issued_at,
            "exp": issued_at + expires_in,
            "scope": scope,
        }

        encoded_payload = self._encode_payload(payload)
        signature = self._sign(encoded_payload)

        return AccessToken(
            access_token=(
                f"{encoded_payload}.{self._base64_encode(signature)}"
            ),
            token_type="Bearer",
            expires_in=expires_in,
            scope=scope,
        )

    def verify_token(
        self,
        token: str,
        *,
        required_scope: str | None = None,
    ) -> dict[str, Any]:
        try:
            encoded_payload, encoded_signature = token.split(".", 1)
            supplied_signature = self._base64_decode(
                encoded_signature
            )
        except (ValueError, TypeError) as exc:
            raise InvalidTokenError(
                "Formato de token inválido."
            ) from exc

        expected_signature = self._sign(encoded_payload)

        if not hmac.compare_digest(
            supplied_signature,
            expected_signature,
        ):
            raise InvalidTokenError(
                "Assinatura do token inválida."
            )

        try:
            payload = json.loads(
                self._base64_decode(encoded_payload)
            )
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise InvalidTokenError(
                "Conteúdo do token inválido."
            ) from exc

        expires_at = payload.get("exp")
        client_id = payload.get("client_id")

        if not isinstance(expires_at, int):
            raise InvalidTokenError(
                "Token sem expiração válida."
            )

        if expires_at <= int(self.clock()):
            raise InvalidTokenError("Token expirado.")

        if client_id != self.settings.gateway_oauth_client_id:
            raise InvalidTokenError(
                "Token emitido para cliente desconhecido."
            )

        scopes = set(str(payload.get("scope", "")).split())

        if (
            required_scope is not None
            and required_scope not in scopes
        ):
            raise InsufficientScopeError(
                f"Token sem o escopo obrigatório: {required_scope}."
            )

        return payload

    def _authenticate_client(
        self,
        *,
        client_id: str,
        client_secret: str,
    ) -> None:
        expected_id = self.settings.gateway_oauth_client_id
        expected_secret = (
            self.settings.gateway_oauth_client_secret
            .get_secret_value()
        )

        valid_id = secrets.compare_digest(client_id, expected_id)
        valid_secret = secrets.compare_digest(
            client_secret,
            expected_secret,
        )

        if not valid_id or not valid_secret:
            raise InvalidClientError(
                "Credenciais OAuth2 inválidas."
            )

    def _sign(self, encoded_payload: str) -> bytes:
        signing_secret = (
            self.settings.gateway_oauth_signing_secret
            .get_secret_value()
            .encode()
        )

        return hmac.new(
            signing_secret,
            encoded_payload.encode(),
            hashlib.sha256,
        ).digest()

    @staticmethod
    def _encode_payload(payload: dict[str, Any]) -> str:
        serialized = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()

        return OAuthTokenService._base64_encode(serialized)

    @staticmethod
    def _base64_encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode().rstrip("=")

    @staticmethod
    def _base64_decode(value: str) -> bytes:
        padding = "=" * (-len(value) % 4)

        return base64.urlsafe_b64decode(value + padding)
