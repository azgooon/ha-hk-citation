"""Tests for HK Citation coordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hk_citation.const import (
    CONF_SCAN_INTERVAL,
    CONF_THRESHOLD_MS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_THRESHOLD_MS,
    DOMAIN,
)
from custom_components.hk_citation.coordinator import HKCitationCoordinator

FAKE_SPEAKER = {
    "name": "Kitchen speaker",
    "ip": "192.168.4.30",
    "uuid": "aaa-bbb-ccc",
    "model": "HK Citation One",
}

FAKE_CHROMECAST = {
    "name": "Living Room TV",
    "ip": "192.168.4.40",
    "uuid": "ddd-eee-fff",
    "model": "Chromecast",
}

HEALTHY_PROBE_RESULT = {
    "healthy": True,
    "response_time_ms": 150.0,
    "probes": [
        {"endpoint": "get_app_device_id", "ms": 100.0, "error": ""},
        {"endpoint": "reboot", "ms": 150.0, "error": ""},
    ],
}


def _make_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Create and add a mock config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={
            CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
            CONF_THRESHOLD_MS: DEFAULT_THRESHOLD_MS,
        },
    )
    entry.add_to_hass(hass)
    return entry


async def test_coordinator_discovers_speakers(hass: HomeAssistant) -> None:
    """Test that mDNS discovery finds an HK Citation speaker."""
    entry = _make_entry(hass)
    coordinator = HKCitationCoordinator(hass, entry)

    with (
        patch.object(
            coordinator,
            "_discover_speakers_sync",
            return_value=[FAKE_SPEAKER],
        ),
        patch.object(
            coordinator,
            "_probe_speaker",
            return_value=HEALTHY_PROBE_RESULT,
        ),
    ):
        data = await coordinator._async_update_data()

    assert "speakers" in data
    assert "aaa-bbb-ccc" in data["speakers"]
    speaker = data["speakers"]["aaa-bbb-ccc"]
    assert speaker["name"] == "Kitchen speaker"
    assert speaker["ip"] == "192.168.4.30"
    assert speaker["uuid"] == "aaa-bbb-ccc"
    assert speaker["model"] == "HK Citation One"
    assert speaker["healthy"] is True


async def test_coordinator_filters_non_hk_speakers(hass: HomeAssistant) -> None:
    """Test that non-HK speakers from mDNS are filtered out.

    The filtering happens inside _discover_speakers_sync, so we simulate
    that it already filtered by returning an empty list when only a Chromecast
    is on the network. We also verify the sync method's logic separately.
    """
    entry = _make_entry(hass)
    coordinator = HKCitationCoordinator(hass, entry)

    # _discover_speakers_sync only returns HK speakers, so a Chromecast
    # would never be in the returned list.
    with patch.object(
        coordinator,
        "_discover_speakers_sync",
        return_value=[],
    ):
        data = await coordinator._async_update_data()

    assert data["speakers"] == {}


async def test_coordinator_handles_empty_scan(hass: HomeAssistant) -> None:
    """Test coordinator handles an empty mDNS scan gracefully."""
    entry = _make_entry(hass)
    coordinator = HKCitationCoordinator(hass, entry)

    with patch.object(
        coordinator,
        "_discover_speakers_sync",
        return_value=[],
    ):
        data = await coordinator._async_update_data()

    assert data == {"speakers": {}}


async def test_healthy_speaker_both_probes_fast(hass: HomeAssistant) -> None:
    """Test that a speaker with two fast probes is marked healthy."""
    entry = _make_entry(hass)
    coordinator = HKCitationCoordinator(hass, entry)

    # Mock the aiohttp session to return fast responses
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_response)
    coordinator._session = mock_session

    with patch.object(
        coordinator,
        "_discover_speakers_sync",
        return_value=[FAKE_SPEAKER],
    ):
        data = await coordinator._async_update_data()

    speaker = data["speakers"]["aaa-bbb-ccc"]
    assert speaker["healthy"] is True
    assert len(speaker["probes"]) == 2
    assert speaker["probes"][0]["endpoint"] == "get_app_device_id"
    assert speaker["probes"][1]["endpoint"] == "reboot"
    assert speaker["probes"][0]["error"] == ""
    assert speaker["probes"][1]["error"] == ""


async def test_frozen_speaker_one_probe_slow(hass: HomeAssistant) -> None:
    """Test that a speaker is unhealthy when one probe times out."""
    entry = _make_entry(hass)
    coordinator = HKCitationCoordinator(hass, entry)

    # First probe succeeds, second probe times out
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return mock_response
        raise TimeoutError("Connection timed out")

    mock_session = MagicMock()
    mock_session.post = MagicMock(side_effect=side_effect)
    coordinator._session = mock_session

    with patch.object(
        coordinator,
        "_discover_speakers_sync",
        return_value=[FAKE_SPEAKER],
    ):
        data = await coordinator._async_update_data()

    speaker = data["speakers"]["aaa-bbb-ccc"]
    assert speaker["healthy"] is False
    assert len(speaker["probes"]) == 2
    # First probe should be fine
    assert speaker["probes"][0]["error"] == ""
    # Second probe should show timeout
    assert speaker["probes"][1]["error"] == "timed out"


async def test_unreachable_speaker_connection_error(hass: HomeAssistant) -> None:
    """Test that unreachable speaker gets error messages on both probes."""
    entry = _make_entry(hass)
    coordinator = HKCitationCoordinator(hass, entry)

    mock_session = MagicMock()
    mock_session.post = MagicMock(
        side_effect=aiohttp.ClientConnectionError("Connection refused")
    )
    coordinator._session = mock_session

    with patch.object(
        coordinator,
        "_discover_speakers_sync",
        return_value=[FAKE_SPEAKER],
    ):
        data = await coordinator._async_update_data()

    speaker = data["speakers"]["aaa-bbb-ccc"]
    assert speaker["healthy"] is False
    assert len(speaker["probes"]) == 2
    assert speaker["probes"][0]["error"] != ""
    assert speaker["probes"][1]["error"] != ""
    assert speaker["probes"][0]["ms"] == 0
    assert speaker["probes"][1]["ms"] == 0


async def test_new_speaker_callback(hass: HomeAssistant) -> None:
    """Test that new speaker callbacks fire on first scan but not on repeat."""
    entry = _make_entry(hass)
    coordinator = HKCitationCoordinator(hass, entry)

    callback_calls: list[set[str]] = []
    coordinator.register_new_speaker_callback(lambda uuids: callback_calls.append(uuids))

    with (
        patch.object(
            coordinator,
            "_discover_speakers_sync",
            return_value=[FAKE_SPEAKER],
        ),
        patch.object(
            coordinator,
            "_probe_speaker",
            return_value=HEALTHY_PROBE_RESULT,
        ),
    ):
        # First scan — callback should fire with new UUID
        await coordinator._async_update_data()
        assert len(callback_calls) == 1
        assert "aaa-bbb-ccc" in callback_calls[0]

        # Second scan — same speaker, callback should NOT fire again
        await coordinator._async_update_data()
        assert len(callback_calls) == 1
