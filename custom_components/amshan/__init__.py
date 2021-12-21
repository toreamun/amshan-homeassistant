"""The AMS HAN meter integration."""
from __future__ import annotations

from asyncio import AbstractEventLoop, BaseProtocol, Queue
from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Any, Mapping, cast

from amshan import obis_map
from amshan.meter_connection import (
    AsyncConnectionFactory,
    ConnectionManager,
    MeterTransportProtocol,
    SmartMeterFrameContentProtocol,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType, EventType, HomeAssistantType
import serial_asyncio
import voluptuous as vol

from .const import (
    CONF_SERIAL_BAUDRATE,
    CONF_SERIAL_BYTESIZE,
    CONF_SERIAL_DSRDTR,
    CONF_SERIAL_PARITY,
    CONF_SERIAL_PORT,
    CONF_SERIAL_RTSCTS,
    CONF_SERIAL_STOPBITS,
    CONF_SERIAL_XONXOFF,
    CONF_TCP_HOST,
    CONF_TCP_PORT,
    DOMAIN,
    ENTRY_DATA_MEASURE_CONNECTION,
    ENTRY_DATA_MEASURE_QUEUE,
    ENTRY_DATA_UPDATE_LISTENER_UNSUBSCRIBE,
    HOSTNAME_IP4_IP6_REGEX,
)

_LOGGER: logging.Logger = logging.getLogger(__name__)

PLATFORM_TYPE = Platform.SENSOR

SERIAL_SCHEMA_DICT = {
    vol.Required(CONF_SERIAL_PORT): cv.string,
    vol.Optional(CONF_SERIAL_BAUDRATE, default=2400): cv.positive_int,
    vol.Optional(CONF_SERIAL_PARITY, default="N"): vol.In(["N", "E", "O"]),
    vol.Optional(CONF_SERIAL_BYTESIZE, default=8): vol.In([5, 6, 7, 8]),
    vol.Optional(CONF_SERIAL_STOPBITS, default="1"): vol.In([1, 1.5, 2]),
    vol.Optional(CONF_SERIAL_XONXOFF, default=False): cv.boolean,
    vol.Optional(CONF_SERIAL_RTSCTS, default=False): cv.boolean,
    vol.Optional(CONF_SERIAL_DSRDTR, default=False): cv.boolean,
}

TCP_SCHEMA_DICT = {
    vol.Required(CONF_TCP_HOST): vol.Match(
        HOSTNAME_IP4_IP6_REGEX, msg="Must be a valid hostname or ip address."
    ),
    vol.Required(CONF_TCP_PORT): vol.Range(0, 65353),
}

SERIAL_SCHEMA = vol.Schema(SERIAL_SCHEMA_DICT)
TCP_SCHEMA = vol.Schema(TCP_SCHEMA_DICT)
CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            vol.Any(SERIAL_SCHEMA, TCP_SCHEMA, msg="Requires tcp or serial settings.")
        )
    },
    extra=vol.ALLOW_EXTRA,
)

METER_DATA_INFO_KEYS = [
    obis_map.NEK_HAN_FIELD_METER_MANUFACTURER,
    obis_map.NEK_HAN_FIELD_METER_TYPE,
    obis_map.NEK_HAN_FIELD_OBIS_LIST_VER_ID,
    obis_map.NEK_HAN_FIELD_METER_ID,
]


async def async_setup(hass: HomeAssistantType, _: ConfigType) -> bool:
    """Set up the amshan component."""
    hass.data[DOMAIN] = {}
    return True


async def async_setup_entry(hass: HomeAssistantType, entry: ConfigEntry) -> bool:
    """Set up amshan from a config entry."""
    measure_queue: Queue[bytes] = Queue(loop=hass.loop)
    connection = setup_meter_connection(hass.loop, entry.data, measure_queue)

    hass.data[DOMAIN][entry.entry_id] = {
        ENTRY_DATA_MEASURE_CONNECTION: connection,
        ENTRY_DATA_MEASURE_QUEUE: measure_queue,
    }

    @callback
    async def on_hass_stop_close_connection(_: EventType) -> None:
        await async_close(measure_queue, connection)

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, on_hass_stop_close_connection)

    # Don't use hass.async_create_task, but schedule directly on the loop,
    # to avoid blocking startup.
    hass.loop.create_task(connection.connect_loop())

    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, PLATFORM_TYPE)
    )

    # Listen for config entry changes and reload when changed.
    listener = entry.add_update_listener(async_config_entry_changed)
    hass.data[DOMAIN][entry.entry_id][ENTRY_DATA_UPDATE_LISTENER_UNSUBSCRIBE] = listener

    return True


async def async_unload_entry(hass: HomeAssistantType, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unsubscribe_update_listener = hass.data[DOMAIN][entry.entry_id][
        ENTRY_DATA_UPDATE_LISTENER_UNSUBSCRIBE
    ]

    is_plaform_unload_success = await hass.config_entries.async_forward_entry_unload(
        entry, PLATFORM_TYPE
    )

    if is_plaform_unload_success:
        resources = hass.data[DOMAIN].pop(entry.entry_id)
        await async_close(
            resources[ENTRY_DATA_MEASURE_QUEUE],
            resources[ENTRY_DATA_MEASURE_CONNECTION],
        )
        unsubscribe_update_listener()

    return is_plaform_unload_success


@callback
async def async_config_entry_changed(hass: HomeAssistantType, entry: ConfigEntry):
    """Handle config entry chnaged callback."""
    _LOGGER.info("Config entry has change. Reload integration.")
    await hass.config_entries.async_reload(entry.entry_id)


async def async_close(
    measure_queue: "Queue[bytes]", connection: ConnectionManager
) -> None:
    """Close meter connection and measure processor."""
    connection.close()

    # signal processor to exit processing loop by sending empty bytes on the queue
    await measure_queue.put(bytes())


def setup_meter_connection(
    loop: AbstractEventLoop,
    config: Mapping[str, Any],
    measure_queue: Queue[bytes],
) -> ConnectionManager:
    """Initialize ConnectionManager using configured connection type."""
    connection_factory = get_connection_factory(loop, config, measure_queue)
    return ConnectionManager(connection_factory)


def get_connection_factory(
    loop: AbstractEventLoop,
    config: Mapping[str, Any],
    measure_queue: Queue[bytes],
) -> AsyncConnectionFactory:
    """Get connection factory based on configured connection type."""

    async def tcp_connection_factory() -> MeterTransportProtocol:
        connection = await loop.create_connection(
            lambda: cast(BaseProtocol, SmartMeterFrameContentProtocol(measure_queue)),
            host=config[CONF_TCP_HOST],
            port=config[CONF_TCP_PORT],
        )
        return cast(MeterTransportProtocol, connection)

    async def serial_connection_factory() -> MeterTransportProtocol:
        connection = await serial_asyncio.create_serial_connection(
            loop,
            lambda: SmartMeterFrameContentProtocol(measure_queue),
            url=config[CONF_SERIAL_PORT],
            baudrate=config[CONF_SERIAL_BAUDRATE],
            parity=config[CONF_SERIAL_PARITY],
            bytesize=config[CONF_SERIAL_BYTESIZE],
            stopbits=float(config[CONF_SERIAL_STOPBITS]),
            xonxoff=config[CONF_SERIAL_XONXOFF],
            rtscts=config[CONF_SERIAL_RTSCTS],
            dsrdtr=config[CONF_SERIAL_DSRDTR],
        )
        return cast(MeterTransportProtocol, connection)

    # select tcp or serial connection factory
    connection_factory = (
        tcp_connection_factory if CONF_TCP_HOST in config else serial_connection_factory
    )

    return connection_factory


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
        return cls(*[cast(str, measure_data[key]) for key in METER_DATA_INFO_KEYS])
