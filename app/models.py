from datetime import datetime
from enum import Enum
from ipaddress import IPv4Address, IPv4Network, ip_network
from typing import Any
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class ApiModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
        extra="forbid",
    )


class Device(ApiModel):
    ipv4_address: IPv4Address = Field(alias="ipv4Address")


class ApplicationServer(ApiModel):
    ipv4_address: str = Field(alias="ipv4Address")

    @field_validator("ipv4_address")
    @classmethod
    def validate_ipv4_subnet(cls, value: str) -> str:
        try:
            network = ip_network(value, strict=False)
        except ValueError as exc:
            raise ValueError(
                "applicationServer.ipv4Address deve ser um IPv4 "
                "ou uma sub-rede IPv4."
            ) from exc

        if not isinstance(network, IPv4Network):
            raise ValueError(
                "applicationServer.ipv4Address deve usar IPv4."
            )

        return str(network)


class QosStatus(str, Enum):
    REQUESTED = "REQUESTED"
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class CreateSessionRequest(ApiModel):
    device: Device
    application_server: ApplicationServer = Field(
        alias="applicationServer"
    )
    qos_profile: str = Field(
        alias="qosProfile",
        min_length=3,
        max_length=256,
        pattern=r"^[a-zA-Z0-9_.-]+$",
    )
    duration: int = Field(ge=1)


class UpdateSessionRequest(ApiModel):
    qos_profile: str | None = Field(
        default=None,
        alias="qosProfile",
        min_length=3,
        max_length=256,
        pattern=r"^[a-zA-Z0-9_.-]+$",
    )
    duration: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def require_at_least_one_change(
        self,
    ) -> "UpdateSessionRequest":
        if self.qos_profile is None and self.duration is None:
            raise ValueError(
                "Informe qosProfile ou duration para atualizar."
            )

        return self


class SessionInfo(ApiModel):
    session_id: UUID = Field(alias="sessionId")
    device: Device
    application_server: ApplicationServer = Field(
        alias="applicationServer"
    )
    qos_profile: str = Field(alias="qosProfile")
    duration: int = Field(ge=1)
    qos_status: QosStatus = Field(alias="qosStatus")
    started_at: datetime | None = Field(
        default=None,
        alias="startedAt",
    )
    expires_at: datetime | None = Field(
        default=None,
        alias="expiresAt",
    )
    nef_subscription_id: str | None = Field(
        default=None,
        alias="nefSubscriptionId",
        exclude=True,
    )


class ApiError(ApiModel):
    status: int
    code: str
    message: str
    details: list[Any] = Field(default_factory=list)
