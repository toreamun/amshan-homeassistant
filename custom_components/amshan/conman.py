"""Connection manager module."""

from __future__ import annotations

from asyncio import AbstractEventLoop, BaseProtocol, Queue
from typing import Any, Mapping, cast

from amshan.meter_connection import (
    AsyncConnectionFactory,
    ConnectionManager,
    MeterTransportProtocol,
    SmartMeterFrameContentProtocol,
)
import serial_asyncio

from .config import (
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
)


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
