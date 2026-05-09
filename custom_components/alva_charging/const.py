"""Constants for the Alva Charging integration."""
from __future__ import annotations

DOMAIN = "alva_charging"

# AWS Cognito configuration (extracted from slimladen.alva-charging.nl Flutter bundle)
COGNITO_USER_POOL_ID = "eu-central-1_5xHk0jl2i"
COGNITO_CLIENT_ID = "3blm957hpc2c3rp6db87mkga1t"
COGNITO_REGION = "eu-central-1"

# Scoptvision API
API_BASE_URL = "https://ta5s5qcaj0.execute-api.eu-central-1.amazonaws.com/v1/api"
API_KEY = "UNOhCoqbpC4Qucp8Ey2jX8QxuY9W7znh3QAvr6rX"

# Polling interval (seconds). Cognito access tokens are valid for 1h by default;
# we refresh as needed inside the coordinator.
SCAN_INTERVAL_SECONDS = 30

# Charge mode mapping (observed values from powerconnect_control endpoint)
CHARGE_MODES = {
    1: "autopilot",
    2: "solar",
    3: "boost",
}

# Charger status values seen in realtime_data evChargerMetrics.state
CHARGER_STATUS_CHARGING = "charging"
CHARGER_STATUS_PAUSED = "paused"
CHARGER_STATUS_IDLE = "idle"
