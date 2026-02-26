"""DataUpdateCoordinator for HK Citation Health Monitor."""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from zeroconf import ServiceBrowser, ServiceInfo, ServiceStateChange, Zeroconf

from .const import (
    CAST_SERVICE,
    CONF_SCAN_INTERVAL,
    CONF_THRESHOLD_MS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_THRESHOLD_MS,
    DOMAIN,
    HTTPS_PROBE_ENDPOINT,
    HTTPS_PROBE_TIMEOUT,
    HK_MODEL_PREFIX,
    PORT_8008,
    PORT_8443,
    PROBE_ENDPOINTS,
)

_LOGGER = logging.getLogger(__name__)

MDNS_SCAN_TIMEOUT = 5.0
PROBE_TIMEOUT = 5.0


class HKCitationCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that discovers and health-checks HK Citation speakers."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        self._session = async_get_clientsession(hass)
        self._known_uuids: set[str] = set()
        self._new_speaker_callbacks: list = []

        scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )

    @property
    def threshold_ms(self) -> float:
        """Return the configured response time threshold in milliseconds."""
        return self.entry.options.get(CONF_THRESHOLD_MS, DEFAULT_THRESHOLD_MS)

    def register_new_speaker_callback(self, callback_fn) -> None:
        """Register a callback to be called when new speakers are discovered."""
        self._new_speaker_callbacks.append(callback_fn)

    def _discover_speakers_sync(self) -> list[dict[str, str]]:
        """Discover HK Citation speakers via mDNS (sync, runs in executor)."""
        found: list[dict[str, str]] = []

        def on_state_change(
            zeroconf: Zeroconf,
            service_type: str,
            name: str,
            state_change: ServiceStateChange,
        ) -> None:
            if state_change is not ServiceStateChange.Added:
                return
            info = ServiceInfo(service_type, name)
            if info.request(zeroconf, 3000):
                addresses = info.parsed_addresses()
                if not addresses:
                    return
                props = info.properties
                model = props.get(b"md", b"").decode("utf-8", errors="replace")
                if not model.startswith(HK_MODEL_PREFIX):
                    return
                found.append(
                    {
                        "name": props.get(b"fn", b"").decode(
                            "utf-8", errors="replace"
                        ),
                        "ip": addresses[0],
                        "uuid": props.get(b"id", b"").decode(
                            "utf-8", errors="replace"
                        ),
                        "model": model,
                    }
                )

        zc = Zeroconf()
        try:
            ServiceBrowser(zc, CAST_SERVICE, handlers=[on_state_change])
            time.sleep(MDNS_SCAN_TIMEOUT)
        finally:
            zc.close()

        return found

    async def _probe_speaker(self, ip: str) -> dict[str, Any]:
        """Probe a speaker's health via port 8008 POST timing and port 8443 HTTPS timeout."""
        probes = []

        # Port 8008 POST timing probes
        for endpoint, payload in PROBE_ENDPOINTS:
            url = f"http://{ip}:{PORT_8008}{endpoint}"
            try:
                start = time.monotonic()
                async with self._session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=PROBE_TIMEOUT),
                ) as resp:
                    elapsed_ms = (time.monotonic() - start) * 1000
                    probes.append(
                        {
                            "endpoint": endpoint.split("/")[-1],
                            "ms": round(elapsed_ms, 1),
                            "error": "",
                        }
                    )
            except TimeoutError:
                probes.append(
                    {
                        "endpoint": endpoint.split("/")[-1],
                        "ms": PROBE_TIMEOUT * 1000,
                        "error": "timed out",
                    }
                )
            except aiohttp.ClientError as err:
                probes.append(
                    {
                        "endpoint": endpoint.split("/")[-1],
                        "ms": 0,
                        "error": str(err),
                    }
                )

        # Port 8443 HTTPS probe — timeout means frozen
        https_url = f"https://{ip}:{PORT_8443}{HTTPS_PROBE_ENDPOINT}"
        try:
            start = time.monotonic()
            async with self._session.get(
                https_url,
                ssl=False,
                timeout=aiohttp.ClientTimeout(total=HTTPS_PROBE_TIMEOUT),
            ) as resp:
                elapsed_ms = (time.monotonic() - start) * 1000
                probes.append(
                    {
                        "endpoint": "https:8443/eureka_info",
                        "ms": round(elapsed_ms, 1),
                        "error": "",
                    }
                )
        except TimeoutError:
            probes.append(
                {
                    "endpoint": "https:8443/eureka_info",
                    "ms": HTTPS_PROBE_TIMEOUT * 1000,
                    "error": "frozen (port 8443 timeout)",
                }
            )
        except aiohttp.ClientError as err:
            probes.append(
                {
                    "endpoint": "https:8443/eureka_info",
                    "ms": 0,
                    "error": str(err),
                }
            )

        # Evaluate health — unhealthy if any probe fails
        post_probes = probes[:2]
        https_probe = probes[2] if len(probes) > 2 else None
        worst_post_time = max((p["ms"] for p in post_probes), default=0)
        post_slow = worst_post_time >= self.threshold_ms
        post_errors = any(p["error"] for p in post_probes)
        https_failed = https_probe is not None and bool(https_probe["error"])

        healthy = not post_slow and not post_errors and not https_failed
        worst_time = max((p["ms"] for p in probes), default=0)

        error = ""
        if https_failed:
            error = https_probe["error"]
        elif post_errors:
            error = next(p["error"] for p in post_probes if p["error"])

        return {
            "healthy": healthy,
            "response_time_ms": worst_time,
            "probes": probes,
            "error": error,
        }

    async def _async_update_data(self) -> dict[str, Any]:
        """Discover speakers and check their health."""
        try:
            discovered = await self.hass.async_add_executor_job(
                self._discover_speakers_sync
            )
        except Exception as err:
            raise UpdateFailed(f"mDNS scan failed: {err}") from err

        speakers: dict[str, dict[str, Any]] = {}
        for speaker_info in discovered:
            uuid = speaker_info["uuid"]
            if not uuid:
                continue
            health = await self._probe_speaker(speaker_info["ip"])
            speakers[uuid] = {
                **speaker_info,
                **health,
            }

        new_uuids = set(speakers.keys()) - self._known_uuids
        if new_uuids:
            self._known_uuids.update(new_uuids)
            for cb in self._new_speaker_callbacks:
                cb(new_uuids)

        return {"speakers": speakers}

    @callback
    def update_interval_from_options(self) -> None:
        """Update the scan interval from config entry options."""
        scan_interval = self.entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        self.update_interval = timedelta(seconds=scan_interval)
