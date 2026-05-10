"""Constants for the Alva Charging integration."""
from __future__ import annotations

DOMAIN = "alva_charging"

# AWS Cognito configuration (extracted from slimladen.alva-charging.nl Flutter bundle)
COGNITO_USER_POOL_ID = "eu-central-1_5xHk0jl2i"
COGNITO_CLIENT_ID = "3blm957hpc2c3rp6db87mkga1t"
COGNITO_REGION = "eu-central-1"

# Scoptvision AWS API (powerconnect_control, realtime_data, historical_data,
# calculated_data, ...). Authenticated with the Cognito access_token.
API_BASE_URL = "https://ta5s5qcaj0.execute-api.eu-central-1.amazonaws.com/v1/api"
API_KEY = "UNOhCoqbpC4Qucp8Ey2jX8QxuY9W7znh3QAvr6rX"

# Alva-branded domain hosts a separate /api with cost/savings endpoints.
# It uses the Cognito id_token (NOT access_token) for auth — different
# Cognito authorizer setup. Returns home-level numbers (whole house grid
# import/export EUR), not strictly EV-only.
SLIMLADEN_BASE_URL = "https://slimladen.alva-charging.nl/api"

# Polling interval (seconds). Cognito access tokens are valid for 1h by default;
# we refresh as needed inside the coordinator.
SCAN_INTERVAL_SECONDS = 30

# Charge mode mapping (observed values from powerconnect_control endpoint).
# Confirmed by toggling each mode and observing what the slimladen portal
# shows: 1 → "Piek" (peak-limited), 2 → "Zon" (solar), 3 → "Boost".
# Mode 0 is what the API returns when no active schedule applies (cannot be
# set explicitly via the user-facing UI). The portal also shows an inactive
# "Autopilot" button which appears to be a higher-tier feature unrelated to
# any of these numeric values.
CHARGE_MODES = {
    0: "off",
    1: "peak",
    2: "solar",
    3: "boost",
}

# Charger status values seen in realtime_data evChargerMetrics.state
CHARGER_STATUS_CHARGING = "charging"
CHARGER_STATUS_PAUSED = "paused"
CHARGER_STATUS_IDLE = "idle"
