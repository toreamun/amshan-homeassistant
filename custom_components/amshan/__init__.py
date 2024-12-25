"""The AMS HAN meter integration."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import datetime as dt
from enum import Enum
import logging
from typing import Callable, Mapping, cast

from han import common as han_type, meter_connection, obis_map
from homeassistant import const as ha_const
from homeassistant.const import UnitOfReactivePower
from homeassistant.components import sensor as ha_sensor
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, callback, HomeAssistant, Event
from homeassistant.helpers import entity_registry
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_CONNECTION_CONFIG,
    CONF_CONNECTION_TYPE,
    CONF_MQTT_TOPICS,
    CONF_TCP_HOST,
)
from .metercon import async_setup_meter_mqtt_subscriptions, setup_meter_connection

_LOGGER: logging.Logger = logging.getLogger(__name__)

PLATFORM_TYPE = ha_const.Platform.SENSOR

type AmsHanConfigEntry = ConfigEntry[AmsHanData]


@dataclass
class AmsHanData:
    integration: AmsHanIntegration


class ConnectionType(Enum):
    """Meter connection type."""

    SERIAL = "serial"
    NETWORK = "network_tcpip"
    MQTT = "hass_mqtt"


class AmsHanIntegration:
    """AMS HAN integration."""

    def __init__(self) -> None:
        """Initialize AmsHanIntegration."""
        self._connection_manager: meter_connection.ConnectionManager | None = None
        self._mqtt_unsubscribe: CALLBACK_TYPE | None = None
        self._listeners: list[CALLBACK_TYPE] = []
        self._tasks: list[asyncio.Task] = []
        self.measure_queue: asyncio.Queue[han_type.MeterMessageBase] = asyncio.Queue()

    async def async_setup_receiver(
        self, hass: HomeAssistant, config_data: Mapping
    ) -> None:
        """Set up MQTT or serial/tcp-ip receiver."""
        connection_type = ConnectionType(config_data[CONF_CONNECTION_TYPE])
        if ConnectionType.MQTT == connection_type:
            self._mqtt_unsubscribe = await async_setup_meter_mqtt_subscriptions(
                hass,
                config_data[CONF_CONNECTION_CONFIG],
                self.measure_queue,
            )
        else:
            manager = setup_meter_connection(
                hass.loop,
                config_data[CONF_CONNECTION_CONFIG],
                self.measure_queue,
            )
            hass.loop.create_task(manager.connect_loop())
            self._connection_manager = manager

        _LOGGER.debug("Configured %s receiver.", connection_type)

    def add_listener(self, listener_unsubscribe: CALLBACK_TYPE) -> None:
        """Add listener to be removed on unload."""
        self._listeners.append(listener_unsubscribe)

    def add_task(self, task: asyncio.Task) -> None:
        """Add task to be cancelled on close/unload."""
        self._tasks.append(task)

    async def async_close_all(self) -> None:
        """Stop receive, unsubscribe listeners and cancel tasks."""
        self.stop_receive()

        for unsub in self._listeners:
            unsub()
        self._listeners.clear()

        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks)
        self._tasks.clear()

    def stop_receive(self) -> None:
        """Stop receivers (serial/tcp-ip and/or MQTT."""
        # signal processor to exit processing loop by sending empty bytes on the queue
        self.measure_queue.put_nowait(StopMessage())

        if self._connection_manager:
            self._connection_manager.close()
            self._connection_manager = None
        if self._mqtt_unsubscribe:
            self._mqtt_unsubscribe()
            self._mqtt_unsubscribe = None


async def async_setup(hass: HomeAssistant, _: ConfigType) -> bool:
    """Set up the amshan component."""
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: AmsHanConfigEntry) -> bool:
    """Set up amshan from a config entry."""
    integration = AmsHanIntegration()

    await integration.async_setup_receiver(hass, config_entry.data)

    # Listen for Home Assistant stop event
    @callback
    async def on_hass_stop(event: Event) -> None:
        _LOGGER.debug("%s received. Close down integration.", event.event_type)
        integration.stop_receive()

    integration.add_listener(
        hass.bus.async_listen_once(ha_const.EVENT_HOMEASSISTANT_STOP, on_hass_stop)
    )

    # Listen for config entry changes and reload when changed.
    integration.add_listener(
        config_entry.add_update_listener(async_config_entry_changed)
    )

    config_entry.runtime_data = AmsHanData(integration)

    await hass.config_entries.async_forward_entry_setup(config_entry, PLATFORM_TYPE)

    _LOGGER.debug("async_setup_entry complete.")

    return True


async def async_migrate_config_entry(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> bool:
    """Migrate config when ConfigFlow version has changed."""
    initial_version = config_entry.version
    current_data = config_entry.data
    _LOGGER.debug("Check for config entry migration of version %d", initial_version)

    if config_entry.version == 1:
        await _async_migrate_entries(
            hass, config_entry.entry_id, _migrate_entity_entry_from_v1_to_v2
        )
        config_entry.version = 2
        current_data = {
            CONF_CONNECTION_TYPE: (
                ConnectionType.MQTT
                if CONF_MQTT_TOPICS in config_entry.data
                else ConnectionType.NETWORK
                if CONF_TCP_HOST in config_entry.data
                else ConnectionType.SERIAL
            ).value,
            CONF_CONNECTION_CONFIG: {**current_data},
        }
        _LOGGER.debug("Config entry migrated to version 2")

    if config_entry.version == 2:
        config_entry.version = 3
        await _async_migrate_entries(
            hass, config_entry.entry_id, _migrate_entity_entry_from_v2_to_v3
        )
        _LOGGER.debug("Config entry migrated to version 3")

    hass.config_entries.async_update_entry(config_entry, data=current_data)
    _LOGGER.debug(
        "Config entry migration from %d to %d successfull.",
        initial_version,
        config_entry.version,
    )

    return True


async def async_unload_entry(
    hass: HomeAssistant, config_entry: AmsHanConfigEntry
) -> bool:
    """Handle removal of an entry."""
    is_plaform_unload_success = await hass.config_entries.async_forward_entry_unload(
        config_entry, PLATFORM_TYPE
    )

    if is_plaform_unload_success:
        _LOGGER.info("Integrations is unloading.")
        await config_entry.runtime_data.integration.async_close_all()

    return is_plaform_unload_success


@callback
async def async_config_entry_changed(
    hass: HomeAssistant, config_entry: ConfigEntry
):
    """Handle config entry changed callback."""
    _LOGGER.info("Config entry has changed. Reload integration.")
    await hass.config_entries.async_reload(config_entry.entry_id)


def _migrate_entity_entry_from_v1_to_v2(entity: entity_registry.RegistryEntry):
    def replace_ending(source, old, new):
        if source.endswith(old):
            return source[: -len(old)] + new
        return source

    update = {}
    if entity.unique_id.endswith("_hour"):
        new_unique_id = replace_ending(entity.unique_id, "_hour", "_total")
        _LOGGER.info("Migrate unique_id from %s to %s", entity.unique_id, new_unique_id)
        update["new_unique_id"] = new_unique_id
    return update


def _migrate_entity_entry_from_v2_to_v3(entity: entity_registry.RegistryEntry):
    update = {}

    v3_migrate_fields = [
        obis_map.FIELD_METER_ID,
        obis_map.FIELD_METER_MANUFACTURER,
        obis_map.FIELD_METER_TYPE,
        obis_map.FIELD_OBIS_LIST_VER_ID,
        obis_map.FIELD_ACTIVE_POWER_IMPORT,
        obis_map.FIELD_ACTIVE_POWER_EXPORT,
        obis_map.FIELD_REACTIVE_POWER_IMPORT,
        obis_map.FIELD_REACTIVE_POWER_EXPORT,
        obis_map.FIELD_CURRENT_L1,
        obis_map.FIELD_CURRENT_L2,
        obis_map.FIELD_CURRENT_L3,
        obis_map.FIELD_VOLTAGE_L1,
        obis_map.FIELD_VOLTAGE_L2,
        obis_map.FIELD_VOLTAGE_L3,
        obis_map.FIELD_ACTIVE_POWER_IMPORT_TOTAL,
        obis_map.FIELD_ACTIVE_POWER_EXPORT_TOTAL,
        obis_map.FIELD_REACTIVE_POWER_IMPORT_TOTAL,
        obis_map.FIELD_REACTIVE_POWER_EXPORT_TOTAL,
    ]

    for measure_id in v3_migrate_fields:
        if entity.unique_id.endswith(f"-{measure_id}"):
            manufacturer = entity.unique_id[: entity.unique_id.find("-")]
            new_entity_id = f"sensor.{manufacturer}_{measure_id}".lower()
            if new_entity_id != entity.entity_id:
                update["new_entity_id"] = new_entity_id
                _LOGGER.info(
                    "Migrate entity_id from %s to %s",
                    entity.entity_id,
                    new_entity_id,
                )

            if measure_id in (
                obis_map.FIELD_REACTIVE_POWER_IMPORT,
                obis_map.FIELD_REACTIVE_POWER_EXPORT,
            ):
                update["device_class"] = ha_sensor.SensorDeviceClass.REACTIVE_POWER
                update["unit_of_measurement"] = UnitOfReactivePower.VOLT_AMPERE_REACTIVE
                _LOGGER.info(
                    "Migrated %s to device class %s with unit %s",
                    entity.unique_id,
                    ha_sensor.SensorDeviceClass.REACTIVE_POWER,
                    UnitOfReactivePower.VOLT_AMPERE_REACTIVE,
                )

            break

    return update


async def _async_migrate_entries(
    hass: HomeAssistant,
    config_entry_id: str,
    entry_callback: Callable[[entity_registry.RegistryEntry], dict | None],
) -> None:
    ent_reg = await entity_registry.async_get_registry(hass)

    # Workaround:
    # entity_registry.async_migrate_entries fails with:
    #   "RuntimeError: dictionary keys changed during iteration"
    # Try to get all entries from the dictionary before working on them.
    # The migration dows not directly change any keys of the registry. Concurrency problem in HA?

    entries = []
    for entry in ent_reg.entities.values():
        if entry.config_entry_id == config_entry_id:
            entries.append(entry)

    for entry in entries:
        updates = entry_callback(entry)
        if updates is not None:
            ent_reg.async_update_entity(entry.entity_id, **updates)


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
        return cls(
            *[
                cast(str, measure_data.get(key))
                for key in [
                    obis_map.FIELD_METER_MANUFACTURER,
                    obis_map.FIELD_METER_MANUFACTURER_ID,
                    obis_map.FIELD_METER_TYPE,
                    obis_map.FIELD_METER_TYPE_ID,
                    obis_map.FIELD_OBIS_LIST_VER_ID,
                    obis_map.FIELD_METER_ID,
                ]
            ]
        )


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
