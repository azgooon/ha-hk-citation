"""DataUpdateCoordinator for HK Citation Health Monitor."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
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

PROBE_TIMEOUT = 5.0
MDNS_SCAN_SECONDS = 8

# Standalone mDNS scanner script — runs in a separate process to bypass
# HA's Zeroconf monkey-patching.
_SCANNER_SCRIPT = """
import json, time
from zeroconf import ServiceBrowser, Zeroconf

PREFIX = "HK_MODEL_PREFIX_PLACEHOLDER"

class L:
    def __init__(self):
        self.f = []
    def add_service(self, zc, t, n):
        self._h(zc, t, n)
    def update_service(self, zc, t, n):
        self._h(zc, t, n)
    def remove_service(self, zc, t, n):
        pass
    def _h(self, zc, t, n):
        try:
            i = zc.get_service_info(t, n)
        except Exception:
            return
        if not i:
            return
        p = i.properties or {}
        m = p.get(b"md", b"").decode("utf-8", errors="replace")
        if not m.startswith(PREFIX):
            return
        u = p.get(b"id", b"").decode("utf-8", errors="replace")
        if not u:
            return
        a = i.parsed_addresses()
        if not a:
            return
        if any(s["uuid"] == u for s in self.f):
            return
        self.f.append({
            "name": p.get(b"fn", b"").decode("utf-8", errors="replace"),
            "ip": a[0], "uuid": u, "model": m,
        })

zc = Zeroconf()
l = L()
b = ServiceBrowser(zc, "_googlecast._tcp.local.", l)
time.sleep(SCAN_SECONDS_PLACEHOLDER)
b.cancel()
zc.close()
print(json.dumps(l.f))
""".replace("HK_MODEL_PREFIX_PLACEHOLDER", HK_MODEL_PREFIX).replace(
    "SCAN_SECONDS_PLACEHOLDER", str(MDNS_SCAN_SECONDS)
)


def _run_mdns_scan() -> list[dict[str, str]]:
    """Run mDNS scan in a subprocess to get a fresh Zeroconf instance."""
    result = subprocess.run(
        [sys.executable, "-c", _SCANNER_SCRIPT],
        capture_output=True,
        text=True,
        timeout=MDNS_SCAN_SECONDS + 10,
    )
    if result.returncode != 0:
        _LOGGER.error("mDNS scanner failed: %s", result.stderr[:500])
        return []
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        _LOGGER.error("mDNS scanner returned invalid JSON: %s", result.stdout[:200])
        return []


class HKCitationCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that discovers and health-checks HK Citation speakers."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        self._session = async_get_clientsession(hass)
        self._known_uuids: set[str] = set()
        self._new_speaker_callbacks: list = []
        # Persistent speaker registry — survives scan gaps
        self._speakers: dict[str, dict[str, str]] = {}
        self._initial_scan_done = False

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

    async def _discover_speakers(self) -> None:
        """Run mDNS scan and merge results into the speaker registry."""
        found_list = await self.hass.async_add_executor_job(_run_mdns_scan)

        for s in found_list:
            uuid = s["uuid"]
            old = self._speakers.get(uuid)
            self._speakers[uuid] = s
            if not old:
                _LOGGER.info("Discovered speaker: %s at %s", s["name"], s["ip"])
            elif old["ip"] != s["ip"]:
                _LOGGER.info(
                    "Speaker %s IP changed: %s -> %s", s["name"], old["ip"], s["ip"]
                )

        if found_list:
            _LOGGER.debug(
                "mDNS scan found %d speakers (registry total: %d)",
                len(found_list),
                len(self._speakers),
            )
        elif not self._speakers:
            _LOGGER.warning("mDNS scan found 0 HK Citation speakers")
        else:
            _LOGGER.debug(
                "mDNS scan found 0 new speakers, using %d from registry",
                len(self._speakers),
            )

    async def _verify_speaker_reachable(self, ip: str) -> bool:
        """Quick check if a speaker is reachable on port 8008."""
        url = f"http://{ip}:{PORT_8008}/setup/eureka_info"
        try:
            async with self._session.get(
                url, timeout=aiohttp.ClientTimeout(total=3)
            ) as resp:
                return resp.status == 200
        except (aiohttp.ClientError, TimeoutError):
            return False

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
        # Run mDNS discovery on first poll and periodically to catch new
        # speakers or IP changes. After the initial scan, the registry
        # persists so a missed scan doesn't lose speakers.
        if not self._initial_scan_done:
            try:
                await self._discover_speakers()
            except Exception as err:
                raise UpdateFailed(f"mDNS scan failed: {err}") from err
            self._initial_scan_done = True
        else:
            # Run discovery in the background — merge any updates
            try:
                await self._discover_speakers()
            except Exception:
                _LOGGER.debug("mDNS scan failed, using cached speakers", exc_info=True)

        if not self._speakers:
            _LOGGER.warning("No HK Citation speakers in registry")
            return {"speakers": {}}

        # Remove speakers that are no longer reachable at their known IP
        stale = []
        speakers: dict[str, dict[str, Any]] = {}
        for uuid, speaker_info in self._speakers.items():
            reachable = await self._verify_speaker_reachable(speaker_info["ip"])
            if not reachable:
                _LOGGER.debug(
                    "Speaker %s at %s not reachable, skipping probes",
                    speaker_info["name"],
                    speaker_info["ip"],
                )
                # Keep in registry (IP may be temporarily unreachable) but
                # don't include in data so entity shows unavailable
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
