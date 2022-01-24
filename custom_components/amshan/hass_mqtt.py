"""Home Assistant MQTT module."""
from __future__ import annotations

from asyncio import Queue
import json
import logging
from typing import Any, Callable, List, Mapping

from amshan.hdlc import HdlcFrame, HdlcFrameReader
from homeassistant.components import mqtt
from homeassistant.components.mqtt.models import ReceiveMessage
from homeassistant.core import callback
from homeassistant.helpers.typing import HomeAssistantType

from .config import CONF_MQTT_TOPICS

_LOGGER: logging.Logger = logging.getLogger(__name__)


def try_read_hdlc_frame(payload: bytes) -> HdlcFrame | None:
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


def get_frame_information(mqtt_message: ReceiveMessage) -> bytes | None:
    """Get frame information part from mqtt message."""
    # Try first to read as HDLC-frame.
    frame = try_read_hdlc_frame(mqtt_message.payload)
    if frame is not None:
        if frame.is_good_ffc and frame.is_expected_length:
            if frame.information is not None:
                _LOGGER.debug(
                    "Got valid frame of expected length with correct checksum from topic %s: %s",
                    mqtt_message.topic,
                    mqtt_message.payload.hex(),
                )
                return frame.information
            else:
                _LOGGER.debug(
                    "Got empty frame of expected length with correct checksum from topic %s: %s",
                    mqtt_message.topic,
                    mqtt_message.payload.hex(),
                )

        _LOGGER.debug(
            "Got invalid frame (ffc is %s and expected length is %s) from topic %s: %s",
            frame.is_good_ffc,
            frame.is_expected_length,
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
    return mqtt_message.payload


async def async_setup_meter_mqtt_subscriptions(
    hass: HomeAssistantType, config: Mapping[str, Any], measure_queue: "Queue[bytes]"
) -> Callable:
    """Set up MQTT topic subscriptions."""

    @callback
    def message_received(mqtt_message: ReceiveMessage) -> None:
        """Handle new MQTT messages."""
        information = get_frame_information(mqtt_message)
        if information:
            measure_queue.put_nowait(information)

    unsubscibers: List[Callable] = []
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
