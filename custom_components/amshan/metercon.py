"""Meter connection module."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Mapping

from han import (
    common as han_type,
    dlde,
    hdlc,
    meter_connection,
    serial_connection_factory as han_serial,
    tcp_connection_factory as han_tcp,
)
from homeassistant.components import mqtt
from homeassistant.core import callback
from homeassistant.helpers.typing import HomeAssistantType

from .const import (
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
)

_LOGGER: logging.Logger = logging.getLogger(__name__)


def setup_meter_connection(
    loop: asyncio.AbstractEventLoop,
    config: Mapping[str, Any],
    measure_queue: asyncio.Queue[han_type.MeterMessageBase],
) -> meter_connection.ConnectionManager:
    """Initialize ConnectionManager using configured connection type."""
    connection_factory = get_connection_factory(loop, config, measure_queue)
    return meter_connection.ConnectionManager(connection_factory)


def get_connection_factory(
    loop: asyncio.AbstractEventLoop,
    config: Mapping[str, Any],
    measure_queue: asyncio.Queue[han_type.MeterMessageBase],
) -> meter_connection.AsyncConnectionFactory:
    """Get connection factory based on configured connection type."""

    async def tcp_connection_factory() -> meter_connection.MeterTransportProtocol:
        return await han_tcp.create_tcp_message_connection(
            measure_queue,
            loop,
            None,
            host=config[CONF_TCP_HOST],
            port=config[CONF_TCP_PORT],
        )

    async def serial_connection_factory() -> meter_connection.MeterTransportProtocol:
        return await han_serial.create_serial_message_connection(
            measure_queue,
            loop,
            None,
            url=config[CONF_SERIAL_PORT],
            baudrate=config[CONF_SERIAL_BAUDRATE],
            parity=config[CONF_SERIAL_PARITY],
            bytesize=config[CONF_SERIAL_BYTESIZE],
            stopbits=float(config[CONF_SERIAL_STOPBITS]),
            xonxoff=config[CONF_SERIAL_XONXOFF],
            rtscts=config[CONF_SERIAL_RTSCTS],
            dsrdtr=config[CONF_SERIAL_DSRDTR],
        )

    # select tcp or serial connection factory
    connection_factory = (
        tcp_connection_factory if CONF_TCP_HOST in config else serial_connection_factory
    )

    return connection_factory


async def async_setup_meter_mqtt_subscriptions(
    hass: HomeAssistantType,
    config: Mapping[str, Any],
    measure_queue: asyncio.Queue[han_type.MeterMessageBase],
) -> Callable:
    """Set up MQTT topic subscriptions."""

    @callback
    def message_received(mqtt_message: mqtt.models.ReceiveMessage) -> None:
        """Handle new MQTT messages."""
        meter_message = get_meter_message(mqtt_message)
        if meter_message:
            measure_queue.put_nowait(meter_message)

    unsubscibers: list[Callable] = []
    topics = {x.strip() for x in config[CONF_MQTT_TOPICS].split(",")}
    for topic in topics:
        unsubscibers.append(
            await mqtt.async_subscribe(hass, topic, message_received, 1, encoding=None)
        )

    @callback
    def unsubscribe_mqtt():
        _LOGGER.debug("Unsubscribe %d MQTT topic(s): %s", len(unsubscibers), topics)
        for unsubscribe in unsubscibers:
            unsubscribe()

    return unsubscribe_mqtt


def get_meter_message(
    mqtt_message: mqtt.models.ReceiveMessage,
) -> han_type.MeterMessageBase | None:
    """Get frame information part from mqtt message."""
    # Try first to read as HDLC-frame.
    message = _try_read_meter_message(mqtt_message.payload)
    if message is not None:
        if message.message_type == han_type.MeterMessageType.P1:
            if message.is_valid:
                _LOGGER.debug(
                    "Got valid P1 message from topic %s: %s",
                    mqtt_message.topic,
                    mqtt_message.payload.hex(),
                )
                return message

            _LOGGER.debug(
                "Got invalid P1 message from topic %s: %s",
                mqtt_message.topic,
                mqtt_message.payload.hex(),
            )

            return None

        if message.is_valid:
            if message.payload is not None:
                _LOGGER.debug(
                    "Got valid frame of expected length with correct checksum from topic %s: %s",
                    mqtt_message.topic,
                    mqtt_message.payload.hex(),
                )
                return message

            _LOGGER.debug(
                "Got empty frame of expected length with correct checksum from topic %s: %s",
                mqtt_message.topic,
                mqtt_message.payload.hex(),
            )

        _LOGGER.debug(
            "Got invalid frame from topic %s: %s",
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

    return han_type.DlmsMessage(mqtt_message.payload)


def _try_read_meter_message(payload: bytes) -> han_type.MeterMessageBase | None:
    """Try to parse HDLC-frame from payload."""
    if payload.startswith(b"/"):
        try:
            return dlde.DataReadout(payload)
        except ValueError as ex:
            _LOGGER.debug("Starts with '/', but not a valid P1 message: %s", ex)

    frame_reader = hdlc.HdlcFrameReader(False)

    # Reader expects flag sequence in start and end.
    flag_seqeuence = hdlc.HdlcFrameReader.FLAG_SEQUENCE.to_bytes(1, byteorder="big")
    if not payload.startswith(flag_seqeuence):
        frame_reader.read(flag_seqeuence)

    frames = frame_reader.read(payload)
    if len(frames) == 0:
        # add flag sequence to the end
        frames = frame_reader.read(flag_seqeuence)

    if len(frames) > 0:
        return frames[0]

    return None
