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
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CHARGE_MODES, DOMAIN
from .coordinator import AlvaCoordinator
from .entity import AlvaEntity


@dataclass(frozen=True, kw_only=True)
class AlvaSensorDescription(SensorEntityDescription):
    """Describes an Alva sensor and how to extract its value."""

    value_fn: Callable[[dict[str, Any]], Any]


def _period_kwh(period: str, kind: str) -> AlvaSensorDescription:
    """Build a kWh sensor description for total/solar/grid × day/month/year."""
    nl_kind = {"total": "totaal", "solar": "zon", "grid": "net"}[kind]
    nl_period = {"day": "vandaag", "month": "deze maand", "year": "dit jaar"}[period]
    return AlvaSensorDescription(
        key=f"{period}_{kind}_kwh",
        translation_key=f"{period}_{kind}_kwh",
        name=f"Geladen {nl_kind} {nl_period}",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value_fn=lambda d, p=period, k=kind: d.get(f"{p}_{k}_kwh"),
    )


def _solar_pct(period: str) -> AlvaSensorDescription:
    nl_period = {"day": "vandaag", "month": "deze maand", "year": "dit jaar"}[period]
    return AlvaSensorDescription(
        key=f"{period}_solar_pct",
        translation_key=f"{period}_solar_pct",
        name=f"Zonpercentage {nl_period}",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d, p=period: d.get(f"{p}_solar_pct"),
    )


def _eur_sensor(period: str, kind: str) -> AlvaSensorDescription:
    """EUR sensors from /api/costs (home grid import/export) and /api/savings."""
    nl_kind = {
        "grid_import": "Netimport kosten",
        "grid_export": "Netexport opbrengst",
        "solar_savings": "Zon besparing",
    }[kind]
    nl_period = {"day": "vandaag", "month": "deze maand", "year": "dit jaar"}[period]
    return AlvaSensorDescription(
        key=f"{period}_{kind}_eur",
        translation_key=f"{period}_{kind}_eur",
        name=f"{nl_kind} {nl_period}",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement="EUR",
        suggested_display_precision=2,
        value_fn=lambda d, p=period, k=kind: d.get(f"{p}_{k}_eur"),
    )


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
    # Year total used as the Energy Dashboard input. State class
    # `total_increasing` makes HA treat the January-1 rollover (year resets to
    # 0) as a meter reset rather than a negative anomaly.
    AlvaSensorDescription(
        key="energy_total",
        translation_key="energy_total",
        name="Totaal geladen",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value_fn=lambda d: d.get("year_total_kwh"),
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
    # Aggregates per period: total / solar / grid kWh + solar%
    *(_period_kwh(p, k) for p in ("day", "month", "year") for k in ("total", "solar", "grid")),
    *(_solar_pct(p) for p in ("day", "month", "year")),
    # EUR cost sensors per period (home-level grid import/export, solar savings)
    *(
        _eur_sensor(p, k)
        for p in ("day", "month", "year")
        for k in ("grid_import", "grid_export", "solar_savings")
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
