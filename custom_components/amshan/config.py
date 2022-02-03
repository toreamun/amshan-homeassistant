"""Configration module."""
from __future__ import annotations

from collections.abc import Callable
from enum import Enum
import logging

import amshan.obis_map as obis_map
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
import homeassistant.const as hassconst
from homeassistant.const import POWER_VOLT_AMPERE_REACTIVE
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_registry import RegistryEntry, async_get_registry
from homeassistant.helpers.typing import HomeAssistantType
import voluptuous as vol

from .const import DOMAIN, HOSTNAME_IP4_IP6_REGEX

_LOGGER = logging.getLogger(__name__)

CONF_CONNECTION_TYPE = "connection_type"
CONF_CONNECTION_CONFIG = "connection"

CONF_SERIAL_PORT = hassconst.CONF_PORT
CONF_SERIAL_BAUDRATE = "baudrate"
CONF_SERIAL_PARITY = "parity"
CONF_SERIAL_BYTESIZE = "bytesize"
CONF_SERIAL_STOPBITS = "stopbits"
CONF_SERIAL_XONXOFF = "xonxoff"
CONF_SERIAL_RTSCTS = "rtscts"
CONF_SERIAL_DSRDTR = "dsrdtr"

CONF_TCP_HOST = hassconst.CONF_HOST
CONF_TCP_PORT = hassconst.CONF_PORT

CONF_MQTT_TOPICS = "mqtt_topics"

CONF_OPTIONS_SCALE_FACTOR = "scale_factor"


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

CONFIGURATION_SCHEMA = vol.Schema(
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


async def async_migrate_config_entry(
    hass: HomeAssistantType, config_entry: ConfigEntry
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


def _migrate_entity_entry_from_v1_to_v2(entity: RegistryEntry):
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


V3_MIGRATE = [
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


def _migrate_entity_entry_from_v2_to_v3(entity: RegistryEntry):
    update = {}

    for measure_id in V3_MIGRATE:
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
                update["device_class"] = SensorDeviceClass.REACTIVE_POWER
                update["unit_of_measurement"] = POWER_VOLT_AMPERE_REACTIVE
                _LOGGER.info(
                    "Migrated %s to device class %s with unit %s",
                    entity.unique_id,
                    SensorDeviceClass.REACTIVE_POWER,
                    POWER_VOLT_AMPERE_REACTIVE,
                )

            break

    return update


async def _async_migrate_entries(
    hass: HomeAssistant,
    config_entry_id: str,
    entry_callback: Callable[[RegistryEntry], dict | None],
) -> None:
    ent_reg = await async_get_registry(hass)

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
