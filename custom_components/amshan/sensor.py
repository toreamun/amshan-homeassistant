"""amshan platform."""
from __future__ import annotations

from asyncio import Queue
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from math import floor
from typing import Callable, Iterable, cast

from amshan.autodecoder import AutoDecoder
import amshan.obis_map as obis_map
from homeassistant import util
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ELECTRIC_CURRENT_AMPERE,
    ELECTRIC_POTENTIAL_VOLT,
    ENERGY_KILO_WATT_HOUR,
    POWER_WATT,
    STATE_UNKNOWN,
)
from homeassistant.core import State, callback
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.entity import DeviceInfo, Entity, EntityCategory
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import HomeAssistantType
from homeassistant.util import dt as dt_util

from . import MeterInfo
from .const import (
    CONF_OPTIONS_SCALE_FACTOR,
    DOMAIN,
    ENTRY_DATA_MEASURE_QUEUE,
    ICON_COUNTER,
    ICON_CURRENT,
    ICON_POWER_EXPORT,
    ICON_POWER_IMPORT,
    ICON_VOLTAGE,
    UNIT_KILO_VOLT_AMPERE_REACTIVE,
    UNIT_KILO_VOLT_AMPERE_REACTIVE_HOURS,
)

_LOGGER: logging.Logger = logging.getLogger(__name__)


@dataclass
class AmsHanSensorEntityDescription(SensorEntityDescription):
    """A class that describes sensor entities."""

    scale: float | None = None
    """Scaling, if any, to be done one the measured value to be in correct unit."""

    decimals: int | None = None
    """Specify a number to round the measure source value to that number of decimals."""

    use_configured_scaling: bool = False
    """Use custom configured scaling."""

    is_hour_sensor: bool = False
    """Is the sensor updated only each hour."""


SENSOR_TYPES: dict[str, AmsHanSensorEntityDescription] = {
    sensor.key: sensor
    for sensor in [
        AmsHanSensorEntityDescription(
            key=obis_map.NEK_HAN_FIELD_METER_ID,
            entity_category=EntityCategory.DIAGNOSTIC,
            name="Meter ID",
            use_configured_scaling=False,
        ),
        AmsHanSensorEntityDescription(
            key=obis_map.NEK_HAN_FIELD_METER_MANUFACTURER,
            entity_category=EntityCategory.DIAGNOSTIC,
            name="Meter manufacturer",
            use_configured_scaling=False,
        ),
        AmsHanSensorEntityDescription(
            key=obis_map.NEK_HAN_FIELD_METER_TYPE,
            entity_category=EntityCategory.DIAGNOSTIC,
            name="Meter type",
            use_configured_scaling=False,
        ),
        AmsHanSensorEntityDescription(
            key=obis_map.NEK_HAN_FIELD_OBIS_LIST_VER_ID,
            entity_category=EntityCategory.DIAGNOSTIC,
            name="OBIS List version identifier",
            use_configured_scaling=False,
        ),
        AmsHanSensorEntityDescription(
            key=obis_map.NEK_HAN_FIELD_ACTIVE_POWER_IMPORT,
            device_class=SensorDeviceClass.POWER,
            native_unit_of_measurement=POWER_WATT,
            state_class=SensorStateClass.MEASUREMENT,
            icon=ICON_POWER_IMPORT,
            name="Active power import (Q1+Q4)",
            decimals=0,
            use_configured_scaling=True,
        ),
        AmsHanSensorEntityDescription(
            key=obis_map.NEK_HAN_FIELD_ACTIVE_POWER_EXPORT,
            device_class=SensorDeviceClass.POWER,
            native_unit_of_measurement=POWER_WATT,
            state_class=SensorStateClass.MEASUREMENT,
            icon=ICON_POWER_EXPORT,
            name="Active power export (Q2+Q3)",
            decimals=0,
            use_configured_scaling=True,
        ),
        AmsHanSensorEntityDescription(
            key=obis_map.NEK_HAN_FIELD_REACTIVE_POWER_IMPORT,
            native_unit_of_measurement=UNIT_KILO_VOLT_AMPERE_REACTIVE,
            state_class=SensorStateClass.MEASUREMENT,
            icon=ICON_POWER_IMPORT,
            name="Reactive power import (Q1+Q2)",
            scale=0.001,
            decimals=3,
            use_configured_scaling=True,
        ),
        AmsHanSensorEntityDescription(
            key=obis_map.NEK_HAN_FIELD_REACTIVE_POWER_EXPORT,
            native_unit_of_measurement=UNIT_KILO_VOLT_AMPERE_REACTIVE,
            state_class=SensorStateClass.MEASUREMENT,
            icon=ICON_POWER_EXPORT,
            name="Reactive power export (Q3+Q4)",
            scale=0.001,
            decimals=3,
            use_configured_scaling=True,
        ),
        AmsHanSensorEntityDescription(
            key=obis_map.NEK_HAN_FIELD_CURRENT_L1,
            device_class=SensorDeviceClass.CURRENT,
            native_unit_of_measurement=ELECTRIC_CURRENT_AMPERE,
            state_class=SensorStateClass.MEASUREMENT,
            icon=ICON_CURRENT,
            name="IL1 Current phase L1",
            decimals=3,
            use_configured_scaling=True,
        ),
        AmsHanSensorEntityDescription(
            key=obis_map.NEK_HAN_FIELD_CURRENT_L2,
            device_class=SensorDeviceClass.CURRENT,
            native_unit_of_measurement=ELECTRIC_CURRENT_AMPERE,
            state_class=SensorStateClass.MEASUREMENT,
            name="IL2 Current phase L2",
            decimals=3,
            use_configured_scaling=True,
        ),
        AmsHanSensorEntityDescription(
            key=obis_map.NEK_HAN_FIELD_CURRENT_L3,
            device_class=SensorDeviceClass.CURRENT,
            native_unit_of_measurement=ELECTRIC_CURRENT_AMPERE,
            state_class=SensorStateClass.MEASUREMENT,
            name="IL3 Current phase L3",
            decimals=3,
            use_configured_scaling=True,
        ),
        AmsHanSensorEntityDescription(
            key=obis_map.NEK_HAN_FIELD_VOLTAGE_L1,
            device_class=SensorDeviceClass.VOLTAGE,
            native_unit_of_measurement=ELECTRIC_POTENTIAL_VOLT,
            state_class=SensorStateClass.MEASUREMENT,
            icon=ICON_VOLTAGE,
            name="UL1 Phase voltage",
            decimals=1,
            use_configured_scaling=False,
        ),
        AmsHanSensorEntityDescription(
            key=obis_map.NEK_HAN_FIELD_VOLTAGE_L2,
            device_class=SensorDeviceClass.VOLTAGE,
            native_unit_of_measurement=ELECTRIC_POTENTIAL_VOLT,
            state_class=SensorStateClass.MEASUREMENT,
            icon=ICON_VOLTAGE,
            name="UL2 Phase voltage",
            decimals=1,
            use_configured_scaling=False,
        ),
        AmsHanSensorEntityDescription(
            key=obis_map.NEK_HAN_FIELD_VOLTAGE_L3,
            device_class=SensorDeviceClass.VOLTAGE,
            native_unit_of_measurement=ELECTRIC_POTENTIAL_VOLT,
            state_class=SensorStateClass.MEASUREMENT,
            icon=ICON_VOLTAGE,
            name="UL3 Phase voltage",
            decimals=1,
            use_configured_scaling=False,
        ),
        AmsHanSensorEntityDescription(
            key=obis_map.NEK_HAN_FIELD_ACTIVE_POWER_IMPORT_HOUR,
            device_class=SensorDeviceClass.ENERGY,
            native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
            state_class=SensorStateClass.TOTAL_INCREASING,
            icon=ICON_COUNTER,
            name="Cumulative hourly active import energy (A+) (Q1+Q4)",
            scale=0.001,
            decimals=2,
            use_configured_scaling=True,
            is_hour_sensor=True,
        ),
        AmsHanSensorEntityDescription(
            key=obis_map.NEK_HAN_FIELD_ACTIVE_POWER_EXPORT_HOUR,
            device_class=SensorDeviceClass.ENERGY,
            native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
            state_class=SensorStateClass.TOTAL_INCREASING,
            icon=ICON_COUNTER,
            name="Cumulative hourly active export energy (A-) (Q2+Q3)",
            scale=0.001,
            decimals=2,
            use_configured_scaling=True,
            is_hour_sensor=True,
        ),
        AmsHanSensorEntityDescription(
            key=obis_map.NEK_HAN_FIELD_REACTIVE_POWER_IMPORT_HOUR,
            native_unit_of_measurement=UNIT_KILO_VOLT_AMPERE_REACTIVE_HOURS,
            state_class=SensorStateClass.TOTAL_INCREASING,
            icon=ICON_COUNTER,
            name="Cumulative hourly reactive import energy (R+) (Q1+Q2)",
            scale=0.001,
            decimals=2,
            use_configured_scaling=True,
            is_hour_sensor=True,
        ),
        AmsHanSensorEntityDescription(
            key=obis_map.NEK_HAN_FIELD_REACTIVE_POWER_EXPORT_HOUR,
            native_unit_of_measurement=UNIT_KILO_VOLT_AMPERE_REACTIVE_HOURS,
            state_class=SensorStateClass.TOTAL_INCREASING,
            icon=ICON_COUNTER,
            name="Cumulative hourly reactive export energy (R-) (Q3+Q4)",
            scale=0.001,
            decimals=2,
            use_configured_scaling=True,
            is_hour_sensor=True,
        ),
    ]
}


async def async_setup_entry(
    hass: HomeAssistantType,
    config_entry: ConfigEntry,
    async_add_entities: Callable[[list[Entity], bool], None],
):
    """Add hantest sensor platform from a config_entry."""
    measure_queue = hass.data[DOMAIN][config_entry.entry_id][ENTRY_DATA_MEASURE_QUEUE]
    processor: MeterMeasureProcessor = MeterMeasureProcessor(
        hass, config_entry, async_add_entities, measure_queue
    )
    hass.loop.create_task(processor.async_process_measures_loop())


class AmsHanEntity(SensorEntity):
    """Representation of a AmsHan sensor."""

    def __init__(
        self,
        entity_description: AmsHanSensorEntityDescription,
        measure_data: dict[str, str | int | float | datetime],
        new_measure_signal_name: str,
        scale_factor: float,
        meter_info: MeterInfo,
    ) -> None:
        """Initialize AmsHanEntity class."""
        if entity_description is None:
            raise TypeError("measure_id is required")
        if measure_data is None:
            raise TypeError("measure_data is required")
        if obis_map.NEK_HAN_FIELD_METER_ID not in measure_data:
            raise ValueError(
                f"Expected element {obis_map.NEK_HAN_FIELD_METER_ID} not in measure_data."
            )
        if new_measure_signal_name is None:
            raise TypeError("new_measure_signal_name is required")

        self.entity_description: AmsHanSensorEntityDescription = entity_description
        self._measure_data = measure_data
        self._new_measure_signal_name = new_measure_signal_name
        self._async_remove_dispatcher: Callable[[], None] | None = None
        self._meter_info: MeterInfo = (
            meter_info if meter_info else MeterInfo.from_measure_data(measure_data)
        )
        self._scale_factor = (
            int(scale_factor) if scale_factor == floor(scale_factor) else scale_factor
        )
        self.entity_id = (
            "sensor."
            f"{self._meter_info.manufacturer}_{util.slugify(entity_description.name)}"
        ).lower()

    @staticmethod
    def is_measure_id_supported(measure_id: str) -> bool:
        """Check if an entity can be created for measure id."""
        return measure_id in SENSOR_TYPES

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""

        @callback
        def on_new_measure(
            measure_data: dict[str, str | int | float | datetime]
        ) -> None:
            if self.measure_id in measure_data:
                self._measure_data = measure_data
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    _LOGGER.debug(
                        "Update sensor %s with state %s",
                        self.unique_id,
                        self.state,
                    )
                self.async_write_ha_state()

        # subscribe to update events for this meter
        self._async_remove_dispatcher = async_dispatcher_connect(
            cast(HomeAssistantType, self.hass),
            self._new_measure_signal_name,
            on_new_measure,
        )

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        if self._async_remove_dispatcher:
            self._async_remove_dispatcher()

    @property
    def measure_id(self) -> str:
        """Return the measure_id handled by this entity."""
        return self.entity_description.key

    @property
    def should_poll(self) -> bool:
        """Return False since updates are pushed from this sensor."""
        return False

    @property
    def unique_id(self) -> str | None:
        """Return the unique id."""
        return f"{self._meter_info.manufacturer}-{self._meter_info.meter_id}-{self.measure_id}"

    @property
    def native_value(self) -> None | str | int | float:
        """Return the native value of the entity."""
        measure = self._measure_data.get(self.measure_id)

        if measure is None:
            return None

        if isinstance(measure, str):
            return measure

        if isinstance(measure, datetime):
            return measure.isoformat()

        if self.entity_description.scale is not None:
            measure = measure * self.entity_description.scale

        if self.entity_description.use_configured_scaling:
            measure = measure * self._scale_factor

        if self.entity_description.decimals is not None:
            measure = (
                round(measure)
                if self.entity_description.decimals == 0
                else round(measure, self.entity_description.decimals)
            )

        return measure

    @property
    def device_info(self) -> DeviceInfo:
        """Return device specific attributes."""
        return DeviceInfo(
            name="HAN port",
            identifiers={(DOMAIN, self._meter_info.unique_id)},
            manufacturer=self._meter_info.manufacturer,
            model=self._meter_info.type,
            sw_version=self._meter_info.list_version_id,
        )


class AmsHanHourlyEntity(AmsHanEntity, RestoreEntity):
    """Representation of a AmsHan sensor each hour."""

    def __init__(
        self,
        entity_description: AmsHanSensorEntityDescription,
        measure_data: dict[str, str | int | float | datetime],
        new_measure_signal_name: str,
        scale_factor: float,
        meter_info: MeterInfo,
    ) -> None:
        """Initialize AmsHanHourlyEntity class."""
        super().__init__(
            entity_description,
            measure_data,
            new_measure_signal_name,
            scale_factor,
            meter_info,
        )
        self._restored_last_state: State | None = None

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        self._restored_last_state = await self.async_get_last_state()
        if (
            self._restored_last_state
            and self._restored_last_state.state == STATE_UNKNOWN
        ):
            _LOGGER.debug(
                "Restored state from %s for sensor %s is unknown. No need to keep.",
                self._restored_last_state.last_updated,
                self.unique_id,
            )
            self._restored_last_state = None

        await super().async_added_to_hass()

    @property
    def native_value(self) -> None | str | int | float:
        """Return the native value from current measure or cache if from current hour."""
        measured_value = super().native_value
        if measured_value is not None:
            self._restored_last_state = None  # no need for restored state anymore
            return measured_value

        if self._restored_last_state:
            if self._is_restored_state_from_current_hour():
                _LOGGER.debug(
                    "Use restored state from %s for sensor %s",
                    self._restored_last_state.last_updated,
                    self.unique_id,
                )
                return self._restored_last_state.state

            _LOGGER.debug(
                "Restored state from %s for sensor %s is too old to be used",
                self._restored_last_state.last_updated,
                self.unique_id,
            )

            self._restored_last_state = None

        return None

    def _is_restored_state_from_current_hour(self):
        now = dt_util.utcnow()
        time_since_update = now - self._restored_last_state.last_updated
        return (
            now.hour == self._restored_last_state.last_updated.hour
            and time_since_update < timedelta(hours=1)
        )


class MeterMeasureProcessor:
    """Process meter measures from queue and setup/update entities."""

    def __init__(
        self,
        hass: HomeAssistantType,
        config_entry: ConfigEntry,
        async_add_entities: Callable[[list[Entity], bool], None],
        measure_queue: Queue[bytes],
    ) -> None:
        """Initialize MeterMeasureProcessor class."""
        self._hass = hass
        self._async_add_entities = async_add_entities
        self._measure_queue = measure_queue
        self._decoder: AutoDecoder = AutoDecoder()
        self._known_measures: set[str] = set()
        self._new_measure_signal_name: str | None = None
        self._scale_factor = float(
            config_entry.options.get(CONF_OPTIONS_SCALE_FACTOR, 1)
        )
        self._meter_info: MeterInfo | None = None

    async def async_process_measures_loop(self) -> None:
        """Start the processing loop. The method exits when None is received from queue."""
        while True:
            try:
                measure_data = await self._async_decode_next_valid_frame()
                if not measure_data:
                    _LOGGER.debug("Received stop signal. Exit processing.")
                    return

                _LOGGER.debug("Received meter measures: %s", measure_data)
                self._update_entities(measure_data)
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Error processing meter readings")

    async def _async_decode_next_valid_frame(
        self,
    ) -> dict[str, str | int | float | datetime]:
        while True:
            measure_frame_content = await self._measure_queue.get()
            if not measure_frame_content:
                # stop signal (empty bytes) reveived
                return dict()

            try:
                decoded_measure = self._decoder.decode_frame_content(
                    measure_frame_content
                )
                if decoded_measure:
                    _LOGGER.debug("Decoded meter frame: %s", decoded_measure)
                    return decoded_measure

                _LOGGER.warning(
                    "Could not decode meter frame: %s", measure_frame_content.hex()
                )
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception(
                    "Exception when decoding meter frame: %s",
                    measure_frame_content.hex(),
                )

    def _update_entities(
        self, measure_data: dict[str, str | int | float | datetime]
    ) -> None:
        self._ensure_entities_are_created(measure_data)

        # signal all entities to update with new measure data
        if self._known_measures:
            assert self._new_measure_signal_name is not None
            async_dispatcher_send(
                self._hass, self._new_measure_signal_name, measure_data
            )

    def _ensure_entities_are_created(
        self, measure_data: dict[str, str | int | float | datetime]
    ) -> None:
        # meter_id is required to register entities (required for unique_id).
        meter_id = measure_data.get(obis_map.NEK_HAN_FIELD_METER_ID)
        if meter_id:
            missing_measures = measure_data.keys() - self._known_measures

            if missing_measures:

                # Add hourly sensors before measurement is available to avoid long delay
                hour_sensors = {
                    s.key for s in SENSOR_TYPES.values() if s.is_hour_sensor
                }
                missing_hour_sensors = hour_sensors - self._known_measures
                if missing_hour_sensors:
                    missing_measures.update(missing_hour_sensors)

                new_enitities = self._create_entities(
                    missing_measures, str(meter_id), measure_data
                )
                if new_enitities:
                    self._add_entities(new_enitities)

    def _add_entities(self, entities: list[AmsHanEntity]):
        new_measures = [x.measure_id for x in entities]
        self._known_measures.update(new_measures)
        _LOGGER.debug(
            "Register new entities for measures: %s",
            new_measures,
        )
        self._async_add_entities(list(entities), True)

    def _create_entities(
        self,
        new_measures: Iterable[str],
        meter_id: str,
        measure_data: dict[str, str | int | float | datetime],
    ) -> list[AmsHanEntity]:
        new_enitities: list[AmsHanEntity] = []
        for measure_id in new_measures:
            if AmsHanEntity.is_measure_id_supported(measure_id):
                if not self._new_measure_signal_name:
                    self._new_measure_signal_name = (
                        f"{DOMAIN}_measure_available_meterid_{meter_id}"
                    )
                if not self._meter_info:
                    self._meter_info = MeterInfo.from_measure_data(measure_data)

                entity_description = SENSOR_TYPES[measure_id]
                entity = (
                    AmsHanHourlyEntity(
                        entity_description,
                        measure_data,
                        self._new_measure_signal_name,
                        self._scale_factor,
                        self._meter_info,
                    )
                    if entity_description.is_hour_sensor
                    else AmsHanEntity(
                        entity_description,
                        measure_data,
                        self._new_measure_signal_name,
                        self._scale_factor,
                        self._meter_info,
                    )
                )
                new_enitities.append(entity)
            else:
                _LOGGER.debug("Ignore unhandled measure_id %s", measure_id)
        return new_enitities
