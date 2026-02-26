"""Config flow for HK Citation Health Monitor."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
    OptionsFlowWithConfigEntry,
)
from homeassistant.core import callback

from .const import (
    CONF_SCAN_INTERVAL,
    CONF_THRESHOLD_MS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_THRESHOLD_MS,
    DOMAIN,
)


class HKCitationConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HK Citation."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step — no user input needed."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title="HK Citation Health Monitor",
            data={},
            options={
                CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                CONF_THRESHOLD_MS: DEFAULT_THRESHOLD_MS,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow handler."""
        return HKCitationOptionsFlow(config_entry)


class HKCitationOptionsFlow(OptionsFlowWithConfigEntry):
    """Handle options flow for HK Citation."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=self.options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): vol.All(int, vol.Range(min=60, max=3600)),
                    vol.Required(
                        CONF_THRESHOLD_MS,
                        default=self.options.get(
                            CONF_THRESHOLD_MS, DEFAULT_THRESHOLD_MS
                        ),
                    ): vol.All(int, vol.Range(min=200, max=10000)),
                }
            ),
        )
