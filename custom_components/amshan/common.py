"""Types used accross AMSHAN."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import cast

from han import obis_map
from han.common import MeterMessageBase, MeterMessageType

_METER_DATA_INFO_KEYS = [
    obis_map.FIELD_METER_MANUFACTURER,
    obis_map.FIELD_METER_TYPE,
    obis_map.FIELD_OBIS_LIST_VER_ID,
    obis_map.FIELD_METER_ID,
]


@dataclass
class MeterInfo:
    """Info about meter."""

    manufacturer: str
    type: str
    list_version_id: str
    meter_id: str

    @property
    def unique_id(self) -> str:
        """Meter unique id."""
        return f"{self.manufacturer}-{self.type}-{self.meter_id}".lower()

    @classmethod
    def from_measure_data(
        cls, measure_data: dict[str, str | int | float | datetime]
    ) -> MeterInfo:
        """Create MeterInfo from measure_data dictionary."""
        return cls(*[cast(str, measure_data[key]) for key in _METER_DATA_INFO_KEYS])


class ConnectionType(Enum):
    """Meter connection type."""

    SERIAL = "serial"
    NETWORK = "network_tcpip"
    MQTT = "hass_mqtt"


class DlmsMessage(MeterMessageBase):
    """Mesage containing DLMS (binary) message without HDLC framing."""

    def __init__(self, binary: bytes) -> None:
        """Initialize DlmsMessage."""
        super().__init__()
        self._binary: bytes = binary

    @property
    def message_type(self) -> MeterMessageType:
        """Return MeterMessageType of message."""
        return MeterMessageType.HDLC_DLMS

    @property
    def is_valid(self) -> bool:
        """Return False for stop message."""
        return len(self._binary) > 4

    @property
    def as_bytes(self) -> bytes | None:
        """Return None for stop message."""
        return self._binary

    @property
    def payload(self) -> bytes | None:
        """Return None for stop message."""
        return self._binary


class StopMessage(MeterMessageBase):
    """Special message top signal stop. No more messages."""

    @property
    def message_type(self) -> MeterMessageType:
        """Return MeterMessageType of message."""
        return MeterMessageType.HDLC_DLMS

    @property
    def is_valid(self) -> bool:
        """Return False for stop message."""
        return False

    @property
    def as_bytes(self) -> bytes | None:
        """Return None for stop message."""
        return None

    @property
    def payload(self) -> bytes | None:
        """Return None for stop message."""
        return None
