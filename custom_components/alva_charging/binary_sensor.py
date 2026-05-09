"""Binary sensor platform for Alva Charging."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AlvaCoordinator
from .entity import AlvaEntity


@dataclass(frozen=True, kw_only=True)
class AlvaBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], bool | None]


BINARY_SENSORS: tuple[AlvaBinarySensorDescription, ...] = (
    AlvaBinarySensorDescription(
        key="car_plugged",
        translation_key="car_plugged",
        name="Auto verbonden",
        device_class=BinarySensorDeviceClass.PLUG,
        value_fn=lambda d: d.get("car_plugged"),
    ),
    AlvaBinarySensorDescription(
        key="charger_online",
        translation_key="charger_online",
        name="Laadpaal online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda d: d.get("charger_online"),
    ),
    AlvaBinarySensorDescription(
        key="charging",
        translation_key="charging",
        name="Aan het laden",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        # Treat as charging when actual power is flowing OR the API status
        # explicitly says charging. The "paused" status can briefly coexist
        # with non-zero power (e.g. between boost-cycles), which previously
        # made this sensor read "off" while the car was clearly drawing kW.
        value_fn=lambda d: (
            (d.get("charger_power_w") or 0) > 100
            or d.get("charger_status") == "charging"
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AlvaCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(AlvaBinarySensor(coordinator, desc) for desc in BINARY_SENSORS)


class AlvaBinarySensor(AlvaEntity, BinarySensorEntity):
    entity_description: AlvaBinarySensorDescription

    def __init__(
        self, coordinator: AlvaCoordinator, description: AlvaBinarySensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator.data or {})
