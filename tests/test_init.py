"""Tests for HK Citation integration setup."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hk_citation.const import (
    CONF_SCAN_INTERVAL,
    CONF_THRESHOLD_MS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_THRESHOLD_MS,
    DOMAIN,
)

MOCK_DATA = {"speakers": {}}


async def _setup_entry(hass: HomeAssistant) -> MockConfigEntry:
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
        return_value=MOCK_DATA,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_setup_entry(hass: HomeAssistant) -> None:
    entry = await _setup_entry(hass)
    assert entry.state is ConfigEntryState.LOADED


async def test_unload_entry(hass: HomeAssistant) -> None:
    entry = await _setup_entry(hass)
    with patch(
        "custom_components.hk_citation.coordinator.HKCitationCoordinator._async_update_data",
        return_value=MOCK_DATA,
    ):
        result = await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
    assert result is True
    assert entry.state is ConfigEntryState.NOT_LOADED
