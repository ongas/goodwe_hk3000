"""Config flow for the HK3000 integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_CLOUD_HOST,
    CONF_CLOUD_PASSWORD,
    CONF_CLOUD_PORT,
    CONF_CLOUD_RELAY,
    CONF_CLOUD_USERNAME,
    CONF_METER_HOST,
    CONF_METER_PORT,
    CONF_UPDATE_INTERVAL,
    DEFAULT_CLOUD_HOST,
    DEFAULT_CLOUD_PORT,
    DEFAULT_METER_HOST,
    DEFAULT_METER_PORT,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)

STEP_SERVER_SCHEMA = vol.Schema(
    {
        vol.Required(
            CONF_METER_HOST, default=DEFAULT_METER_HOST
        ): selector.TextSelector(),
        vol.Required(
            CONF_METER_PORT, default=DEFAULT_METER_PORT
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1, max=65535, mode=selector.NumberSelectorMode.BOX
            )
        ),
        vol.Required(CONF_CLOUD_RELAY, default=False): selector.BooleanSelector(),
        vol.Required(
            CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=5,
                max=3600,
                mode=selector.NumberSelectorMode.BOX,
                unit_of_measurement="s",
            )
        ),
    }
)

STEP_CLOUD_CREDENTIALS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CLOUD_USERNAME): selector.TextSelector(),
        vol.Required(CONF_CLOUD_PASSWORD): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
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

    def __init__(self) -> None:
        """Initialise the config flow."""
        self._server_data: dict = {}

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Start directly with server mode configuration."""
        return await self.async_step_server(user_input)

    async def async_step_server(self, user_input: dict | None = None) -> FlowResult:
        """Handle server mode configuration — meter IP, port, relay toggle, and update interval."""
        if user_input is not None:
            self._server_data = {
                CONF_METER_HOST: user_input[CONF_METER_HOST],
                CONF_METER_PORT: int(user_input[CONF_METER_PORT]),
                CONF_CLOUD_RELAY: user_input[CONF_CLOUD_RELAY],
                CONF_UPDATE_INTERVAL: int(user_input[CONF_UPDATE_INTERVAL]),
            }
            if user_input[CONF_CLOUD_RELAY]:
                return await self.async_step_cloud_credentials()
            return self.async_create_entry(
                title=f"HK3000 @ {user_input[CONF_METER_HOST]}",
                data=self._server_data,
            )

        return self.async_show_form(
            step_id="server",
            data_schema=STEP_SERVER_SCHEMA,
        )

    async def async_step_cloud_credentials(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Handle GoodWe cloud credentials when relay is enabled."""
        if user_input is not None:
            self._server_data.update(
                {
                    CONF_CLOUD_USERNAME: user_input[CONF_CLOUD_USERNAME],
                    CONF_CLOUD_PASSWORD: user_input[CONF_CLOUD_PASSWORD],
                    CONF_CLOUD_HOST: user_input[CONF_CLOUD_HOST],
                    CONF_CLOUD_PORT: int(user_input[CONF_CLOUD_PORT]),
                }
            )
            return self.async_create_entry(
                title=f"HK3000 @ {self._server_data[CONF_METER_HOST]}",
                data=self._server_data,
            )

        return self.async_show_form(
            step_id="cloud_credentials",
            data_schema=STEP_CLOUD_CREDENTIALS_SCHEMA,
        )
