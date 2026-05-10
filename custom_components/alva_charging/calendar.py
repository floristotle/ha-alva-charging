"""Calendar platform — exposes the autopilot charge schedule as read-only events.

Each `autopilot_setpoints` entry covers a 15-minute window at a target wattage.
Consecutive same-wattage slots are merged into a single event for a cleaner
calendar view. 0-watt slots are emitted as "Pauze" events; non-zero slots as
"Laden X.X kW".
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.components.calendar import (
    CalendarEntity,
    CalendarEntityFeature,
    CalendarEvent,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AlvaCoordinator
from .entity import AlvaEntity

_LOGGER = logging.getLogger(__name__)

SLOT_MINUTES = 15


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AlvaCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([AlvaScheduleCalendar(coordinator)])


class AlvaScheduleCalendar(AlvaEntity, CalendarEntity):
    """Read-only calendar showing the autopilot/zon charge schedule."""

    _attr_supported_features = CalendarEntityFeature(0)  # explicit: read-only
    _attr_name = "Laadschema"

    def __init__(self, coordinator: AlvaCoordinator) -> None:
        super().__init__(coordinator, "schedule_calendar")

    @property
    def event(self) -> CalendarEvent | None:
        """Currently active event (the schedule slot covering 'now')."""
        events = self._build_events()
        now = datetime.now(timezone.utc)
        for ev in events:
            if ev.start <= now < ev.end:
                return ev
        # If no active slot, return the next one if any.
        for ev in events:
            if ev.start > now:
                return ev
        return None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return events overlapping [start_date, end_date]."""
        events = self._build_events()
        return [
            e for e in events
            if e.end > start_date and e.start < end_date
        ]

    def _build_events(self) -> list[CalendarEvent]:
        """Convert the setpoints dict into a list of merged calendar events."""
        sp: dict[str, Any] | None = (self.coordinator.data or {}).get("autopilot_setpoints")
        if not isinstance(sp, dict) or not sp:
            return []

        # Parse and sort the (timestamp, watts) pairs.
        slots: list[tuple[datetime, float]] = []
        for k, v in sp.items():
            try:
                dt = datetime.fromisoformat(k.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
            if not isinstance(v, (int, float)):
                continue
            slots.append((dt, float(v)))
        if not slots:
            return []
        slots.sort(key=lambda p: p[0])

        # Merge consecutive same-watt slots.
        events: list[CalendarEvent] = []
        run_start = slots[0][0]
        run_watts = slots[0][1]
        prev_end = run_start + timedelta(minutes=SLOT_MINUTES)
        for ts, watts in slots[1:]:
            slot_end = ts + timedelta(minutes=SLOT_MINUTES)
            if watts == run_watts and ts == prev_end:
                # Extend current run
                prev_end = slot_end
                continue
            events.append(_event(run_start, prev_end, run_watts))
            run_start = ts
            run_watts = watts
            prev_end = slot_end
        events.append(_event(run_start, prev_end, run_watts))
        return events


def _event(start: datetime, end: datetime, watts: float) -> CalendarEvent:
    if watts <= 0:
        summary = "Pauze"
    else:
        summary = f"Laden {watts / 1000:.1f} kW"
    return CalendarEvent(
        start=start,
        end=end,
        summary=summary,
        description=f"Autopilot-doel: {watts:.0f} W",
    )
