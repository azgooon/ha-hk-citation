"""Tests for HK Citation binary sensor."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.const import STATE_ON, STATE_OFF
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hk_citation.const import (
    CONF_SCAN_INTERVAL,
    CONF_THRESHOLD_MS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_THRESHOLD_MS,
    DOMAIN,
)

MOCK_COORDINATOR_DATA = {
    "speakers": {
        "uuid-kitchen": {
            "name": "Kitchen speaker",
            "ip": "192.168.4.30",
            "uuid": "uuid-kitchen",
            "model": "HK Citation One",
            "healthy": True,
            "response_time_ms": 50.0,
            "probes": [
                {"endpoint": "get_app_device_id", "ms": 45.0, "error": ""},
                {"endpoint": "reboot", "ms": 50.0, "error": ""},
            ],
        },
        "uuid-hallway": {
            "name": "Hallway speaker",
            "ip": "192.168.4.33",
            "uuid": "uuid-hallway",
            "model": "HK Citation One",
            "healthy": False,
            "response_time_ms": 3106.0,
            "probes": [
                {"endpoint": "get_app_device_id", "ms": 38.0, "error": ""},
                {"endpoint": "reboot", "ms": 3106.0, "error": ""},
            ],
        },
    }
}


async def _setup_integration(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={
            CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
            CONF_THRESHOLD_MS: DEFAULT_THRESHOLD_MS,
        },
        unique_id=DOMAIN,
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.hk_citation.coordinator.HKCitationCoordinator._async_update_data",
        return_value=MOCK_COORDINATOR_DATA,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return entry


async def test_binary_sensor_healthy_speaker(hass: HomeAssistant) -> None:
    await _setup_integration(hass)
    state = hass.states.get("binary_sensor.kitchen_speaker_health")
    assert state is not None
    assert state.state == STATE_ON


async def test_binary_sensor_frozen_speaker(hass: HomeAssistant) -> None:
    await _setup_integration(hass)
    state = hass.states.get("binary_sensor.hallway_speaker_health")
    assert state is not None
    assert state.state == STATE_OFF


async def test_binary_sensor_attributes(hass: HomeAssistant) -> None:
    await _setup_integration(hass)
    state = hass.states.get("binary_sensor.kitchen_speaker_health")
    assert state.attributes["response_time_ms"] == 50.0
    assert state.attributes["ip_address"] == "192.168.4.30"


async def test_binary_sensor_device_info(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    await _setup_integration(hass)
    er_entry = entity_registry.async_get("binary_sensor.kitchen_speaker_health")
    assert er_entry is not None
    device = device_registry.async_get(er_entry.device_id)
    assert device is not None
    assert device.manufacturer == "Harman Kardon"
    assert device.model == "HK Citation One"
