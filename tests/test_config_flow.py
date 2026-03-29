"""Tests for config flow."""

import unittest
from unittest.mock import AsyncMock, MagicMock

from homeassistant.data_entry_flow import FlowResult

from goodwe_hk3000.config_flow import GwhkConfigFlow
from goodwe_hk3000.const import DOMAIN


class TestConfigFlow(unittest.TestCase):
    """Test the HK3000 config flow."""

    def setUp(self):
        """Set up test fixtures."""
        self.flow = GwhkConfigFlow()
        self.flow.hass = MagicMock()

    def test_config_flow_imports(self):
        """Test that all required constants are importable."""
        from custom_components.goodwe_hk3000 import config_flow as cf

        self.assertTrue(hasattr(cf, "GwhkConfigFlow"))
        self.assertTrue(hasattr(cf, "STEP_SERVER_SCHEMA"))
        self.assertTrue(hasattr(cf, "STEP_CLOUD_SETTINGS_SCHEMA"))
        self.assertFalse(hasattr(cf, "STEP_CLOUD_CREDENTIALS_SCHEMA"), "credentials schema should be removed")

    def test_step_server_schema_fields(self):
        """Test that STEP_SERVER_SCHEMA has the correct fields."""
        from custom_components.goodwe_hk3000.config_flow import STEP_SERVER_SCHEMA

        # Get the schema keys
        required_fields = set()
        for key in STEP_SERVER_SCHEMA.schema.keys():
            required_fields.add(key.schema)

        # These are the expected fields (no update_interval)
        expected = {"meter_host", "meter_port", "cloud_relay"}
        self.assertEqual(
            required_fields, expected, "Schema should have correct fields"
        )

    def test_step_cloud_settings_schema_fields(self):
        """Test that STEP_CLOUD_SETTINGS_SCHEMA has the correct fields (no credentials)."""
        from custom_components.goodwe_hk3000.config_flow import (
            STEP_CLOUD_SETTINGS_SCHEMA,
        )

        required_fields = set()
        for key in STEP_CLOUD_SETTINGS_SCHEMA.schema.keys():
            required_fields.add(key.schema)

        expected = {"cloud_host", "cloud_port"}
        self.assertEqual(
            required_fields, expected, "Cloud schema should only have host and port — no credentials"
        )

    def test_config_flow_initialization(self):
        """Test that config flow initializes correctly."""
        flow = GwhkConfigFlow()
        self.assertEqual(flow._server_data, {})

    async def test_async_step_user(self):
        """Test async_step_user delegates to async_step_server."""
        self.flow.async_step_server = AsyncMock(return_value={"type": "form"})

        result = await self.flow.async_step_user()

        self.flow.async_step_server.assert_called_once()
        self.assertEqual(result, {"type": "form"})

    async def test_async_step_server_without_relay(self):
        """Test server step without cloud relay."""
        self.flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})

        user_input = {
            "meter_host": "192.168.1.100",
            "meter_port": 20001,
            "cloud_relay": False,
        }

        result = await self.flow.async_step_server(user_input)

        self.flow.async_create_entry.assert_called_once()
        self.assertEqual(self.flow._server_data["meter_host"], "192.168.1.100")
        self.assertFalse(self.flow._server_data["cloud_relay"])

    async def test_async_step_server_with_relay(self):
        """Test server step with cloud relay enabled advances to cloud_settings."""
        self.flow.async_step_cloud_settings = AsyncMock(
            return_value={"type": "form"}
        )

        user_input = {
            "meter_host": "192.168.1.100",
            "meter_port": 20001,
            "cloud_relay": True,
        }

        result = await self.flow.async_step_server(user_input)

        self.flow.async_step_cloud_settings.assert_called_once()

    async def test_async_step_cloud_settings(self):
        """Test cloud settings step stores host/port and creates entry."""
        self.flow._server_data = {
            "meter_host": "192.168.1.100",
            "meter_port": 20001,
            "cloud_relay": True,
        }
        self.flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})

        user_input = {
            "cloud_host": "tcp.goodwe-power.com",
            "cloud_port": 20001,
        }

        result = await self.flow.async_step_cloud_settings(user_input)

        self.flow.async_create_entry.assert_called_once()
        self.assertEqual(
            self.flow._server_data["cloud_host"], "tcp.goodwe-power.com"
        )
        self.assertNotIn("cloud_username", self.flow._server_data)
        self.assertNotIn("cloud_password", self.flow._server_data)


if __name__ == "__main__":
    unittest.main()
