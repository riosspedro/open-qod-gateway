import ssl

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.nef_client import build_nef_ssl_context


def make_settings(**changes: object) -> Settings:
    values: dict[str, object] = {
        "nef_client_id": "nef-client",
        "nef_client_secret": "nef-secret",
        "nef_notification_destination": "http://callback",
        "gateway_oauth_client_id": "test-client",
        "gateway_oauth_client_secret": "test-secret",
        "gateway_oauth_signing_secret": "test-signing-secret",
    }
    values.update(changes)

    return Settings(
        _env_file=None,
        **values,
    )


def test_tls_disabled_without_client_certificate_returns_false() -> None:
    settings = make_settings(
        nef_verify_tls=False,
    )

    assert build_nef_ssl_context(settings) is False


def test_client_certificate_and_key_must_be_configured_together() -> None:
    with pytest.raises(ValidationError):
        make_settings(
            nef_client_cert="/tmp/client.crt",
        )

    with pytest.raises(ValidationError):
        make_settings(
            nef_client_key="/tmp/client.key",
        )


def test_empty_tls_paths_are_normalized_to_none() -> None:
    settings = make_settings(
        nef_ca_bundle="",
        nef_client_cert="",
        nef_client_key="",
    )

    assert settings.nef_ca_bundle is None
    assert settings.nef_client_cert is None
    assert settings.nef_client_key is None


def test_verified_tls_loads_ca_and_client_certificate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, object] = {}

    class FakeContext:
        check_hostname = True
        verify_mode = ssl.CERT_REQUIRED

        def load_cert_chain(
            self,
            certfile: str,
            keyfile: str,
        ) -> None:
            calls["certfile"] = certfile
            calls["keyfile"] = keyfile

    fake_context = FakeContext()

    def fake_create_default_context(
        *,
        cafile: str | None = None,
    ) -> FakeContext:
        calls["cafile"] = cafile
        return fake_context

    monkeypatch.setattr(
        ssl,
        "create_default_context",
        fake_create_default_context,
    )

    settings = make_settings(
        nef_verify_tls=True,
        nef_ca_bundle="/tmp/ca.crt",
        nef_client_cert="/tmp/client.crt",
        nef_client_key="/tmp/client.key",
    )

    result = build_nef_ssl_context(settings)

    assert result is fake_context
    assert calls["cafile"] == "/tmp/ca.crt"
    assert calls["certfile"] == "/tmp/client.crt"
    assert calls["keyfile"] == "/tmp/client.key"
    assert fake_context.check_hostname is True
    assert fake_context.verify_mode == ssl.CERT_REQUIRED


def test_unverified_tls_can_still_load_client_certificate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, object] = {}

    class FakeContext:
        check_hostname = True
        verify_mode = ssl.CERT_REQUIRED

        def load_cert_chain(
            self,
            certfile: str,
            keyfile: str,
        ) -> None:
            calls["certfile"] = certfile
            calls["keyfile"] = keyfile

    fake_context = FakeContext()

    def fake_create_default_context(
        *,
        cafile: str | None = None,
    ) -> FakeContext:
        calls["cafile"] = cafile
        return fake_context

    monkeypatch.setattr(
        ssl,
        "create_default_context",
        fake_create_default_context,
    )

    settings = make_settings(
        nef_verify_tls=False,
        nef_client_cert="/tmp/client.crt",
        nef_client_key="/tmp/client.key",
    )

    result = build_nef_ssl_context(settings)

    assert result is fake_context
    assert calls["cafile"] is None
    assert fake_context.check_hostname is False
    assert fake_context.verify_mode == ssl.CERT_NONE
