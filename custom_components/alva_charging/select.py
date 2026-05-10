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
# Mode 0 ("off"/no active schedule) is read-only — not user-settable.
# Mode 1 ("Piek") was discovered during testing but is intentionally NOT
# exposed here: it's a feature the user's account is not entitled to and
# was only reachable by directly POSTing to the API.
MODE_OPTIONS: dict[str, int] = {
    "Zon": 2,
    "Autopilot": 3,
    # Boost mode number is not yet identified — leaving out of options
    # until we probe a real Boost click.
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

    @property
    def current_option(self) -> str | None:
        mode = (self.coordinator.data or {}).get("mode")
        if mode is None:
            return None
        return INT_TO_OPTION.get(int(mode))

    async def async_select_option(self, option: str) -> None:
        mode_int = MODE_OPTIONS.get(option)
        if mode_int is None:
            _LOGGER.warning("Unknown mode option: %s", option)
            return
        ok = await self.coordinator.api.async_set_mode(mode_int)
        if not ok:
            _LOGGER.warning("API did not confirm mode change to %s", option)
        # Refresh state so the new mode shows up promptly.
        await self.coordinator.async_request_refresh()
