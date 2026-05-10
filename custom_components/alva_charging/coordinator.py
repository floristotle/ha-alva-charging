"""Data update coordinator for Alva Charging."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AlvaApiClient, AlvaApiError, AlvaAuthError
from .const import DOMAIN, SCAN_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)

# How often to refresh the slower aggregates (totals per day/month/year + solar
# breakdown). These rarely change minute-to-minute and each refresh costs 6
# API calls.
AGGREGATE_REFRESH_INTERVAL = timedelta(minutes=5)


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
        self._last_aggregates: dict[str, Any] = {}
        self._last_aggregate_fetch: datetime | None = None

    async def async_initialize(self) -> None:
        """Optional one-time async setup hook."""
        return None

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch all relevant endpoints and return a flattened state dict."""
        if not self._authenticated:
            try:
                await self.api.async_login()
                self._authenticated = True
            except AlvaAuthError as err:
                raise UpdateFailed(f"Login failed: {err}") from err

        try:
            charger, control = await asyncio.gather(
                self.api.async_get_charger_state(),
                self.api.async_get_powerconnect_control(),
            )
        except AlvaApiError as err:
            raise UpdateFailed(str(err)) from err

        state = _parse(charger, control)

        now = datetime.now(timezone.utc)
        if (
            self._last_aggregate_fetch is None
            or now - self._last_aggregate_fetch >= AGGREGATE_REFRESH_INTERVAL
        ):
            try:
                aggs = await self._fetch_aggregates(now)
            except AlvaApiError as err:
                _LOGGER.debug("Aggregate fetch failed: %s", err)
            else:
                self._last_aggregates = aggs
                self._last_aggregate_fetch = now

        state.update(self._last_aggregates)
        return state

    async def _fetch_aggregates(self, now: datetime) -> dict[str, Any]:
        """Fetch totals, solar share, and EUR costs for day/month/year windows."""
        windows = _period_windows(now)
        # 4 calls per window: total kWh, solar kWh, costs (import/export EUR),
        # solar savings EUR. All issued in parallel.
        tasks: list[asyncio.Task] = []
        for _label, (t1, t2) in windows.items():
            tasks.append(asyncio.create_task(self.api.async_get_total_charged_wh(t1, t2)))
            tasks.append(asyncio.create_task(self.api.async_get_solar_charge_kwh(t1, t2)))
            tasks.append(asyncio.create_task(self.api.async_get_costs(t1, t2)))
            tasks.append(asyncio.create_task(self.api.async_get_solar_savings_eur(t1, t2)))
        results = await asyncio.gather(*tasks, return_exceptions=True)

        out: dict[str, Any] = {}
        for i, label in enumerate(windows):
            total_wh = results[i * 4]
            solar_kwh = results[i * 4 + 1]
            costs = results[i * 4 + 2]
            savings = results[i * 4 + 3]

            total_kwh = (
                round(total_wh / 1000.0, 2)
                if isinstance(total_wh, (int, float))
                else None
            )
            solar_kwh_val = (
                round(float(solar_kwh), 2)
                if isinstance(solar_kwh, (int, float))
                else None
            )
            grid_kwh = None
            solar_pct = None
            if total_kwh is not None and solar_kwh_val is not None:
                grid_kwh = round(max(total_kwh - solar_kwh_val, 0.0), 2)
                if total_kwh > 0:
                    solar_pct = round((solar_kwh_val / total_kwh) * 100, 1)
                    solar_pct = max(0.0, min(100.0, solar_pct))
            out[f"{label}_total_kwh"] = total_kwh
            out[f"{label}_solar_kwh"] = solar_kwh_val
            out[f"{label}_grid_kwh"] = grid_kwh
            out[f"{label}_solar_pct"] = solar_pct

            if isinstance(costs, dict):
                imp = costs.get("import")
                exp = costs.get("export")
                out[f"{label}_grid_import_eur"] = (
                    round(float(imp), 2) if isinstance(imp, (int, float)) else None
                )
                out[f"{label}_grid_export_eur"] = (
                    round(float(exp), 2) if isinstance(exp, (int, float)) else None
                )
            if isinstance(savings, (int, float)):
                out[f"{label}_solar_savings_eur"] = round(float(savings), 2)

        return out


def _period_windows(now: datetime) -> dict[str, tuple[str, str]]:
    """Return UTC ISO windows for today, this month, this year, ending at `now`."""
    fmt = lambda dt: dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    end = now
    day_start = end.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = day_start.replace(day=1)
    year_start = month_start.replace(month=1)
    return {
        "day": (fmt(day_start), fmt(end)),
        "month": (fmt(month_start), fmt(end)),
        "year": (fmt(year_start), fmt(end)),
    }


def _parse(
    charger: list[dict[str, Any]] | None,
    control: dict[str, Any] | None,
) -> dict[str, Any]:
    """Flatten the realtime + control responses into a single dict."""
    out: dict[str, Any] = {}

    for item in charger or []:
        if item.get("no_data"):
            continue
        if item.get("measurement") == "evChargerMetrics" and item.get("field") == "state":
            data = item.get("data")
            if isinstance(data, list) and len(data) >= 2:
                ts, state_obj = data[0], data[1]
                if isinstance(state_obj, dict):
                    out["charger_power_w"] = _to_float(state_obj.get("power"))
                    out["car_plugged"] = bool(state_obj.get("car_plugged"))
                    out["charger_online"] = bool(state_obj.get("online"))
                    out["charger_status"] = state_obj.get("status")
                    out["car_setting"] = state_obj.get("car_setting")
                if isinstance(ts, str):
                    out["charger_last_update"] = ts

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

    return out


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
