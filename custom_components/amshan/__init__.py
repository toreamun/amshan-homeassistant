"""The AMS HAN meter integration."""
from __future__ import annotations

from asyncio import Queue
from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Callable, cast

from amshan import obis_map
from amshan.meter_connection import ConnectionManager
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import callback
from homeassistant.helpers.typing import ConfigType, EventType, HomeAssistantType

from .config import (
    CONF_CONNECTION_CONFIG,
    CONF_CONNECTION_TYPE,
    CONFIGURATION_SCHEMA,
    ConnectionType,
    async_migrate_config_entry,
)
from .conman import setup_meter_connection
from .const import (
    DOMAIN,
    ENTRY_DATA_MEASURE_CONNECTION,
    ENTRY_DATA_MEASURE_MQTT_SUBSCRIPTIONS,
    ENTRY_DATA_MEASURE_QUEUE,
    ENTRY_DATA_UPDATE_LISTENER_UNSUBSCRIBE,
)
from .hass_mqtt import async_setup_meter_mqtt_subscriptions

_LOGGER: logging.Logger = logging.getLogger(__name__)

PLATFORM_TYPE = Platform.SENSOR

CONFIG_SCHEMA = CONFIGURATION_SCHEMA


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


async def async_setup_entry(hass: HomeAssistantType, config_entry: ConfigEntry) -> bool:
    """Set up amshan from a config entry."""
    measure_queue: Queue[bytes] = Queue(loop=hass.loop)

    connection = None
    mqtt_unsubscribe = None

    connection_type = ConnectionType(config_entry.data[CONF_CONNECTION_TYPE])
    if connection_type == ConnectionType.MQTT:
        mqtt_unsubscribe = await async_setup_meter_mqtt_subscriptions(
            hass, config_entry.data[CONF_CONNECTION_CONFIG], measure_queue
        )
    else:
        connection = setup_meter_connection(
            hass.loop, config_entry.data[CONF_CONNECTION_CONFIG], measure_queue
        )

    hass.data[DOMAIN][config_entry.entry_id] = {
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
        hass.config_entries.async_forward_entry_setup(config_entry, PLATFORM_TYPE)
    )

    # Listen for config entry changes and reload when changed.
    listener = config_entry.add_update_listener(async_config_entry_changed)
    hass.data[DOMAIN][config_entry.entry_id][
        ENTRY_DATA_UPDATE_LISTENER_UNSUBSCRIBE
    ] = listener

    return True


async def async_migrate_entry(
    hass: HomeAssistantType, config_entry: ConfigEntry
) -> bool:
    """Migrate config when ConfigFlow version has changed."""
    await async_migrate_config_entry(hass, config_entry)


async def async_unload_entry(
    hass: HomeAssistantType, config_entry: ConfigEntry
) -> bool:
    """Migrate config when ConfigFlow version has changed."""
    unsubscribe_update_listener = hass.data[DOMAIN][config_entry.entry_id][
        ENTRY_DATA_UPDATE_LISTENER_UNSUBSCRIBE
    ]

    is_plaform_unload_success = await hass.config_entries.async_forward_entry_unload(
        config_entry, PLATFORM_TYPE
    )

    if is_plaform_unload_success:
        resources = hass.data[DOMAIN].pop(config_entry.entry_id)
        await async_close(
            resources[ENTRY_DATA_MEASURE_QUEUE],
            resources[ENTRY_DATA_MEASURE_CONNECTION],
            resources[ENTRY_DATA_MEASURE_MQTT_SUBSCRIPTIONS],
        )
        unsubscribe_update_listener()

    return is_plaform_unload_success


@callback
async def async_config_entry_changed(
    hass: HomeAssistantType, config_entry: ConfigEntry
):
    """Handle config entry chnaged callback."""
    _LOGGER.info("Config entry has changed. Reload integration.")
    await hass.config_entries.async_reload(config_entry.entry_id)


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
