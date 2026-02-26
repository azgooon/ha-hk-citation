"""Tests for HK Citation config flow."""

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hk_citation.const import (
    CONF_SCAN_INTERVAL,
    CONF_THRESHOLD_MS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_THRESHOLD_MS,
    DOMAIN,
)


async def test_user_flow_creates_entry(hass: HomeAssistant) -> None:
    """Test that the user flow creates a config entry with no user input."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "HK Citation Health Monitor"
    assert result["data"] == {}


async def test_single_instance_only(hass: HomeAssistant) -> None:
    """Test that only one instance can be configured."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow_shows_form(hass: HomeAssistant) -> None:
    """Test that the options flow shows a form with current values."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={
            CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
            CONF_THRESHOLD_MS: DEFAULT_THRESHOLD_MS,
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"


async def test_options_flow_updates_values(hass: HomeAssistant) -> None:
    """Test that submitting options flow updates the config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={
            CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
            CONF_THRESHOLD_MS: DEFAULT_THRESHOLD_MS,
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_SCAN_INTERVAL: 120,
            CONF_THRESHOLD_MS: 2000,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_SCAN_INTERVAL] == 120
    assert entry.options[CONF_THRESHOLD_MS] == 2000
