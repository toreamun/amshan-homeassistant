"""Configration module."""
from __future__ import annotations

from enum import Enum
import logging

from homeassistant.config_entries import ConfigEntry
import homeassistant.const as hassconst
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_registry import RegistryEntry, async_migrate_entries
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
