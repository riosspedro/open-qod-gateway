import pytest
from pydantic import ValidationError

from app.models import CreateSessionRequest
from app.profiles import (
    UnknownQosProfileError,
    get_qos_profile,
    list_qos_profiles,
)


VALID_REQUEST = {
    "device": {
        "ipv4Address": "10.61.0.1",
    },
    "applicationServer": {
        "ipv4Address": "10.100.200.1/32",
    },
    "qosProfile": "QOS_M",
    "duration": 300,
}


def test_create_session_request_accepts_valid_payload() -> None:
    request = CreateSessionRequest.model_validate(VALID_REQUEST)

    assert str(request.device.ipv4_address) == "10.61.0.1"
    assert request.application_server.ipv4_address == "10.100.200.1/32"
    assert request.qos_profile == "QOS_M"
    assert request.duration == 300

    serialized = request.model_dump(
        by_alias=True,
        mode="json",
    )

    assert serialized == VALID_REQUEST


def test_device_is_required_for_two_legged_subset() -> None:
    payload = dict(VALID_REQUEST)
    payload.pop("device")

    with pytest.raises(ValidationError):
        CreateSessionRequest.model_validate(payload)


def test_invalid_application_server_is_rejected() -> None:
    payload = {
        **VALID_REQUEST,
        "applicationServer": {
            "ipv4Address": "servidor-invalido",
        },
    }

    with pytest.raises(ValidationError):
        CreateSessionRequest.model_validate(payload)


def test_ipv4_host_is_normalized_as_single_host_subnet() -> None:
    payload = {
        **VALID_REQUEST,
        "applicationServer": {
            "ipv4Address": "10.100.200.1",
        },
    }

    request = CreateSessionRequest.model_validate(payload)

    assert request.application_server.ipv4_address == "10.100.200.1/32"


def test_local_qos_profile_maps_to_validated_rates() -> None:
    profile = get_qos_profile("QOS_M")

    assert profile.guaranteed_bandwidth == "10 Mbps"
    assert profile.maximum_bandwidth == "20 Mbps"


def test_unknown_qos_profile_is_rejected() -> None:
    with pytest.raises(UnknownQosProfileError):
        get_qos_profile("QOS_INEXISTENTE")


def test_profile_registry_contains_qos_m() -> None:
    names = [profile.name for profile in list_qos_profiles()]

    assert set(names) == {"QOS_M", "QOS_HIGH"}
