"""Constants for HK Citation Health Monitor."""

from homeassistant.const import Platform

DOMAIN = "hk_citation"
PLATFORMS = [Platform.BINARY_SENSOR]

CAST_SERVICE = "_googlecast._tcp.local."
HK_MODEL_PREFIX = "HK Citation"
HEALTH_CHECK_PORT = 8008

PROBE_ENDPOINTS = [
    ("/setup/get_app_device_id", {"app_id": "E8C28D3C"}),
    ("/setup/reboot", {"params": "now"}),
]

CONF_SCAN_INTERVAL = "scan_interval"
CONF_THRESHOLD_MS = "threshold_ms"

DEFAULT_SCAN_INTERVAL = 300  # 5 minutes
DEFAULT_THRESHOLD_MS = 1000
