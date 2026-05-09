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

        # The Flutter app uses the access_token (not id_token) in its
        # Authorization header — verified by comparing JWT kid prefixes
        # against what the browser sends.
        self._access_token = tokens["access_token"]
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
                "refresh_token": user.refresh_token or self._refresh_token,
            }

        try:
            tokens = await self._hass.async_add_executor_job(_refresh)
            self._access_token = tokens["access_token"]
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

    async def async_get_charged_energy_deltas(
        self, time1: str, time2: str, connector_id: int = 1
    ) -> list[dict[str, Any]]:
        """Return hourly charged-energy deltas (Wh) between two ISO timestamps.

        Each item in `data` is keyed by index ("0", "1", ...) with value
        ["timestamp", delta_wh]. Sum the deltas to get cumulative Wh charged.
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
        return await self._request("POST", "historical_data", json_body=body)
