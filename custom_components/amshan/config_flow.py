"""Config flow for AMS HAN meter integration."""
from asyncio import AbstractEventLoop, Queue, wait_for
from enum import Enum
import logging
import socket
from typing import Any, Dict, Optional, cast
from serial import SerialException

from amshan import obis_map
from amshan.autodecoder import AutoDecoder
from homeassistant import config_entries
from homeassistant.helpers.typing import HomeAssistantType
import voluptuous as vol

from . import (
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
    SERIAL_SCHEMA,
    TCP_SCHEMA,
    MeterInfo,
    get_connection_factory,
)
from .const import DOMAIN  # pylint:disable=unused-import

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA_SELECT_DEVICE_TYPE = vol.Schema(
    {vol.Required("type"): vol.In(["serial", "network"])}
)

DATA_SCHEMA_NETWORK_DATA = vol.Schema(
    {vol.Required(CONF_TCP_HOST): str, vol.Required(CONF_TCP_PORT): int}
)

DATA_SCHEMA_SERIAL_DATA = vol.Schema(
    {
        vol.Required(CONF_SERIAL_PORT): str,
        vol.Optional(CONF_SERIAL_BAUDRATE, default=2400): int,
        vol.Optional(CONF_SERIAL_PARITY, default="N"): vol.In(["N", "E", "O"]),
        vol.Optional(CONF_SERIAL_BYTESIZE, default=8): vol.In([5, 6, 7, 8]),
        vol.Optional(CONF_SERIAL_STOPBITS, default="1"): vol.In([1, 1.5, 2]),
        vol.Optional(CONF_SERIAL_XONXOFF, default=False): bool,
        vol.Optional(CONF_SERIAL_RTSCTS, default=False): bool,
        vol.Optional(CONF_SERIAL_DSRDTR, default=False): bool,
    }
)

# max number of frames to search for needed meter information
# Some meters sends 3 frames with minimal data in between larger. Skip them.
# Some frames may be abortet correctly. Add some for that.
# A max count of 4 should be the normal situation, but a little more is more robust.
MAX_FRAME_SEARCH_COUNT = 6

# Kamstrup sends data frame every 10 sec. Aidon every 2.5 sec. Kaifa evry 2 sec.
MAX_FRAME_WAIT_TIME = 12

# Error codes
# Use the key base if you want to show an error unrelated to a specific field.
# The specified errors need to refer to a key in a translation file.
VALIDATION_ERROR_BASE = "base"
VALIDATION_ERROR_TIMEOUT_CONNECT = "timeout_connect"
VALIDATION_ERROR_TIMEOUT_READ_FRAMES = "timeout_read_frames"
VALIDATION_ERROR_HOST_CHECK = "host_check"
VALIDATION_ERROR_VOLUPTUOUS_BASE = "voluptuous_"
VALIDATION_ERROR_SERIAL_EXCEPTION_GENERAL = "serial_exception_general"
VALIDATION_ERROR_SERIAL_EXCEPTION_ERRNO_2 = "serial_exception_errno_2"


class ConnectionType(Enum):
    """Meter connection type."""

    SERIAL = 1
    NETWORK = 2


class AmsHanConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for amshan."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_PUSH

    def __init__(self) -> None:
        """Initialize AmsHanConfigFlow class."""
        self._validator = ConfigFlowValidation()

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Handle the initial step."""
        if user_input is not None:
            connection_type = self._validator.validate_connection_type_input(user_input)

            if connection_type == ConnectionType.NETWORK:
                return await self.async_step_network_connection()

            if connection_type == ConnectionType.SERIAL:
                return await self.async_step_serial_connection()

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA_SELECT_DEVICE_TYPE, errors={}
        )

    async def async_step_serial_connection(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Handle the network connection step."""
        if user_input:
            meter_info = await self._validator.async_validate_connection_input(
                cast(HomeAssistantType, self.hass).loop,
                ConnectionType.SERIAL,
                user_input,
            )

            if not self._validator.errors and meter_info:
                await self.async_set_unique_id(meter_info.unique_id)
                self._abort_if_unique_id_configured()

                title = f"{meter_info.manufacturer} {meter_info.type} connectet to {user_input[CONF_SERIAL_PORT]}"
                return self.async_create_entry(title=title, data=user_input)

        return self.async_show_form(
            step_id="serial_connection",
            data_schema=DATA_SCHEMA_SERIAL_DATA,
            errors=self._validator.errors,
        )

    async def async_step_network_connection(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Handle the network connection step."""
        if user_input:
            meter_info = await self._validator.async_validate_connection_input(
                cast(HomeAssistantType, self.hass).loop,
                ConnectionType.NETWORK,
                user_input,
            )

            if not self._validator.errors and meter_info:
                await self.async_set_unique_id(meter_info.unique_id)
                self._abort_if_unique_id_configured()

                title = f"{meter_info.manufacturer} {meter_info.type} connectet to {user_input[CONF_TCP_HOST]} port {user_input[CONF_TCP_PORT]}"
                return self.async_create_entry(title=title, data=user_input)

        return self.async_show_form(
            step_id="network_connection",
            data_schema=DATA_SCHEMA_NETWORK_DATA,
            errors=self._validator.errors,
        )


class ConfigFlowValidation:
    """ConfigFlow input validation."""

    def __init__(self) -> None:
        """Initialize ConfigFlowValidation class."""
        self.errors: Dict[str, Any] = {}

    def _set_base_error(self, error_key: str) -> None:
        """
        Show an error unrelated to a specific field.

        :param error_key: error key that needs to refer to a key in a translation file.
        """
        self.errors[VALIDATION_ERROR_BASE] = error_key

    async def _async_get_meter_info(self, measure_queue: "Queue[bytes]") -> MeterInfo:
        """Decode meter data stream and return meter information if available."""
        decoder = AutoDecoder()

        for _ in range(MAX_FRAME_SEARCH_COUNT):
            measure = await wait_for(measure_queue.get(), MAX_FRAME_WAIT_TIME)
            decoded_measure = decoder.decode_frame_content(measure)
            if decoded_measure:
                if (
                    obis_map.NEK_HAN_FIELD_METER_ID in decoded_measure
                    and obis_map.NEK_HAN_FIELD_METER_MANUFACTURER
                ):
                    return MeterInfo.from_measure_data(decoded_measure)
        raise TimeoutError()

    async def _async_validate_connection(
        self, loop: AbstractEventLoop, user_input: Dict[str, Any]
    ) -> Optional[MeterInfo]:
        """Try to connect an get meter information to validate connection data."""
        measure_queue: "Queue[bytes]" = Queue()
        connection_factory = get_connection_factory(loop, user_input, measure_queue)

        transport = None
        try:
            try:
                transport, _ = await connection_factory()
            except TimeoutError as ex:
                _LOGGER.debug("Timeout when connecting to HAN-port: %s", ex)
                self._set_base_error(VALIDATION_ERROR_TIMEOUT_CONNECT)
                return None
            except SerialException as ex:
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

            except Exception as ex:
                _LOGGER.exception("Unexpected error connecting to HAN-port: %s", ex)
                raise

            try:
                return await self._async_get_meter_info(measure_queue)
            except TimeoutError:
                self._set_base_error(VALIDATION_ERROR_TIMEOUT_READ_FRAMES)
                return None
        finally:
            if transport:
                transport.close()

    async def _async_validate_host_address(
        self, loop: AbstractEventLoop, user_input: Dict[str, Any]
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
        except OSError:
            self.errors[CONF_SERIAL_PORT] = VALIDATION_ERROR_HOST_CHECK

    def _validate_schema(
        self, connection_type: ConnectionType, user_input: Dict[str, Any]
    ) -> None:
        schema = (
            SERIAL_SCHEMA if connection_type == ConnectionType.SERIAL else TCP_SCHEMA
        )
        try:
            schema(user_input)
        except vol.MultipleInvalid as ex:
            for err in ex.errors:
                for element in err.path:
                    self.errors[element] = VALIDATION_ERROR_VOLUPTUOUS_BASE + element

    def validate_connection_type_input(
        self, user_input: Dict[str, Any]
    ) -> ConnectionType:
        """Validate user input from first step."""
        self.errors = {}
        return ConnectionType[user_input["type"].upper()]

    async def async_validate_connection_input(
        self,
        loop: AbstractEventLoop,
        connection_type: ConnectionType,
        user_input: Dict[str, Any],
    ) -> Optional[MeterInfo]:
        """Validate user input from connection step and try connection."""
        self.errors = {}

        self._validate_schema(connection_type, user_input)

        if not self.errors and connection_type == ConnectionType.NETWORK:
            await self._async_validate_host_address(loop, user_input)

        if not self.errors:
            return await self._async_validate_connection(loop, user_input)

        return None
