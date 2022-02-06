"""Types used accross AMSHAN."""
from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
from enum import Enum
from typing import cast

from han import common as han_type, obis_map

_METER_DATA_INFO_KEYS = [
    obis_map.FIELD_METER_MANUFACTURER,
    obis_map.FIELD_METER_MANUFACTURER_ID,
    obis_map.FIELD_METER_TYPE,
    obis_map.FIELD_METER_TYPE_ID,
    obis_map.FIELD_OBIS_LIST_VER_ID,
    obis_map.FIELD_METER_ID,
]


@dataclass
class MeterInfo:
    """Info about meter."""

    manufacturer: str | None
    manufacturer_id: str | None
    type: str | None
    type_id: str | None
    list_version_id: str
    meter_id: str | None

    @property
    def unique_id(self) -> str | None:
        """Meter unique id."""
        if self.meter_id:
            return f"{self.manufacturer}-{self.type}-{self.meter_id}".lower()
        return None

    @classmethod
    def from_measure_data(
        cls, measure_data: dict[str, str | int | float | dt.datetime]
    ) -> MeterInfo:
        """Create MeterInfo from measure_data dictionary."""
        return cls(*[cast(str, measure_data.get(key)) for key in _METER_DATA_INFO_KEYS])


class ConnectionType(Enum):
    """Meter connection type."""

    SERIAL = "serial"
    NETWORK = "network_tcpip"
    MQTT = "hass_mqtt"


class StopMessage(han_type.MeterMessageBase):
    """Special message top signal stop. No more messages."""

    @property
    def message_type(self) -> han_type.MeterMessageType:
        """Return MeterMessageType of message."""
        return han_type.MeterMessageType.UNKNOWN

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
