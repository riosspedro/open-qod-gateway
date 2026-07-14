import pytest

from app.config import Settings
from app.oauth import (
    InvalidClientError,
    InvalidTokenError,
    OAuthTokenService,
)


def make_settings() -> Settings:
    return Settings(
        nef_client_id="nef-client",
        nef_client_secret="nef-secret",
        nef_notification_destination="http://callback",
        gateway_oauth_client_id="test-client",
        gateway_oauth_client_secret="test-secret",
        gateway_oauth_signing_secret="test-signing-secret",
        gateway_oauth_token_ttl_seconds=60,
    )


def test_issue_and_verify_access_token() -> None:
    service = OAuthTokenService(
        make_settings(),
        clock=lambda: 1000,
    )

    token = service.issue_token(
        client_id="test-client",
        client_secret="test-secret",
    )

    payload = service.verify_token(
        token.access_token,
        required_scope="qod:write",
    )

    assert token.token_type == "Bearer"
    assert token.expires_in == 60
    assert payload["client_id"] == "test-client"
    assert payload["exp"] == 1060


def test_invalid_client_credentials_are_rejected() -> None:
    service = OAuthTokenService(make_settings())

    with pytest.raises(InvalidClientError):
        service.issue_token(
            client_id="test-client",
            client_secret="wrong-secret",
        )


def test_tampered_token_is_rejected() -> None:
    service = OAuthTokenService(make_settings())

    token = service.issue_token(
        client_id="test-client",
        client_secret="test-secret",
    )

    payload, signature = token.access_token.split(".", 1)
    tampered = f"{payload}A.{signature}"

    with pytest.raises(InvalidTokenError):
        service.verify_token(tampered)


def test_expired_token_is_rejected() -> None:
    current_time = [1000]

    service = OAuthTokenService(
        make_settings(),
        clock=lambda: current_time[0],
    )

    token = service.issue_token(
        client_id="test-client",
        client_secret="test-secret",
    )

    current_time[0] = 1061

    with pytest.raises(InvalidTokenError):
        service.verify_token(token.access_token)
