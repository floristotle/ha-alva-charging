"""Sensor platform for Alva Charging."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CHARGE_MODES, DOMAIN
from .coordinator import AlvaCoordinator
from .entity import AlvaEntity


@dataclass(frozen=True, kw_only=True)
class AlvaSensorDescription(SensorEntityDescription):
    """Describes an Alva sensor and how to extract its value."""

    value_fn: Callable[[dict[str, Any]], Any]


SENSORS: tuple[AlvaSensorDescription, ...] = (
    AlvaSensorDescription(
        key="charger_power",
        translation_key="charger_power",
        name="Laadvermogen",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        value_fn=lambda d: d.get("charger_power_w"),
    ),
    AlvaSensorDescription(
        key="energy_total",
        translation_key="energy_total",
        name="Totaal geladen",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=lambda d: d.get("energy_total_kwh"),
    ),
    AlvaSensorDescription(
        key="grid_power",
        translation_key="grid_power",
        name="Netvermogen",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        value_fn=lambda d: d.get("grid_power_w"),
    ),
    AlvaSensorDescription(
        key="charger_status",
        translation_key="charger_status",
        name="Laadstatus",
        value_fn=lambda d: d.get("charger_status"),
    ),
    AlvaSensorDescription(
        key="charge_mode",
        translation_key="charge_mode",
        name="Laadmodus",
        value_fn=lambda d: CHARGE_MODES.get(d.get("mode")) if d.get("mode") is not None else None,
    ),
    AlvaSensorDescription(
        key="charge_need_km",
        translation_key="charge_need_km",
        name="Laadbehoefte",
        native_unit_of_measurement="km",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("charge_need_km"),
    ),
    AlvaSensorDescription(
        key="month_peak",
        translation_key="month_peak",
        name="Maandpiek",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        value_fn=lambda d: d.get("current_month_peak_w"),
    ),
    AlvaSensorDescription(
        key="session_start",
        translation_key="session_start",
        name="Sessie gestart",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: d.get("session_start"),
    ),
    AlvaSensorDescription(
        key="solar_savings",
        translation_key="solar_savings",
        name="Zon-besparing",
        native_unit_of_measurement="EUR",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda d: d.get("solar_savings_eur"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Alva sensors from a config entry."""
    coordinator: AlvaCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(AlvaSensor(coordinator, desc) for desc in SENSORS)


class AlvaSensor(AlvaEntity, SensorEntity):
    """A single Alva sensor entity."""

    entity_description: AlvaSensorDescription

    def __init__(
        self, coordinator: AlvaCoordinator, description: AlvaSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data or {})
