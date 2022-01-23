"""The AMS HAN meter integration."""
from __future__ import annotations

from asyncio import AbstractEventLoop, BaseProtocol, Queue
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import json
import logging
from typing import Any, Callable, List, Mapping, cast

from amshan import obis_map
from amshan.hdlc import HdlcFrame, HdlcFrameReader
from amshan.meter_connection import (
    AsyncConnectionFactory,
    ConnectionManager,
    MeterTransportProtocol,
    SmartMeterFrameContentProtocol,
)
from homeassistant.components import mqtt
from homeassistant.components.mqtt.models import ReceiveMessage
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_registry import RegistryEntry, async_migrate_entries
from homeassistant.helpers.typing import ConfigType, EventType, HomeAssistantType
import serial_asyncio
import voluptuous as vol

from .const import (
    CONF_CONNECTION_CONFIG,
    CONF_CONNECTION_TYPE,
    CONF_MQTT_TOPICS,
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
    ENTRY_DATA_MEASURE_MQTT_SUBSCRIPTIONS,
    ENTRY_DATA_MEASURE_QUEUE,
    ENTRY_DATA_UPDATE_LISTENER_UNSUBSCRIBE,
    HOSTNAME_IP4_IP6_REGEX,
)

_LOGGER: logging.Logger = logging.getLogger(__name__)

PLATFORM_TYPE = Platform.SENSOR


class ConnectionType(Enum):
    """Meter connection type."""

    SERIAL = "serial"
    NETWORK = "network_tcpip"
    MQTT = "hass_mqtt"


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
        HOSTNAME_IP4_IP6_REGEX, msg="Must be a valid hostname or an IP address."
    ),
    vol.Required(CONF_TCP_PORT): vol.Range(0, 65535),
}

HASS_MSMQ_SCHEMA_DICT = {
    vol.Required(CONF_MQTT_TOPICS): cv.string,
}

SERIAL_SCHEMA = vol.Schema(SERIAL_SCHEMA_DICT)
TCP_SCHEMA = vol.Schema(TCP_SCHEMA_DICT)
HASS_MSMQ_SCHEMA = vol.Schema(HASS_MSMQ_SCHEMA_DICT)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_CONNECTION_TYPE): cv.enum(ConnectionType),
                vol.Required(CONF_CONNECTION_CONFIG): vol.Any(
                    SERIAL_SCHEMA,
                    TCP_SCHEMA,
                    HASS_MSMQ_SCHEMA,
                ),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

METER_DATA_INFO_KEYS = [
    obis_map.FIELD_METER_MANUFACTURER,
    obis_map.FIELD_METER_TYPE,
    obis_map.FIELD_OBIS_LIST_VER_ID,
    obis_map.FIELD_METER_ID,
]


async def async_setup(hass: HomeAssistantType, _: ConfigType) -> bool:
    """Set up the amshan component."""
    hass.data[DOMAIN] = {}
    return True


async def async_setup_entry(hass: HomeAssistantType, entry: ConfigEntry) -> bool:
    """Set up amshan from a config entry."""
    measure_queue: Queue[bytes] = Queue(loop=hass.loop)

    connection = None
    mqtt_unsubscribe = None

    connection_type = ConnectionType(entry.data[CONF_CONNECTION_TYPE])
    if connection_type == ConnectionType.MQTT:
        mqtt_unsubscribe = await async_setup_meter_mqtt_subscriptions(
            hass, entry.data[CONF_CONNECTION_CONFIG], measure_queue
        )
    else:
        connection = setup_meter_connection(
            hass.loop, entry.data[CONF_CONNECTION_CONFIG], measure_queue
        )

    hass.data[DOMAIN][entry.entry_id] = {
        ENTRY_DATA_MEASURE_CONNECTION: connection,
        ENTRY_DATA_MEASURE_MQTT_SUBSCRIPTIONS: mqtt_unsubscribe,
        ENTRY_DATA_MEASURE_QUEUE: measure_queue,
    }

    @callback
    async def on_hass_stop(_: EventType) -> None:
        await async_close(measure_queue, connection, mqtt_unsubscribe)

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, on_hass_stop)

    if connection:
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


async def async_migrate_entry(
    hass: HomeAssistantType, config_entry: ConfigEntry
) -> bool:
    """Migrate config entry if needed."""
    initial_version = config_entry.version
    _LOGGER.debug("Check for config entry migration of version %d", initial_version)

    def replace_ending(source, old, new):
        if source.endswith(old):
            return source[: -len(old)] + new
        return source

    def migrate_entity_entry(entity: RegistryEntry):
        update = {}
        if entity.unique_id.endswith("_hour"):
            new_unique_id = replace_ending(entity.unique_id, "_hour", "_total")
            _LOGGER.info(
                "Migrate unique_id from %s to %s", entity.unique_id, new_unique_id
            )
            update["new_unique_id"] = new_unique_id
        return update

    if config_entry.version == 1:
        await async_migrate_entries(hass, config_entry.entry_id, migrate_entity_entry)
        config_entry.version = 2
        version2_config = {
            CONF_CONNECTION_TYPE: (
                ConnectionType.MQTT
                if CONF_MQTT_TOPICS in config_entry.data
                else ConnectionType.NETWORK
                if CONF_TCP_HOST in config_entry.data
                else ConnectionType.SERIAL
            ).value,
            CONF_CONNECTION_CONFIG: {**config_entry.data},
        }
        hass.config_entries.async_update_entry(config_entry, data=version2_config)
        _LOGGER.debug("Config entry migrated to version %d", initial_version)

    if config_entry.version == initial_version:
        _LOGGER.debug(
            "Current config version %d is already the current version.", initial_version
        )
    else:
        _LOGGER.debug("Config entry migration successfull.")

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
            resources[ENTRY_DATA_MEASURE_MQTT_SUBSCRIPTIONS],
        )
        unsubscribe_update_listener()

    return is_plaform_unload_success


@callback
async def async_config_entry_changed(hass: HomeAssistantType, entry: ConfigEntry):
    """Handle config entry chnaged callback."""
    _LOGGER.info("Config entry has changed. Reload integration.")
    await hass.config_entries.async_reload(entry.entry_id)


async def async_close(
    measure_queue: "Queue[bytes]",
    connection: ConnectionManager | None,
    mqtt_unsubscribe: Callable | None,
) -> None:
    """Close meter connection and measure processor."""
    _LOGGER.info("Close down integration.")
    if connection:
        connection.close()

    if mqtt_unsubscribe:
        mqtt_unsubscribe()

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


def try_read_hdlc_frame(payload: bytes) -> HdlcFrame | None:
    """Try to parse HDLC-frame from payload."""
    frame_reader = HdlcFrameReader(False)

    # Reader expects flag sequence in start and end.
    flag_seqeuence = HdlcFrameReader.FLAG_SEQUENCE.to_bytes(1, byteorder="big")
    if not payload.startswith(flag_seqeuence):
        frame_reader.read(flag_seqeuence)

    frames = frame_reader.read(payload)
    if len(frames) == 0:
        # add flag sequence to the end
        frames = frame_reader.read(flag_seqeuence)

    if len(frames) > 0:
        return frames[0]

    return None


def get_frame_information(mqtt_message: ReceiveMessage) -> bytes | None:
    """Get frame information part from mqtt message."""
    # Try first to read as HDLC-frame.
    frame = try_read_hdlc_frame(mqtt_message.payload)
    if frame is not None:
        if frame.is_good_ffc and frame.is_expected_length:
            if frame.information is not None:
                _LOGGER.debug(
                    "Got valid frame of expected length with correct checksum from topic %s: %s",
                    mqtt_message.topic,
                    mqtt_message.payload.hex(),
                )
                return frame.information
            else:
                _LOGGER.debug(
                    "Got empty frame of expected length with correct checksum from topic %s: %s",
                    mqtt_message.topic,
                    mqtt_message.payload.hex(),
                )

        _LOGGER.debug(
            "Got invalid frame (ffc is %s and expected length is %s) from topic %s: %s",
            frame.is_good_ffc,
            frame.is_expected_length,
            mqtt_message.topic,
            mqtt_message.payload.hex(),
        )
        return None

    try:
        json_data = json.loads(mqtt_message.payload)
        _LOGGER.debug(
            "Ignore JSON in payload without HDLC framing from topic %s: %s",
            mqtt_message.topic,
            json_data,
        )
        return None
    except ValueError:
        pass

    _LOGGER.debug(
        "Got payload without HDLC framing from topic %s: %s",
        mqtt_message.topic,
        mqtt_message.payload.hex(),
    )
    return mqtt_message.payload


async def async_setup_meter_mqtt_subscriptions(
    hass: HomeAssistantType, config: Mapping[str, Any], measure_queue: "Queue[bytes]"
) -> Callable:
    """Set up MQTT topic subscriptions."""

    @callback
    def message_received(mqtt_message: ReceiveMessage):
        """Handle new MQTT messages."""
        information = get_frame_information(mqtt_message)
        if information:
            measure_queue.put_nowait(information)

    unsubscibers: List[Callable] = []
    topics = {x.strip() for x in config[CONF_MQTT_TOPICS].split(",")}
    for topic in topics:
        unsubscibers.append(
            await mqtt.async_subscribe(hass, topic, message_received, 1, encoding=None)
        )

    def unsubscribe_mqtt():
        _LOGGER.debug("Unsubscribe %d MQTT topic(s)", len(unsubscibers))
        for unsubscribe in unsubscibers:
            unsubscribe()

    return unsubscribe_mqtt


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
