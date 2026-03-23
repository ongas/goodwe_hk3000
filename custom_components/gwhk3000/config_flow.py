"""Config flow for the HK3000 integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_CLOUD_HOST,
    CONF_CLOUD_PORT,
    CONF_LISTEN_PORT,
    DEFAULT_CLOUD_HOST,
    DEFAULT_CLOUD_PORT,
    DEFAULT_LISTEN_PORT,
    DOMAIN,
)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(
            CONF_LISTEN_PORT, default=DEFAULT_LISTEN_PORT
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1, max=65535, mode=selector.NumberSelectorMode.BOX
            )
        ),
        vol.Required(
            CONF_CLOUD_HOST, default=DEFAULT_CLOUD_HOST
        ): selector.TextSelector(),
        vol.Required(
            CONF_CLOUD_PORT, default=DEFAULT_CLOUD_PORT
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1, max=65535, mode=selector.NumberSelectorMode.BOX
            )
        ),
    }
)


class GwhkConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HK3000."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> ConfigFlowResult:
        """Handle the initial configuration step."""
        if user_input is not None:
            return self.async_create_entry(
                title=f"HK3000 (port {int(user_input[CONF_LISTEN_PORT])})",
                data={
                    CONF_LISTEN_PORT: int(user_input[CONF_LISTEN_PORT]),
                    CONF_CLOUD_HOST: user_input[CONF_CLOUD_HOST],
                    CONF_CLOUD_PORT: int(user_input[CONF_CLOUD_PORT]),
                },
            )

        return self.async_show_form(step_id="user", data_schema=STEP_USER_SCHEMA)
