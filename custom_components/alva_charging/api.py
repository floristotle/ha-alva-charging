"""API client for the Scoptvision/Alva Charging cloud."""
from __future__ import annotations

import asyncio
import json as json_lib
import logging
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    API_BASE_URL,
    API_KEY,
    COGNITO_CLIENT_ID,
    COGNITO_REGION,
    COGNITO_USER_POOL_ID,
    SLIMLADEN_BASE_URL,
)

_LOGGER = logging.getLogger(__name__)


class AlvaAuthError(Exception):
    """Raised when authentication fails."""


class AlvaApiError(Exception):
    """Raised when an API request fails."""


class AlvaApiClient:
    """Wrapper around the Scoptvision API used by Alva Charging."""

    def __init__(self, hass: HomeAssistant, email: str, password: str) -> None:
        self._hass = hass
        self._email = email
        self._password = password
        self._session: aiohttp.ClientSession = async_get_clientsession(hass)
        self._access_token: str | None = None
        self._id_token: str | None = None
        self._refresh_token: str | None = None

    async def async_login(self) -> None:
        """Authenticate against AWS Cognito (SRP flow) and store tokens."""

        def _login() -> dict[str, str]:
            # pycognito is sync; run in executor to avoid blocking the event loop.
            from pycognito import Cognito  # pylint: disable=import-outside-toplevel

            user = Cognito(
                user_pool_id=COGNITO_USER_POOL_ID,
                client_id=COGNITO_CLIENT_ID,
                user_pool_region=COGNITO_REGION,
                username=self._email,
            )
            user.authenticate(password=self._password)
            return {
                "access_token": user.access_token,
                "id_token": user.id_token,
                "refresh_token": user.refresh_token,
            }

        try:
            tokens = await self._hass.async_add_executor_job(_login)
        except Exception as err:  # pycognito raises various boto3 errors
            _LOGGER.debug("Cognito login failed: %s", err)
            raise AlvaAuthError(str(err)) from err

        # AWS API Gateway (execute-api.eu-central-1) requires access_token.
        # slimladen.alva-charging.nl/api requires id_token. Keep both.
        self._access_token = tokens["access_token"]
        self._id_token = tokens["id_token"]
        self._refresh_token = tokens["refresh_token"]

    async def async_refresh(self) -> None:
        """Refresh the access token using the refresh token, or re-login."""
        if not self._refresh_token:
            await self.async_login()
            return

        def _refresh() -> dict[str, str]:
            from pycognito import Cognito  # pylint: disable=import-outside-toplevel

            user = Cognito(
                user_pool_id=COGNITO_USER_POOL_ID,
                client_id=COGNITO_CLIENT_ID,
                user_pool_region=COGNITO_REGION,
                username=self._email,
                refresh_token=self._refresh_token,
            )
            user.check_token(renew=True)
            return {
                "access_token": user.access_token,
                "id_token": user.id_token,
                "refresh_token": user.refresh_token or self._refresh_token,
            }

        try:
            tokens = await self._hass.async_add_executor_job(_refresh)
            self._access_token = tokens["access_token"]
            self._id_token = tokens["id_token"]
            self._refresh_token = tokens["refresh_token"]
        except Exception as err:
            _LOGGER.debug("Cognito refresh failed, falling back to full login: %s", err)
            await self.async_login()

    def _headers(self) -> dict[str, str]:
        if not self._access_token:
            raise AlvaAuthError("Not authenticated")
        return {
            "Authorization": f"Bearer {self._access_token}",
            "x-api-key": API_KEY,
            "Content-Type": "application/json",
            "Accept-Language": "nl-nl",
            "Origin": "https://slimladen.alva-charging.nl",
            "Referer": "https://slimladen.alva-charging.nl/",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        json_body: Any = None,
        retry: bool = True,
    ) -> Any:
        url = f"{API_BASE_URL}/{endpoint.strip('/')}/"
        # Serialize manually so the Content-Type header stays exactly
        # "application/json" (without charset=utf-8 that aiohttp's json= adds);
        # the AWS Lambda rejects with 400 "Wrong body format" otherwise.
        data = json_lib.dumps(json_body) if json_body is not None else None
        try:
            async with self._session.request(
                method,
                url,
                headers=self._headers(),
                data=data,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status == 401 and retry:
                    _LOGGER.debug("401 on %s, refreshing token", endpoint)
                    await self.async_refresh()
                    return await self._request(method, endpoint, json_body, retry=False)
                if resp.status >= 400:
                    text = await resp.text()
                    _LOGGER.warning(
                        "Alva %s %s -> %s headers=%s body=%s",
                        method,
                        endpoint,
                        resp.status,
                        dict(resp.headers),
                        text[:500],
                    )
                    raise AlvaApiError(
                        f"{method} {endpoint} -> {resp.status}: {text[:300]}"
                    )
                return await resp.json()
        except asyncio.TimeoutError as err:
            raise AlvaApiError(f"Timeout on {method} {endpoint}") from err

    async def async_get_charger_state(
        self, connector_id: int = 1
    ) -> list[dict[str, Any]]:
        """POST realtime_data for evChargerMetrics.state — returns charger live state.

        Note: gridMetrics through realtime_data returns 400 Wrong body format
        for every body shape we tried. The Flutter app does fetch gridMetrics
        but likely via a different endpoint (TBD) — left out of MVP.
        """
        body = [
            {
                "measurement": "evChargerMetrics",
                "field": "state",
                "tags": {"connector_id": connector_id},
            }
        ]
        return await self._request("POST", "realtime_data", json_body=body)

    async def async_get_powerconnect_control(self) -> dict[str, Any]:
        """Return the powerconnect_control object (mode, online, session info)."""
        return await self._request("GET", "powerconnect_control")

    # NOTE: /savings/ lives on slimladen.alva-charging.nl (cookie auth),
    # not on the AWS API Gateway — intentionally not implemented in MVP.

    async def async_get_total_charged_wh(
        self, time1: str, time2: str, connector_id: int = 1
    ) -> float | None:
        """Return total Wh charged between time1 and time2 (single delta).

        deltaMeter returns ONE [timestamp, delta_wh] pair across the window
        (verified via probe). Same value the portal shows as 'Totaal verbruik'.
        """
        body = [
            {
                "time1": time1,
                "time2": time2,
                "retention_policy": "rp_one_h",
                "field": "mean_chargedAbsEnergyTot_Wh",
                "measurement": "evChargerMetrics",
                "operator": "deltaMeter",
                "tags": {"connector_id": connector_id},
            }
        ]
        result = await self._request("POST", "historical_data", json_body=body)
        if not isinstance(result, list) or not result:
            return None
        item = result[0]
        if item.get("no_data"):
            return None
        data = item.get("data")
        if isinstance(data, list) and len(data) >= 2:
            value = data[1]
            if isinstance(value, (int, float)) and value >= 0:
                return float(value)
        return None

    async def async_get_grid_power_w(self) -> float | None:
        """Return the most recent ~minute-level grid power reading (W).

        Uses the site's alt body shape on /realtime_data/ with a single
        `time` parameter and `rp_one_m` retention. Negative values = exporting
        to the grid; positive = importing. Resolution ~minute (much better
        than the hourly historical_data fallback we used in 0.4.x).
        """
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        body = [
            {
                "time": now_iso,
                "retention_policy": "rp_one_m",
                "field": "actualPowerTot_W",
                "measurement": "gridMetrics",
            }
        ]
        result = await self._request("POST", "realtime_data", json_body=body)
        if not isinstance(result, list) or not result:
            return None
        item = result[0]
        if item.get("no_data"):
            return None
        data = item.get("data")
        # Response shape: data is either [[ts, val]] or [ts, val] depending on call.
        if isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, list) and len(first) >= 2 and isinstance(first[1], (int, float)):
                return float(first[1])
            if isinstance(first, str) and len(data) >= 2 and isinstance(data[1], (int, float)):
                return float(data[1])
        return None

    async def async_get_solar_charge_kwh(
        self, time1: str, time2: str, connector_id: int = 1
    ) -> float | None:
        """Return total kWh charged from solar between time1 and time2."""
        body = [
            {
                "time1": time1,
                "time2": time2,
                "retention_policy": None,
                "field": "solar_charge",
                "measurement": None,
                "frequency": "total",
                "tags": {"connector_id": connector_id},
            }
        ]
        result = await self._request("POST", "calculated_data", json_body=body)
        if not isinstance(result, list) or not result:
            return None
        item = result[0]
        if item.get("no_data"):
            return None
        data = item.get("data")
        if isinstance(data, list) and len(data) >= 2:
            value = data[1]
            if isinstance(value, (int, float)) and value >= 0:
                return float(value)
        return None

    # NOTE: slimladen.alva-charging.nl/api/{costs,savings} endpoints removed
    # in v0.4.0. Their EUR data is whole-house (not EV-only), bloats HA's
    # recorder DB without much benefit, and the savings/ endpoint ignores
    # its time params (always returns the same value). Code retained below
    # but no longer wired into the coordinator.
    async def _slimladen_get(self, endpoint: str, params: dict[str, str]) -> Any:
        """GET https://slimladen.alva-charging.nl/api/<endpoint>/ with id_token."""
        if not self._id_token:
            raise AlvaAuthError("Not authenticated (no id_token)")
        # Build query string manually to match the format the portal uses.
        from urllib.parse import urlencode  # local import keeps top of file clean
        url = f"{SLIMLADEN_BASE_URL}/{endpoint.strip('/')}/"
        if params:
            url = f"{url}?{urlencode(params)}"
        headers = {
            "Authorization": f"Bearer {self._id_token}",
            "Content-Type": "application/json",
            "Accept-Language": "nl-nl",
            "Origin": "https://slimladen.alva-charging.nl",
            "Referer": "https://slimladen.alva-charging.nl/",
        }
        try:
            async with self._session.get(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status == 401:
                    # id_token might have expired — refresh and retry once.
                    await self.async_refresh()
                    headers["Authorization"] = f"Bearer {self._id_token}"
                    async with self._session.get(
                        url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)
                    ) as r2:
                        if r2.status >= 400:
                            text = await r2.text()
                            raise AlvaApiError(
                                f"slimladen GET {endpoint} -> {r2.status}: {text[:200]}"
                            )
                        return await r2.json()
                if resp.status >= 400:
                    text = await resp.text()
                    raise AlvaApiError(
                        f"slimladen GET {endpoint} -> {resp.status}: {text[:200]}"
                    )
                return await resp.json()
        except asyncio.TimeoutError as err:
            raise AlvaApiError(f"Timeout on slimladen GET {endpoint}") from err

    async def async_get_costs(self, time1: str, time2: str) -> dict[str, float] | None:
        """Return {'import': eur_cost, 'export': eur_revenue} for the home over the period."""
        result = await self._slimladen_get(
            "costs", {"start_time": time1, "end_time": time2}
        )
        if isinstance(result, dict):
            return result
        return None

    async def async_get_solar_savings_eur(
        self, time1: str, time2: str
    ) -> float | None:
        """Return EUR savings from solar charging over the period."""
        result = await self._slimladen_get(
            "savings", {"start_time": time1, "end_time": time2}
        )
        if isinstance(result, dict):
            value = result.get("solar")
            if isinstance(value, (int, float)):
                return float(value)
        return None

    async def async_set_mode(self, mode: int) -> bool:
        """Set the charge mode. Returns True on success.

        Verified via probe: POST powerconnect_control with body {"mode": <int>}
        returns {"message": true}. Known mappings: 1=autopilot (likely),
        2=solar, 3=boost. Mode 0 observed when no schedule is active and
        cannot be set explicitly via the portal.
        """
        result = await self._request(
            "POST", "powerconnect_control", json_body={"mode": int(mode)}
        )
        return isinstance(result, dict) and result.get("message") is True
