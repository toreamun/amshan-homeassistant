"""Config flow for AMS HAN meter integration."""
from __future__ import annotations

import asyncio
import logging
import os
import socket
from typing import Any

import async_timeout
from han import autodecoder, common as han_type, obis_map
from homeassistant import config_entries
from homeassistant.components import mqtt
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv
from homeassistant.core import HomeAssistant
import serial
import voluptuous as vol

from . import ConnectionType, MeterInfo
from .const import (
    CONF_CONNECTION_CONFIG,
    CONF_CONNECTION_TYPE,
    CONF_MQTT_TOPICS,
    CONF_OPTIONS_SCALE_FACTOR,
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
    HOSTNAME_IP4_IP6_REGEX,
)
from .const import DOMAIN  # pylint: disable=unused-import
from .metercon import get_connection_factory, get_meter_message

_LOGGER = logging.getLogger(__name__)


# max number of frames to search for needed meter information
# Some meters sends 3 frames containing minimal of data between larger frames. Skip them.
# Some frames may be abortet correctly. Add some for that.
# A max count of 4 should be the normal situation, but a little more is more robust.
MAX_FRAME_SEARCH_COUNT = 6

# Kamstrup sends data frame every 10 sec. Aidon every 2.5 sec. Kaifa evry 2 sec.
MAX_FRAME_WAIT_TIME = 12

# Error codes
# Use the key base if you want to show an error unrelated to a specific field.
# The specified errors need to refer to a key in a translation file.
VALIDATION_ERROR_BASE = "base"
VALIDATION_ERROR_CONNECT = "cannot_connect"
VALIDATION_ERROR_TIMEOUT_CONNECT = "timeout_connect"
VALIDATION_ERROR_TIMEOUT_READ_MESSAGE = "timeout_read_messages"
VALIDATION_ERROR_HOST_CHECK = "host_check"
VALIDATION_ERROR_VOLUPTUOUS_BASE = "voluptuous_"
VALIDATION_ERROR_SERIAL_EXCEPTION_GENERAL = "serial_exception_general"
VALIDATION_ERROR_SERIAL_EXCEPTION_ERRNO_2 = "serial_exception_errno_2"
VALIDATION_ERROR_MQTT_NOT_AVAILAVLE = "mqtt_not_available"
VALIDATION_ERROR_MQTT_INVALID_SUBSCRIBE_TOPIC = "invalid_subscribe_topic"


class AmsHanConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for amshan."""

    VERSION = 3
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_PUSH

    def __init__(self) -> None:
        """Initialize AmsHanConfigFlow class."""
        self._validator = ConfigFlowValidation()

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get options flow handler."""
        return AmsHanOptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            connection_type = self._validator.validate_connection_type_input(user_input)

            if connection_type == ConnectionType.NETWORK:
                return await self.async_step_network_connection()

            if connection_type == ConnectionType.SERIAL:
                return await self.async_step_serial_connection()

            if connection_type == ConnectionType.MQTT:
                if self._is_mqtt_available():
                    return await self.async_step_hass_mqtt_connection()
                errors[VALIDATION_ERROR_BASE] = VALIDATION_ERROR_MQTT_NOT_AVAILAVLE

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required("type"): vol.In(["serial", "network", "MQTT"])}
            ),
            errors=errors,
        )

    async def async_step_serial_connection(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the serial_connection step."""
        if user_input:
            entry_result = await self._async_try_create_entry(
                ConnectionType.SERIAL, user_input
            )
            if entry_result:
                return entry_result
        else:
            # set defaults
            port = await self.hass.async_add_executor_job(
                self._try_get_first_available_serial
            )

            user_input = {
                CONF_SERIAL_PORT: port if port else "",
                CONF_SERIAL_BAUDRATE: 2400,
                CONF_SERIAL_PARITY: "N",
                CONF_SERIAL_BYTESIZE: "8",
                CONF_SERIAL_STOPBITS: "1",
                CONF_SERIAL_XONXOFF: False,
                CONF_SERIAL_RTSCTS: False,
                CONF_SERIAL_DSRDTR: False,
            }

        return self.async_show_form(
            step_id="serial_connection",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SERIAL_PORT, default=user_input[CONF_SERIAL_PORT]
                    ): cv.string,
                    vol.Optional(
                        CONF_SERIAL_BAUDRATE, default=user_input[CONF_SERIAL_BAUDRATE]
                    ): cv.positive_int,
                    vol.Optional(
                        CONF_SERIAL_PARITY, default=user_input[CONF_SERIAL_PARITY]
                    ): vol.In(["N", "E", "O"]),
                    vol.Optional(
                        CONF_SERIAL_BYTESIZE, default=user_input[CONF_SERIAL_BYTESIZE]
                    ): vol.In(
                        ["5", "6", "7", "8"]
                    ),  # use string as workaround gui bug
                    vol.Optional(
                        CONF_SERIAL_STOPBITS, default=user_input[CONF_SERIAL_STOPBITS]
                    ): vol.In(
                        ["1", "1.5", "2"]
                    ),  # use string as workaround gui bug
                    vol.Optional(
                        CONF_SERIAL_XONXOFF, default=user_input[CONF_SERIAL_XONXOFF]
                    ): cv.boolean,
                    vol.Optional(
                        CONF_SERIAL_RTSCTS, default=user_input[CONF_SERIAL_RTSCTS]
                    ): cv.boolean,
                    vol.Optional(
                        CONF_SERIAL_DSRDTR, default=user_input[CONF_SERIAL_DSRDTR]
                    ): cv.boolean,
                }
            ),
            errors=self._validator.errors,
        )

    async def async_step_network_connection(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the network_connection step."""
        if user_input:
            entry_result = await self._async_try_create_entry(
                ConnectionType.NETWORK, user_input
            )
            if entry_result:
                return entry_result
        else:
            # set defaults
            user_input = {
                CONF_TCP_HOST: "",
                CONF_TCP_PORT: None,
            }

        return self.async_show_form(
            step_id="network_connection",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_TCP_HOST, default=user_input[CONF_TCP_HOST]
                    ): cv.string,
                    vol.Required(
                        CONF_TCP_PORT, default=user_input[CONF_TCP_PORT]
                    ): cv.positive_int,
                }
            ),
            errors=self._validator.errors,
        )

    async def async_step_hass_mqtt_connection(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle hass_mqtt_connection step."""
        if user_input:
            entry_result = await self._async_try_create_entry(
                ConnectionType.MQTT, user_input
            )
            if entry_result:
                return entry_result
        else:
            # set defaults
            user_input = {
                CONF_MQTT_TOPICS: "",
            }

        return self.async_show_form(
            step_id="hass_mqtt_connection",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_MQTT_TOPICS, default=user_input[CONF_MQTT_TOPICS]
                    ): cv.string,
                }
            ),
            errors=self._validator.errors,
        )

    async def _async_try_create_entry(
        self, connection_type: ConnectionType, user_input: dict[str, Any]
    ) -> FlowResult | None:
        config = dict(user_input)  # create a copy to be able to make changes
        if connection_type == ConnectionType.SERIAL:
            config[CONF_SERIAL_BYTESIZE] = int(config[CONF_SERIAL_BYTESIZE])
            config[CONF_SERIAL_STOPBITS] = float(config[CONF_SERIAL_STOPBITS])
        elif connection_type == ConnectionType.NETWORK:
            config[CONF_TCP_PORT] = int(config[CONF_TCP_PORT])
        elif connection_type == ConnectionType.MQTT:
            # strip empty elements
            topics = [
                x.strip() for x in config[CONF_MQTT_TOPICS].split(",") if x.strip()
            ]
            config[CONF_MQTT_TOPICS] = ",".join(topics)

        meter_info = await self._validator.async_validate_connection_input(
            self.hass,
            connection_type,
            config,
        )

        if not self._validator.errors and meter_info:
            if meter_info.unique_id:
                await self.async_set_unique_id(meter_info.unique_id)
                self._abort_if_unique_id_configured()

            manufacturer = (
                meter_info.manufacturer
                if meter_info.manufacturer
                else meter_info.manufacturer_id
            )
            meter_type = (
                meter_info.type
                if meter_info.type
                else meter_info.type_id
                if meter_info.type_id
                else ""
            )

            return self.async_create_entry(
                title=f"{manufacturer} {meter_type} ({connection_type.name.lower()})",
                data={
                    CONF_CONNECTION_TYPE: connection_type.value,
                    CONF_CONNECTION_CONFIG: config,
                },
            )

        return None

    def _is_mqtt_available(self) -> bool:
        return mqtt.DOMAIN in self.hass.config.components

    @staticmethod
    def _try_get_first_available_serial() -> str | None:
        by_id = "/dev/serial/by-id"
        if not os.path.isdir(by_id):
            return None

        for device in (entry.path for entry in os.scandir(by_id) if entry.is_symlink()):
            try:
                # Open to test if port is available...
                port = serial.Serial(device)
            except serial.SerialException:
                # It has some error, skip this one
                continue
            else:
                port.close()
                return device

        return None


class ConfigFlowValidation:
    """ConfigFlow input validation."""

    def __init__(self) -> None:
        """Initialize ConfigFlowValidation class."""
        self.errors: dict[str, Any] = {}

    def _set_base_error(self, error_key: str) -> None:
        """
        Show an error unrelated to a specific field.

        :param error_key: error key that needs to refer to a key in a translation file.
        """
        self.errors[VALIDATION_ERROR_BASE] = error_key

    async def _async_get_meter_info(
        self, measure_queue: asyncio.Queue[han_type.MeterMessageBase]
    ) -> MeterInfo:
        """Decode meter data stream and return meter information if available."""
        decoder = autodecoder.AutoDecoder()

        for _ in range(MAX_FRAME_SEARCH_COUNT):
            measure = await self._async_try_get_message(measure_queue)
            if measure is not None:
                decoded_measure = decoder.decode_message(measure)
                if decoded_measure:
                    if (
                        obis_map.FIELD_METER_MANUFACTURER_ID in decoded_measure
                        or obis_map.FIELD_METER_MANUFACTURER in decoded_measure
                    ):
                        return MeterInfo.from_measure_data(decoded_measure)

                    _LOGGER.debug("Decoded measure data is missing required info.")

        raise TimeoutError()

    async def _async_try_get_message(
        self, measure_queue: asyncio.Queue[han_type.MeterMessageBase]
    ) -> han_type.MeterMessageBase | None:
        async with async_timeout.timeout(MAX_FRAME_WAIT_TIME):
            try:
                return await measure_queue.get()
            except (TimeoutError, asyncio.CancelledError):
                _LOGGER.debug(
                    "Timout waiting %d seconds for meter measure.", MAX_FRAME_WAIT_TIME
                )
                return None

    async def _async_validate_device_connection(
        self, loop: asyncio.AbstractEventLoop, user_input: dict[str, Any]
    ) -> MeterInfo | None:
        """Try to connect and get meter information to validate connection data."""
        measure_queue: asyncio.Queue[han_type.MeterMessageBase] = asyncio.Queue()
        connection_factory = get_connection_factory(loop, user_input, measure_queue)

        transport = None
        try:
            try:
                transport, _ = await connection_factory()
            except TimeoutError as ex:
                _LOGGER.debug("Timeout when connecting to HAN-port: %s", ex)
                self._set_base_error(VALIDATION_ERROR_TIMEOUT_CONNECT)
                return None
            except serial.SerialException as ex:
                if ex.errno == 2:
                    # No such file or directory
                    self._set_base_error(VALIDATION_ERROR_SERIAL_EXCEPTION_ERRNO_2)
                    _LOGGER.debug(
                        "Serial exception when connecting to HAN-port: %s", ex
                    )
                else:
                    self._set_base_error(VALIDATION_ERROR_SERIAL_EXCEPTION_GENERAL)
                    _LOGGER.error(
                        "Serial exception when connecting to HAN-port: %s", ex
                    )
                return None
            except ConnectionError as ex:
                self._set_base_error(VALIDATION_ERROR_CONNECT)
                _LOGGER.error(
                    "Network exception (%s) when connecting to HAN-port: %s",
                    type(ex).__name__,
                    ex,
                )

            except Exception as ex:
                _LOGGER.exception("Unexpected error connecting to HAN-port: %s", ex)
                raise

            try:
                return await self._async_get_meter_info(measure_queue)
            except TimeoutError:
                self._set_base_error(VALIDATION_ERROR_TIMEOUT_READ_MESSAGE)
                return None
        finally:
            if transport:
                transport.close()

    async def _async_validate_mqtt_connection(
        self, hass: HomeAssistant, user_input: dict[str, Any]
    ) -> MeterInfo | None:
        measure_queue: asyncio.Queue[han_type.MeterMessageBase] = asyncio.Queue()

        @callback
        def message_received(mqtt_message: mqtt.models.ReceiveMessage) -> None:
            """Handle new MQTT messages."""
            meter_message = get_meter_message(mqtt_message)
            if meter_message:
                measure_queue.put_nowait(meter_message)

        unsubscibers = []
        topics = {x.strip() for x in user_input[CONF_MQTT_TOPICS].split(",")}
        for topic in topics:
            unsubscibers.append(
                await mqtt.async_subscribe(
                    hass, topic, message_received, 1, encoding=None
                )
            )

        try:
            return await self._async_get_meter_info(measure_queue)
        except TimeoutError:
            self._set_base_error(VALIDATION_ERROR_TIMEOUT_READ_MESSAGE)
            return None
        finally:
            for ubsubscribe in unsubscibers:
                ubsubscribe()

            # workaround MQTT bug when topic is re-subscribed at setup at the same
            # time as unsubscribe runs as a background job
            await asyncio.sleep(1)

    async def _async_validate_host_address(
        self, loop: asyncio.AbstractEventLoop, user_input: dict[str, Any]
    ) -> None:
        try:
            await loop.getaddrinfo(
                user_input[CONF_TCP_HOST],
                None,
                family=0,
                type=socket.SOCK_STREAM,
                proto=0,
                flags=0,
            )
        except OSError as ex:
            _LOGGER.debug(
                "Could not resolve host '%s': %s", user_input[CONF_TCP_HOST], ex
            )
            self.errors[CONF_TCP_HOST] = VALIDATION_ERROR_HOST_CHECK

    def _validate_topics(self, user_input: dict[str, Any]) -> None:
        topics = {x.strip() for x in user_input[CONF_MQTT_TOPICS].split(",")}
        if not topics:
            self.errors[
                CONF_MQTT_TOPICS
            ] = VALIDATION_ERROR_MQTT_INVALID_SUBSCRIBE_TOPIC

        for topic in topics:
            try:
                mqtt.valid_subscribe_topic(topic)
            except vol.Invalid:
                self.errors[
                    CONF_MQTT_TOPICS
                ] = VALIDATION_ERROR_MQTT_INVALID_SUBSCRIBE_TOPIC

    def _validate_schema(
        self, connection_type: ConnectionType, user_input: dict[str, Any]
    ) -> None:
        if connection_type == ConnectionType.SERIAL:
            schema = vol.Schema(
                {
                    vol.Required(CONF_SERIAL_PORT): cv.string,
                    vol.Optional(CONF_SERIAL_BAUDRATE): cv.positive_int,
                },
                extra=vol.ALLOW_EXTRA,
            )
        elif connection_type == ConnectionType.NETWORK:
            schema = vol.Schema(
                {
                    vol.Required(CONF_TCP_HOST): cv.matches_regex(
                        HOSTNAME_IP4_IP6_REGEX
                    ),
                    vol.Required(CONF_TCP_PORT): cv.port,
                }
            )
        elif connection_type == ConnectionType.MQTT:
            schema = vol.Schema(
                {
                    vol.Required(CONF_MQTT_TOPICS): cv.string,
                }
            )
        else:
            raise ValueError(f"Unexpected connection type {connection_type}")

        try:
            schema(user_input)
        except vol.MultipleInvalid as ex:
            for err in ex.errors:
                for element in err.path:
                    self.errors[element] = VALIDATION_ERROR_VOLUPTUOUS_BASE + element

    def validate_connection_type_input(
        self, user_input: dict[str, Any]
    ) -> ConnectionType:
        """Validate user input from first step."""
        self.errors = {}
        return ConnectionType[user_input["type"].upper()]

    async def async_validate_connection_input(
        self,
        hass: HomeAssistant,
        connection_type: ConnectionType,
        user_input: dict[str, Any],
    ) -> MeterInfo | None:
        """Validate user input from connection step and try connection."""
        self.errors = {}

        self._validate_schema(connection_type, user_input)

        if not self.errors and connection_type == ConnectionType.NETWORK:
            await self._async_validate_host_address(hass.loop, user_input)
        elif not self.errors and connection_type == ConnectionType.MQTT:
            self._validate_topics(user_input)

        if not self.errors and connection_type in (
            ConnectionType.NETWORK,
            ConnectionType.SERIAL,
        ):
            return await self._async_validate_device_connection(hass.loop, user_input)

        if not self.errors and connection_type == ConnectionType.MQTT:
            return await self._async_validate_mqtt_connection(hass, user_input)

        return None


class AmsHanOptionsFlowHandler(config_entries.OptionsFlow):
    """Config flow options handler."""

    def __init__(self, config_entry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry
        self.options = dict(config_entry.options)

    async def async_step_init(self, user_input=None):  # pylint: disable=unused-argument
        """Manage the options."""
        return await self.async_step_user()

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        if user_input is not None:
            self.options.update(user_input)
            return self.async_create_entry(title="", data=self.options)

        options = {
            vol.Optional(
                CONF_OPTIONS_SCALE_FACTOR,
                default=self.options.get(CONF_OPTIONS_SCALE_FACTOR, 1.0),
            ): cv.positive_float,
        }

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(options),
        )
