"""The GWHK3000 integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_CLOUD_HOST,
    CONF_CLOUD_PORT,
    CONF_LISTEN_PORT,
    DEFAULT_CLOUD_HOST,
    DEFAULT_CLOUD_PORT,
    DEFAULT_LISTEN_PORT,
    DOMAIN,
)
from .coordinator import GwhkDataManager, GwhkTcpServer

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up GWHK3000 from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    manager = GwhkDataManager()

    listen_port = entry.data.get(CONF_LISTEN_PORT, DEFAULT_LISTEN_PORT)
    cloud_host = entry.data.get(CONF_CLOUD_HOST, DEFAULT_CLOUD_HOST)
    cloud_port = entry.data.get(CONF_CLOUD_PORT, DEFAULT_CLOUD_PORT)

    server = GwhkTcpServer(
        manager=manager,
        listen_host="0.0.0.0",
        listen_port=listen_port,
        cloud_host=cloud_host,
        cloud_port=cloud_port,
    )

    try:
        await server.start()
    except OSError:
        _LOGGER.exception("Failed to start GWHK3000 TCP server on port %d", listen_port)
        return False

    hass.data[DOMAIN][entry.entry_id] = manager
    hass.data[DOMAIN][f"{entry.entry_id}_server"] = server

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a GWHK3000 config entry."""
    server: GwhkTcpServer = hass.data[DOMAIN].pop(f"{entry.entry_id}_server", None)
    if server:
        await server.stop()

    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unloaded
