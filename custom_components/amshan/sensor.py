"""amshan platform."""
from asyncio import Queue
from datetime import datetime
import logging
from typing import (
    Any,
    Callable,
    ClassVar,
    Dict,
    Iterable,
    List,
    NamedTuple,
    Optional,
    Set,
    Union,
    cast,
)

from amshan.autodecoder import AutoDecoder
import amshan.obis_map as obis_map
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import DEVICE_CLASS_POWER, ENERGY_KILO_WATT_HOUR, POWER_WATT
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import HomeAssistantType

from . import MeterInfo
from .const import (
    DOMAIN,
    ENTRY_DATA_MEASURE_QUEUE,
    ICON_COUNTER,
    ICON_CURRENT,
    ICON_POWER_EXPORT,
    ICON_POWER_IMPORT,
    ICON_VOLTAGE,
    UNIT_CURRENT_AMPERE,
    UNIT_KILO_VOLT_AMPERE_REACTIVE,
    UNIT_KILO_VOLT_AMPERE_REACTIVE_HOURS,
    UNIT_VOLTAGE,
)

_LOGGER: logging.Logger = logging.getLogger(__name__)


class EntitySetup(NamedTuple):
    """Entity setup."""

    """The unit of measurement of entity, if any."""
    unit: Optional[str]

    """Scaling, if any, to be done one the measured value to be in correct unit."""
    scale: Optional[float]

    """Specify a number to round the measure source value to that number of decimals."""
    decimals: Optional[int]

    """The icon to use in the frontend, if any."""
    icon: Optional[str]

    """The name of the entity."""
    name: str


async def async_setup_entry(
    hass: HomeAssistantType,
    config_entry: ConfigEntry,
    async_add_entities: Callable[[List[Entity], bool], None],
):
    """Add hantest sensor platform from a config_entry."""
    measure_queue = hass.data[DOMAIN][config_entry.entry_id][ENTRY_DATA_MEASURE_QUEUE]
    processor: MeterMeasureProcessor = MeterMeasureProcessor(
        hass, async_add_entities, measure_queue
    )
    hass.loop.create_task(processor.async_process_measures_loop())


class NorhanEntity(Entity):
    """Representation of a Norhan sensor."""

    ENTITY_SETUPS: ClassVar[Dict[str, EntitySetup]] = {
        obis_map.NEK_HAN_FIELD_METER_ID: EntitySetup(
            None, None, None, None, "Meter ID"
        ),
        obis_map.NEK_HAN_FIELD_METER_MANUFACTURER: EntitySetup(
            None, None, None, None, "Meter manufacturer"
        ),
        obis_map.NEK_HAN_FIELD_METER_TYPE: EntitySetup(
            None, None, None, None, "Meter type"
        ),
        obis_map.NEK_HAN_FIELD_OBIS_LIST_VER_ID: EntitySetup(
            None,
            None,
            None,
            None,
            "OBIS List version identifier",
        ),
        obis_map.NEK_HAN_FIELD_ACTIVE_POWER_IMPORT: EntitySetup(
            POWER_WATT,
            None,
            None,
            ICON_POWER_IMPORT,
            "Active power import (Q1+Q4)",
        ),
        obis_map.NEK_HAN_FIELD_ACTIVE_POWER_EXPORT: EntitySetup(
            POWER_WATT,
            None,
            None,
            ICON_POWER_EXPORT,
            "Active power export (Q2+Q3)",
        ),
        obis_map.NEK_HAN_FIELD_REACTIVE_POWER_IMPORT: EntitySetup(
            UNIT_KILO_VOLT_AMPERE_REACTIVE,
            0.001,
            None,
            ICON_POWER_IMPORT,
            "Reactive power import (Q1+Q2)",
        ),
        obis_map.NEK_HAN_FIELD_REACTIVE_POWER_EXPORT: EntitySetup(
            UNIT_KILO_VOLT_AMPERE_REACTIVE,
            0.001,
            None,
            ICON_POWER_EXPORT,
            "Reactive power export (Q3+Q4)",
        ),
        obis_map.NEK_HAN_FIELD_CURRENT_L1: EntitySetup(
            UNIT_CURRENT_AMPERE, None, 3, ICON_CURRENT, "IL1 Current phase L1"
        ),
        obis_map.NEK_HAN_FIELD_CURRENT_L2: EntitySetup(
            UNIT_CURRENT_AMPERE, None, 3, ICON_CURRENT, "IL2 Current phase L2"
        ),
        obis_map.NEK_HAN_FIELD_CURRENT_L3: EntitySetup(
            UNIT_CURRENT_AMPERE, None, 3, ICON_CURRENT, "IL3 Current phase L3"
        ),
        obis_map.NEK_HAN_FIELD_VOLTAGE_L1: EntitySetup(
            UNIT_VOLTAGE, None, 1, ICON_VOLTAGE, "UL1 Phase voltage"
        ),
        obis_map.NEK_HAN_FIELD_VOLTAGE_L2: EntitySetup(
            UNIT_VOLTAGE, None, 1, ICON_VOLTAGE, "UL2 Phase voltage"
        ),
        obis_map.NEK_HAN_FIELD_VOLTAGE_L3: EntitySetup(
            UNIT_VOLTAGE, None, 1, ICON_VOLTAGE, "UL3 Phase voltage"
        ),
        obis_map.NEK_HAN_FIELD_ACTIVE_POWER_IMPORT_HOUR: EntitySetup(
            ENERGY_KILO_WATT_HOUR,
            0.001,
            None,
            ICON_COUNTER,
            "Cumulative hourly active import energy (A+) (Q1+Q4)",
        ),
        obis_map.NEK_HAN_FIELD_ACTIVE_POWER_EXPORT_HOUR: EntitySetup(
            ENERGY_KILO_WATT_HOUR,
            0.001,
            None,
            ICON_COUNTER,
            "Cumulative hourly active export energy (A-) (Q2+Q3)",
        ),
        obis_map.NEK_HAN_FIELD_REACTIVE_POWER_IMPORT_HOUR: EntitySetup(
            UNIT_KILO_VOLT_AMPERE_REACTIVE_HOURS,
            0.001,
            None,
            ICON_COUNTER,
            "Cumulative hourly reactive import energy (R+) (Q1+Q2)",
        ),
        obis_map.NEK_HAN_FIELD_REACTIVE_POWER_EXPORT_HOUR: EntitySetup(
            UNIT_KILO_VOLT_AMPERE_REACTIVE_HOURS,
            0.001,
            None,
            ICON_COUNTER,
            "Cumulative hourly reactive import energy (R-) (Q3+Q4)",
        ),
    }

    def __init__(
        self,
        measure_id: str,
        measure_data: Dict[str, Union[str, int, float, datetime]],
        new_measure_signal_name: str,
    ) -> None:
        """Initialize NorhanEntity class."""
        if measure_id is None:
            raise TypeError("measure_id is required")
        if measure_data is None:
            raise TypeError("measure_data is required")
        if obis_map.NEK_HAN_FIELD_METER_ID not in measure_data:
            raise ValueError(
                f"Expected element {obis_map.NEK_HAN_FIELD_METER_ID} not in measure_data."
            )
        if new_measure_signal_name is None:
            raise TypeError("new_measure_signal_name is required")

        self._measure_id = measure_id
        self._measure_data = measure_data
        self._entity_setup = NorhanEntity.ENTITY_SETUPS[measure_id]
        self._new_measure_signal_name = new_measure_signal_name
        self._async_remove_dispatcher: Optional[Callable[[], None]] = None
        self._meter_info: MeterInfo = MeterInfo.from_measure_data(measure_data)

    @staticmethod
    def is_measure_id_supported(measure_id: str) -> bool:
        """Check if an entity can be created for measure id."""
        return measure_id in NorhanEntity.ENTITY_SETUPS

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""

        @callback
        def on_new_measure(
            measure_data: Dict[str, Union[str, int, float, datetime]]
        ) -> None:
            if self._measure_id in measure_data:
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
        return self._measure_id

    @property
    def should_poll(self) -> bool:
        """Return False since updates are pushed from this sensor."""
        return False

    @property
    def unique_id(self) -> Optional[str]:
        """Return the unique id."""
        return f"{self._meter_info.manufacturer}-{self._meter_info.meter_id}-{self._measure_id}"

    @property
    def name(self) -> Optional[str]:
        """Return the name of the entity."""
        return f"{self._meter_info.manufacturer} {self._entity_setup.name}"

    @property
    def state(self) -> Union[None, str, int, float]:
        """Return the state of the entity."""
        measure = self._measure_data[self._measure_id]

        if measure is None:
            return None

        if isinstance(measure, str):
            return measure

        if isinstance(measure, datetime):
            return measure.isoformat()

        if self._entity_setup.decimals:
            measure = round(measure, self._entity_setup.decimals)

        if self._entity_setup.scale:
            measure = measure * self._entity_setup.scale

        return measure

    @property
    def device_info(self) -> Optional[Dict[str, Any]]:
        """Return device specific attributes."""
        return {
            "identifiers": {(DOMAIN, self._meter_info.unique_id)},
            "name": "HAN port",
            "manufacturer": self._meter_info.manufacturer,
            "model": self._meter_info.type,
            "sw_version": self._meter_info.list_version_id,
        }

    @property
    def device_class(self) -> Optional[str]:
        """Return the class of this device, from component DEVICE_CLASSES."""
        return DEVICE_CLASS_POWER

    @property
    def unit_of_measurement(self) -> Optional[str]:
        """Return the unit of measurement of this entity, if any."""
        return self._entity_setup.unit

    @property
    def icon(self) -> Optional[str]:
        """Return the icon to use in the frontend, if any."""
        return self._entity_setup.icon


class MeterMeasureProcessor:
    """Process meter measures from queue and setup/update entities."""

    def __init__(
        self,
        hass: HomeAssistantType,
        async_add_entities: Callable[[List[Entity], bool], None],
        measure_queue: "Queue[bytes]",
    ) -> None:
        """Initialize MeterMeasureProcessor class."""
        self._hass = hass
        self._async_add_entities = async_add_entities
        self._measure_queue = measure_queue
        self._decoder: AutoDecoder = AutoDecoder()
        self._known_measures: Set[str] = set()
        self._new_measure_signal_name: Optional[str] = None

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
            except Exception as ex:
                _LOGGER.exception("Error processing meter readings: %s", ex)
                raise

    async def _async_decode_next_valid_frame(
        self,
    ) -> Dict[str, Union[str, int, float, datetime]]:
        while True:
            measure_frame_content = await self._measure_queue.get()
            if not measure_frame_content:
                # stop signal (empty bytes) reveived
                return dict()

            decoded_measure = self._decoder.decode_frame_content(measure_frame_content)
            if decoded_measure:
                _LOGGER.debug("Decoded measure frame: %s", decoded_measure)
                return decoded_measure

            _LOGGER.warning("Could not decode frame: %s", measure_frame_content.hex())

    def _update_entities(
        self, measure_data: Dict[str, Union[str, int, float, datetime]]
    ) -> None:
        self._ensure_entities_are_created(measure_data)

        # signal all entities to update with new measure data
        if self._known_measures:
            async_dispatcher_send(
                self._hass, self._new_measure_signal_name, measure_data
            )

    def _ensure_entities_are_created(
        self, measure_data: Dict[str, Union[str, int, float, datetime]]
    ) -> None:
        # meter_id is required to register entities (required for unique_id).
        meter_id = measure_data.get(obis_map.NEK_HAN_FIELD_METER_ID)
        if meter_id:
            missing_measures = measure_data.keys() - self._known_measures
            if missing_measures:
                new_enitities = self._create_entities(
                    missing_measures, str(meter_id), measure_data
                )
                if new_enitities:
                    self._add_entities(new_enitities)

    def _add_entities(self, entities: List[NorhanEntity]):
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
        measure_data: Dict[str, Union[str, int, float, datetime]],
    ) -> List[NorhanEntity]:
        new_enitities: List[NorhanEntity] = []
        for measure_id in new_measures:
            if NorhanEntity.is_measure_id_supported(measure_id):
                if not self._new_measure_signal_name:
                    self._new_measure_signal_name = (
                        f"{DOMAIN}_measure_available_meterid_{meter_id}"
                    )
                entity = NorhanEntity(
                    measure_id,
                    measure_data,
                    self._new_measure_signal_name,
                )
                new_enitities.append(entity)
            else:
                _LOGGER.debug("Ignore unhandled measure_id %s", measure_id)
        return new_enitities
