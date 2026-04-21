"""Sensor platform for edata component."""

import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import CURRENCY_EURO, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant

from . import const
from .entity import EdataSensorEntity

# HA variables
_LOGGER = logging.getLogger(__name__)

INFO_SENSORS_DESC = [
    # (name, state_key, [attributes_key])
    (
        "info",
        "last_registered_date",
        [
            "contract_p1_kW",
            "contract_p2_kW",
            "import_all_data_calls",
            "import_all_data_last_run",
        ],
    ),
]

ENERGY_SENSORS_DESC = [
    (
        "yesterday_kwh",
        "yesterday_kWh",
        ["yesterday_hours", "yesterday_p1_kWh", "yesterday_p2_kWh", "yesterday_p3_kWh"],
    ),
    (
        "yesterday_surplus_kwh",
        "yesterday_surplus_kWh",
        [
            "yesterday_hours",
            "yesterday_surplus_p1_kWh",
            "yesterday_surplus_p2_kWh",
            "yesterday_surplus_p3_kWh",
        ],
    ),
    (
        "last_registered_day_kwh",
        "last_registered_day_kWh",
        [
            "last_registered_date",
            "last_registered_day_hours",
            "last_registered_day_p1_kWh",
            "last_registered_day_p2_kWh",
            "last_registered_day_p3_kWh",
        ],
    ),
    (
        "last_registered_day_surplus_kwh",
        "last_registered_day_surplus_kWh",
        [
            "last_registered_date",
            "last_registered_day_hours",
            "last_registered_day_surplus_p1_kWh",
            "last_registered_day_surplus_p2_kWh",
            "last_registered_day_surplus_p3_kWh",
        ],
    ),
    (
        "month_kwh",
        "month_kWh",
        [
            "month_days",
            "month_daily_kWh",
            "month_p1_kWh",
            "month_p2_kWh",
            "month_p3_kWh",
        ],
    ),
    (
        "month_surplus_kwh",
        "month_surplus_kWh",
        [
            "month_days",
            "month_surplus_p1_kWh",
            "month_surplus_p2_kWh",
            "month_surplus_p3_kWh",
        ],
    ),
    (
        "last_month_kwh",
        "last_month_kWh",
        [
            "last_month_days",
            "last_month_daily_kWh",
            "last_month_p1_kWh",
            "last_month_p2_kWh",
            "last_month_p3_kWh",
        ],
    ),
    (
        "last_month_surplus_kwh",
        "last_month_surplus_kWh",
        [
            "last_month_days",
            "last_month_surplus_p1_kWh",
            "last_month_surplus_p2_kWh",
            "last_month_surplus_p3_kWh",
        ],
    ),
]

POWER_SENSORS_DESC = [
    (
        "max_power_kw",
        "max_power_kW",
        [
            "max_power_date",
            "max_power_mean_kW",
            "max_power_90perc_kW",
        ],
    ),
]

COST_SENSORS_DESC = [
    (
        "month_eur",
        "month_€",
        [],
    ),
    (
        "last_month_eur",
        "last_month_€",
        [],
    ),
    (
        "month_surplus_eur",
        "month_surplus_€",
        [],
    ),
    (
        "last_month_surplus_eur",
        "last_month_surplus_€",
        [],
    ),
]


async def async_setup_entry(hass: HomeAssistant, config_entry, async_add_entities):
    """Set up entry."""
    hass.data.setdefault(const.DOMAIN, {})

    # get configured parameters
    scups = config_entry.data[const.CONF_SCUPS]
    coordinator = hass.data[const.DOMAIN][scups.lower()]["coordinator"]
    # add sensor entities
    _entities = []
    _entities.extend([EdataInfoSensor(coordinator, *x) for x in INFO_SENSORS_DESC])
    _entities.extend([EdataEnergySensor(coordinator, *x) for x in ENERGY_SENSORS_DESC])
    _entities.extend([EdataPowerSensor(coordinator, *x) for x in POWER_SENSORS_DESC])
    _entities.extend([EdataCostSensor(coordinator, *x) for x in COST_SENSORS_DESC])
    async_add_entities(_entities)

    return True


class EdataInfoSensor(EdataSensorEntity, SensorEntity):
    """Representation of the info related to an e-data sensor."""

    _attr_icon = "mdi:home-lightning-bolt-outline"
    _attr_native_unit_of_measurement = None
    _attr_has_entity_name = False

    def __init__(
        self, coordinator, name: str, state: str, attributes: list[str]
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, name, state, attributes)

        # override to allow backwards compatibility
        self._attr_translation_key = None
        self._attr_name = f"edata_{coordinator.id}"


class EdataEnergySensor(EdataSensorEntity, SensorEntity):
    """Representation of an energy-related e-data sensor."""

    _attr_icon = "mdi:counter"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR


class EdataPowerSensor(EdataSensorEntity, SensorEntity):
    """Representation of a power-related e-data sensor."""

    _attr_icon = "mdi:gauge"
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT


class EdataCostSensor(EdataSensorEntity, SensorEntity):
    """Representation of an cost-related e-data sensor."""

    _attr_icon = "mdi:currency-eur"
    _attr_native_unit_of_measurement = CURRENCY_EURO
