from dataclasses import dataclass


class UnknownQosProfileError(ValueError):
    pass


@dataclass(frozen=True)
class QosProfile:
    name: str
    guaranteed_bandwidth: str
    maximum_bandwidth: str


_PROFILES: dict[str, QosProfile] = {
    "QOS_M": QosProfile(
        name="QOS_M",
        guaranteed_bandwidth="10 Mbps",
        maximum_bandwidth="20 Mbps",
    ),
    "QOS_HIGH": QosProfile(
        name="QOS_HIGH",
        guaranteed_bandwidth="12 Mbps",
        maximum_bandwidth="24 Mbps",
    ),
}


def get_qos_profile(name: str) -> QosProfile:
    try:
        return _PROFILES[name]
    except KeyError as exc:
        available = ", ".join(sorted(_PROFILES))

        raise UnknownQosProfileError(
            f"Perfil QoS desconhecido: {name}. "
            f"Perfis disponíveis: {available}."
        ) from exc


def list_qos_profiles() -> list[QosProfile]:
    return list(_PROFILES.values())
