"""Data update coordinator for Alva Charging."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.storage import Store

from .api import AlvaApiClient, AlvaApiError, AlvaAuthError
from .const import DOMAIN, SCAN_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)

# How often to refresh the cumulative kWh (more expensive, less time-critical
# than the realtime endpoints).
ENERGY_UPDATE_INTERVAL = timedelta(minutes=2)

# Storage version for the persisted baseline + last cumulative value.
STORAGE_VERSION = 1


class AlvaCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that polls the Scoptvision API and exposes parsed data."""

    def __init__(self, hass: HomeAssistant, email: str, password: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )
        self.api = AlvaApiClient(hass, email, password)
        self._authenticated = False
        self._store: Store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_state")
        self._baseline_iso: str | None = None
        self._last_energy_wh: float | None = None
        self._last_energy_fetch: datetime | None = None

    async def async_initialize(self) -> None:
        """Restore persistent state (baseline + last cumulative kWh)."""
        stored = await self._store.async_load()
        if isinstance(stored, dict):
            self._baseline_iso = stored.get("baseline_iso")
            self._last_energy_wh = stored.get("last_energy_wh")
        if not self._baseline_iso:
            # First-time setup: start the cumulative counter from now (UTC).
            self._baseline_iso = (
                datetime.now(timezone.utc).replace(microsecond=0).isoformat()
                .replace("+00:00", "Z")
            )
            await self._save_state()

    async def _save_state(self) -> None:
        await self._store.async_save(
            {
                "baseline_iso": self._baseline_iso,
                "last_energy_wh": self._last_energy_wh,
            }
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch all relevant endpoints and return a flattened state dict."""
        if not self._authenticated:
            try:
                await self.api.async_login()
                self._authenticated = True
            except AlvaAuthError as err:
                raise UpdateFailed(f"Login failed: {err}") from err

        try:
            realtime, control, savings = await asyncio.gather(
                self.api.async_get_realtime_data(),
                self.api.async_get_powerconnect_control(),
                self.api.async_get_savings(),
            )
        except AlvaApiError as err:
            raise UpdateFailed(str(err)) from err

        state = _parse(realtime, control, savings)

        # Refresh the cumulative kWh on a slower cadence (~every 2 minutes)
        # to avoid hammering the historical_data endpoint.
        now = datetime.now(timezone.utc)
        if (
            self._last_energy_fetch is None
            or now - self._last_energy_fetch >= ENERGY_UPDATE_INTERVAL
        ):
            try:
                energy_wh = await self._fetch_cumulative_energy(now)
            except AlvaApiError as err:
                _LOGGER.debug("Cumulative energy fetch failed: %s", err)
                energy_wh = self._last_energy_wh
            else:
                self._last_energy_fetch = now
                # Guard against transient API blips returning lower totals.
                if (
                    energy_wh is not None
                    and self._last_energy_wh is not None
                    and energy_wh < self._last_energy_wh
                ):
                    _LOGGER.debug(
                        "Ignoring lower cumulative reading %.1f < %.1f",
                        energy_wh,
                        self._last_energy_wh,
                    )
                    energy_wh = self._last_energy_wh
                self._last_energy_wh = energy_wh
                await self._save_state()

        if self._last_energy_wh is not None:
            state["energy_total_kwh"] = round(self._last_energy_wh / 1000.0, 3)

        return state

    async def _fetch_cumulative_energy(self, now: datetime) -> float | None:
        """Sum hourly charged-energy deltas since the persistent baseline."""
        if not self._baseline_iso:
            return None
        time2 = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        items = await self.api.async_get_charged_energy_deltas(
            time1=self._baseline_iso, time2=time2
        )
        total = 0.0
        for item in items or []:
            if item.get("no_data"):
                continue
            data = item.get("data") or {}
            for entry in data.values():
                if isinstance(entry, list) and len(entry) >= 2:
                    delta = entry[1]
                    if isinstance(delta, (int, float)) and delta > 0:
                        total += float(delta)
        return total


def _parse(
    realtime: list[dict[str, Any]] | None,
    control: dict[str, Any] | None,
    savings: dict[str, Any] | None,
) -> dict[str, Any]:
    """Flatten the three responses into a single dict the entities consume."""
    out: dict[str, Any] = {}

    if realtime:
        for item in realtime:
            measurement = item.get("measurement")
            field = item.get("field")
            data = item.get("data") or {}
            if item.get("no_data"):
                continue
            if measurement == "evChargerMetrics" and field == "state":
                state_obj = data.get("1") if isinstance(data, dict) else None
                if isinstance(state_obj, dict):
                    out["charger_power_w"] = _to_float(state_obj.get("power"))
                    out["car_plugged"] = bool(state_obj.get("car_plugged"))
                    out["charger_online"] = bool(state_obj.get("online"))
                    out["charger_status"] = state_obj.get("status")
                    out["car_setting"] = state_obj.get("car_setting")
                ts = data.get("0") if isinstance(data, dict) else None
                if isinstance(ts, str):
                    out["charger_last_update"] = ts
            elif measurement == "gridMetrics" and field == "actualPowerTot_W":
                point = data.get("0") if isinstance(data, dict) else None
                if isinstance(point, list) and len(point) >= 2:
                    out["grid_power_w"] = _to_float(point[1])
                    out["grid_last_update"] = point[0]

    if control:
        out["mode"] = control.get("mode")
        out["online"] = control.get("online")
        out["min_charge_rate_w"] = _to_float(control.get("min_charge_rate"))
        out["max_charge_rate_w"] = _to_float(control.get("max_charge_rate"))
        out["current_month_peak_w"] = _to_float(control.get("current_month_peak"))
        out["charge_need_km"] = _to_float(control.get("charge_need_km"))
        out["charge_end_date"] = control.get("charge_end_date")
        out["session_start"] = control.get("start_session_timestamp")
        out["km_per_hour_charge"] = _to_float(control.get("km_hour_charge"))

    if savings:
        out["solar_savings_eur"] = _to_float(savings.get("solar"))

    return out


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
