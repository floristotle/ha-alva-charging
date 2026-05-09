"""Base entity for Alva Charging."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AlvaCoordinator


class AlvaEntity(CoordinatorEntity[AlvaCoordinator]):
    """Common base providing shared device info and naming."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: AlvaCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._key = key
        # The Alva account is the device. We don't have a stable charger ID
        # exposed via the API yet, so we anchor on the config entry id.
        entry_id = coordinator.config_entry.entry_id if coordinator.config_entry else "alva"
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="Alva Charging",
            manufacturer="Alva Charging Services",
            model="Alfen Eve Single (NG910)",
        )
