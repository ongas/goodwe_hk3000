"""Config flow for the HK3000 integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_CLOUD_HOST,
    CONF_CLOUD_PORT,
    CONF_LISTEN_PORT,
    CONF_METER_HOST,
    CONF_MODE,
    CONF_POLL_INTERVAL,
    DEFAULT_CLOUD_HOST,
    DEFAULT_CLOUD_PORT,
    DEFAULT_LISTEN_PORT,
    DEFAULT_METER_HOST,
    DEFAULT_MODE,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    MODE_CLIENT,
    MODE_SERVER,
)

STEP_MODE_SCHEMA = vol.Schema(
    {
        vol.Required(
            CONF_MODE, default=DEFAULT_MODE
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    selector.SelectOptionDict(value=MODE_CLIENT, label="Client Mode (meter pushes data)"),
                    selector.SelectOptionDict(value=MODE_SERVER, label="Server Mode (HA polls meter)"),
                ]
            )
        ),
    }
)

STEP_CLIENT_SCHEMA = vol.Schema(
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

STEP_SERVER_SCHEMA = vol.Schema(
    {
        vol.Required(
            CONF_METER_HOST, default=DEFAULT_METER_HOST
        ): selector.TextSelector(),
        vol.Required(
            CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=5, max=300, mode=selector.NumberSelectorMode.BOX
            )
        ),
    }
)


class GwhkConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HK3000."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Handle mode selection step."""
        if user_input is not None:
            mode = user_input[CONF_MODE]
            if mode == MODE_CLIENT:
                return await self.async_step_client()
            else:
                return await self.async_step_server()

        return self.async_show_form(step_id="user", data_schema=STEP_MODE_SCHEMA)

    async def async_step_client(self, user_input: dict | None = None) -> FlowResult:
        """Handle client mode configuration."""
        if user_input is not None:
            return self.async_create_entry(
                title=f"HK3000 (client port {int(user_input[CONF_LISTEN_PORT])})",
                data={
                    CONF_MODE: MODE_CLIENT,
                    CONF_LISTEN_PORT: int(user_input[CONF_LISTEN_PORT]),
                    CONF_CLOUD_HOST: user_input[CONF_CLOUD_HOST],
                    CONF_CLOUD_PORT: int(user_input[CONF_CLOUD_PORT]),
                },
            )

        return self.async_show_form(step_id="client", data_schema=STEP_CLIENT_SCHEMA)

    async def async_step_server(self, user_input: dict | None = None) -> FlowResult:
        """Handle server mode configuration."""
        if user_input is not None:
            return self.async_create_entry(
                title=f"HK3000 (server {user_input[CONF_METER_HOST]})",
                data={
                    CONF_MODE: MODE_SERVER,
                    CONF_METER_HOST: user_input[CONF_METER_HOST],
                    CONF_POLL_INTERVAL: int(user_input[CONF_POLL_INTERVAL]),
                },
            )

        return self.async_show_form(step_id="server", data_schema=STEP_SERVER_SCHEMA)
