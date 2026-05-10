"""Select platform — set the Alva charge mode (Autopilot / Zon / Boost)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AlvaCoordinator
from .entity import AlvaEntity

_LOGGER = logging.getLogger(__name__)

# Mapping option label -> mode integer to send to the API.
# Verified by toggling each option in the slimladen portal (commit 6b6e71f):
#   0 = Boost, 2 = Zon, 3 = Autopilot.
# Mode 1 ("Piek") is intentionally NOT exposed — this account is not entitled
# to that feature and it was only reachable by direct POST during probing.
MODE_OPTIONS: dict[str, int] = {
    "Zon": 2,
    "Autopilot": 3,
    "Boost": 0,
}
INT_TO_OPTION: dict[int, str] = {v: k for k, v in MODE_OPTIONS.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AlvaCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([AlvaModeSelect(coordinator)])


class AlvaModeSelect(AlvaEntity, SelectEntity):
    """Select entity for switching the Alva charge mode."""

    _attr_options = list(MODE_OPTIONS.keys())
    entity_description = SelectEntityDescription(
        key="mode",
        translation_key="charge_mode_select",
        name="Laadmodus instellen",
    )

    def __init__(self, coordinator: AlvaCoordinator) -> None:
        super().__init__(coordinator, self.entity_description.key)
        self._optimistic_option: str | None = None

    @property
    def current_option(self) -> str | None:
        if self._optimistic_option is not None:
            return self._optimistic_option
        mode = (self.coordinator.data or {}).get("mode")
        if mode is None:
            return None
        return INT_TO_OPTION.get(int(mode))

    async def async_select_option(self, option: str) -> None:
        mode_int = MODE_OPTIONS.get(option)
        if mode_int is None:
            _LOGGER.warning("Unknown mode option: %s", option)
            return
        # Show the new option immediately; the next coordinator refresh confirms.
        self._optimistic_option = option
        self.async_write_ha_state()
        ok = await self.coordinator.api.async_set_mode(mode_int)
        if not ok:
            _LOGGER.warning("API did not confirm mode change to %s", option)
        await self.coordinator.async_request_refresh()

    def _handle_coordinator_update(self) -> None:
        # Drop the optimistic value once the coordinator catches up.
        self._optimistic_option = None
        super()._handle_coordinator_update()
