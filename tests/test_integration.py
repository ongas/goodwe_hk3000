"""Tests for the HK3000 integration."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from goodwe_hk3000.const import DOMAIN


class TestIntegrationSetup(unittest.TestCase):
    """Test integration setup."""

    def test_imports_all_constants(self):
        """Test that __init__.py can import all required constants.
        
        This would catch any missing constant imports.
        """
        import goodwe_hk3000 as init_module

        # Verify key components are available
        self.assertTrue(hasattr(init_module, "async_setup_entry"))
        self.assertTrue(hasattr(init_module, "async_unload_entry"))
        self.assertTrue(hasattr(init_module, "PLATFORMS"))

    def test_const_module_structure(self):
        """Test that const module has all required constants."""
        import goodwe_hk3000.const as const

        required_consts = [
            "DOMAIN",
            "CONF_METER_HOST",
            "CONF_METER_PORT",
            "CONF_CLOUD_RELAY",
            "CONF_CLOUD_HOST",
            "CONF_CLOUD_PORT",
            "DEFAULT_CLOUD_HOST",
            "DEFAULT_CLOUD_PORT",
            "DEFAULT_METER_HOST",
            "DEFAULT_METER_PORT",
        ]

        for const_name in required_consts:
            self.assertTrue(
                hasattr(const, const_name),
                f"const.py missing required constant: {const_name}",
            )

    def test_no_update_interval_in_const(self):
        """Verify update_interval constants were removed.
        
        This prevents regression of the config flow error.
        """
        import goodwe_hk3000.const as const

        self.assertFalse(
            hasattr(const, "CONF_UPDATE_INTERVAL"),
            "CONF_UPDATE_INTERVAL should not exist in const",
        )
        self.assertFalse(
            hasattr(const, "DEFAULT_UPDATE_INTERVAL"),
            "DEFAULT_UPDATE_INTERVAL should not exist in const",
        )

    def test_coordinator_imports(self):
        """Test that coordinator module imports correctly."""
        import goodwe_hk3000.coordinator as coordinator

        # Verify key classes exist
        self.assertTrue(hasattr(coordinator, "GwhkDataManager"))
        self.assertTrue(hasattr(coordinator, "GwhkTcpClient"))
        self.assertTrue(hasattr(coordinator, "_parse_server_mode_packet"))

        # Verify unused classes were removed
        self.assertFalse(
            hasattr(coordinator, "GwhkTcpServer"),
            "GwhkTcpServer should be removed (replaced by GwhkTcpClient)",
        )
        self.assertFalse(
            hasattr(coordinator, "_decrypt_meter_payload"),
            "_decrypt_meter_payload should be removed (replaced by _parse_server_mode_packet)",
        )

    async def test_async_setup_entry_missing_host(self):
        """Test that setup fails gracefully without meter_host."""
        import goodwe_hk3000 as init_module

        hass = MagicMock()
        hass.data = {DOMAIN: {}}

        entry = MagicMock()
        entry.entry_id = "test_entry"
        entry.options = {}
        entry.data = {}  # Missing meter_host

        result = await init_module.async_setup_entry(hass, entry)

        self.assertFalse(result, "Setup should fail without meter_host")

    async def test_async_setup_entry_valid_config(self):
        """Test setup with valid configuration."""
        import goodwe_hk3000 as init_module

        hass = MagicMock()
        hass.data = {DOMAIN: {}}
        hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=True)

        entry = MagicMock()
        entry.entry_id = "test_entry"
        entry.options = {}
        entry.data = {
            "meter_host": "192.168.1.100",
            "meter_port": 20001,
            "cloud_relay": False,
        }
        entry.async_on_unload = MagicMock()

        with patch("goodwe_hk3000.GwhkTcpClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            result = await init_module.async_setup_entry(hass, entry)

            # Client should have been created and started
            mock_client.start.assert_called_once()


if __name__ == "__main__":
    unittest.main()
