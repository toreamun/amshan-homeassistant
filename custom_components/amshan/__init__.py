"""The AMS HAN meter integration."""
from __future__ import annotations

from asyncio import Queue, Task, gather
import logging
from types import MappingProxyType

from han.common import MeterMessageBase
from han.meter_connection import ConnectionManager
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import CALLBACK_TYPE, callback
from homeassistant.helpers.typing import ConfigType, EventType, HomeAssistantType

from .common import StopMessage
from .config import (
    CONF_CONNECTION_CONFIG,
    CONF_CONNECTION_TYPE,
    CONFIGURATION_SCHEMA,
    ConnectionType,
    async_migrate_config_entry,
)
from .conman import setup_meter_connection
from .const import DOMAIN
from .hass_mqtt import async_setup_meter_mqtt_subscriptions

_LOGGER: logging.Logger = logging.getLogger(__name__)

PLATFORM_TYPE = Platform.SENSOR

CONFIG_SCHEMA = CONFIGURATION_SCHEMA


class AmsHanIntegration:
    """AMS HAN integration."""

    def __init__(self) -> None:
        """Initialize AmsHanIntegration."""
        self._connection_manager: ConnectionManager | None = None
        self._mqtt_unsubscribe: CALLBACK_TYPE
        self._listeners: list[CALLBACK_TYPE] = []
        self._tasks: list[Task] = []
        self.measure_queue: Queue[MeterMessageBase] = Queue()

    async def async_setup_receiver(
        self, hass: HomeAssistantType, config: MappingProxyType
    ) -> None:
        """Set up MQTT or serial/tcp-ip receiver."""
        if ConnectionType.MQTT == ConnectionType(config[CONF_CONNECTION_TYPE]):
            self._mqtt_unsubscribe = await async_setup_meter_mqtt_subscriptions(
                hass, config[CONF_CONNECTION_CONFIG], self.measure_queue
            )
        else:
            manager = setup_meter_connection(
                hass.loop, config[CONF_CONNECTION_CONFIG], self.measure_queue
            )
            hass.loop.create_task(manager.connect_loop())
            self._connection_manager = manager

    def add_listener(self, listener_unsubscribe: CALLBACK_TYPE) -> None:
        """Add listener to be removed on unload."""
        self._listeners.append(listener_unsubscribe)

    def add_task(self, task: Task) -> None:
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
        await gather(*self._tasks)
        self._tasks.clear()

    def stop_receive(self) -> None:
        """Stop receivers (serial/tcpip and/or MQTT."""
        # signal processor to exit processing loop by sending empty bytes on the queue
        self.measure_queue.put_nowait(StopMessage())

        if self._connection_manager:
            self._connection_manager.close()
            self._connection_manager = None
        if self._mqtt_unsubscribe:
            self._mqtt_unsubscribe()
            self._mqtt_unsubscribe = None


async def async_setup(hass: HomeAssistantType, _: ConfigType) -> bool:
    """Set up the amshan component."""
    hass.data[DOMAIN] = {}
    return True


async def async_setup_entry(hass: HomeAssistantType, config_entry: ConfigEntry) -> bool:
    """Set up amshan from a config entry."""
    ctx = AmsHanIntegration()

    await ctx.async_setup_receiver(hass, config_entry.data)

    # Listen for Home Assistant stop event
    @callback
    async def on_hass_stop(event: EventType) -> None:
        _LOGGER.debug("%s received. Close down integration.", event.event_type)
        ctx.stop_receive()

    ctx.add_listener(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, on_hass_stop))

    # Listen for config entry changes and reload when changed.
    ctx.add_listener(config_entry.add_update_listener(async_config_entry_changed))

    hass.config_entries.async_setup_platforms(config_entry, [PLATFORM_TYPE])
    hass.data[DOMAIN][config_entry.entry_id] = ctx

    return True


async def async_migrate_entry(
    hass: HomeAssistantType, config_entry: ConfigEntry
) -> bool:
    """Migrate config when ConfigFlow version has changed."""
    return await async_migrate_config_entry(hass, config_entry)


async def async_unload_entry(
    hass: HomeAssistantType, config_entry: ConfigEntry
) -> bool:
    """Migrate config when ConfigFlow version has changed."""
    is_plaform_unload_success = await hass.config_entries.async_forward_entry_unload(
        config_entry, PLATFORM_TYPE
    )

    if is_plaform_unload_success:
        _LOGGER.info("Integrations is unloading.")
        ctx: AmsHanIntegration = hass.data[DOMAIN].pop(config_entry.entry_id)
        await ctx.async_close_all()

    return is_plaform_unload_success


@callback
async def async_config_entry_changed(
    hass: HomeAssistantType, config_entry: ConfigEntry
):
    """Handle config entry chnaged callback."""
    _LOGGER.info("Config entry has changed. Reload integration.")
    await hass.config_entries.async_reload(config_entry.entry_id)
