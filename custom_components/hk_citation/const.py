"""Constants for HK Citation Health Monitor."""

from homeassistant.const import Platform

DOMAIN = "hk_citation"
PLATFORMS = [Platform.BINARY_SENSOR]

CAST_SERVICE = "_googlecast._tcp.local."
HK_MODEL_PREFIX = "HK Citation"

PORT_8008 = 8008
PORT_8443 = 8443

PROBE_ENDPOINTS = [
    ("/setup/get_app_device_id", {"app_id": "E8C28D3C"}),
    ("/setup/reboot", {"params": "now"}),
]
HTTPS_PROBE_ENDPOINT = "/setup/eureka_info"

CONF_SCAN_INTERVAL = "scan_interval"
CONF_THRESHOLD_MS = "threshold_ms"

DEFAULT_SCAN_INTERVAL = 300  # 5 minutes
DEFAULT_THRESHOLD_MS = 1000
HTTPS_PROBE_TIMEOUT = 3.0
