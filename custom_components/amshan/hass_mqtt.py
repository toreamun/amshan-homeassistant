"""Home Assistant MQTT module."""
from __future__ import annotations

from asyncio import Queue
import json
import logging
from typing import Any, Callable, Mapping

from han.common import MeterMessageBase
from han.hdlc import HdlcFrame, HdlcFrameReader
from homeassistant.components import mqtt
from homeassistant.components.mqtt.models import ReceiveMessage
from homeassistant.core import callback
from homeassistant.helpers.typing import HomeAssistantType

from .common import DlmsMessage
from .config import CONF_MQTT_TOPICS

_LOGGER: logging.Logger = logging.getLogger(__name__)


def try_read_meter_message(payload: bytes) -> HdlcFrame | None:
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


def get_meter_message(mqtt_message: ReceiveMessage) -> MeterMessageBase | None:
    """Get frame information part from mqtt message."""
    # Try first to read as HDLC-frame.
    message = try_read_meter_message(mqtt_message.payload)
    if message is not None:
        if message.is_good_ffc and message.is_expected_length:
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
            "Got invalid frame (ffc is %s and expected length is %s) from topic %s: %s",
            message.is_good_ffc,
            message.is_expected_length,
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

    return DlmsMessage(mqtt_message.payload)


async def async_setup_meter_mqtt_subscriptions(
    hass: HomeAssistantType,
    config: Mapping[str, Any],
    measure_queue: Queue[MeterMessageBase],
) -> Callable:
    """Set up MQTT topic subscriptions."""

    @callback
    def message_received(mqtt_message: ReceiveMessage) -> None:
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
