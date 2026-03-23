"""The HK3000 integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

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
    DOMAIN,
    MODE_CLIENT,
    MODE_SERVER,
)
from .coordinator import GwhkDataManager, GwhkTcpClient, GwhkTcpServer

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HK3000 from a config entry."""
    _LOGGER.info("HK3000 setup_entry called for entry %s", entry.entry_id)
    hass.data.setdefault(DOMAIN, {})

    manager = GwhkDataManager()
    mode = entry.data.get(CONF_MODE, MODE_CLIENT)
    _LOGGER.info("HK3000 mode=%s", mode)

    if mode == MODE_CLIENT:
        return await _setup_client_mode(hass, entry, manager)
    else:
        return await _setup_server_mode(hass, entry, manager)


async def _setup_client_mode(
    hass: HomeAssistant, entry: ConfigEntry, manager: GwhkDataManager
) -> bool:
    """Set up client mode (meter connects to HA)."""
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
        _LOGGER.exception("Failed to start HK3000 TCP server on port %d", listen_port)
        return False

    hass.data[DOMAIN][entry.entry_id] = manager
    hass.data[DOMAIN][f"{entry.entry_id}_server"] = server

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def _setup_server_mode(
    hass: HomeAssistant, entry: ConfigEntry, manager: GwhkDataManager
) -> bool:
    """Set up server mode (HA polls meter)."""
    meter_host = entry.data.get(CONF_METER_HOST)
    poll_interval = entry.data.get(CONF_POLL_INTERVAL, 15)

    if not meter_host:
        _LOGGER.error("Meter host not configured for server mode")
        return False

    client = GwhkTcpClient(
        manager=manager,
        meter_host=meter_host,
        meter_port=20001,
        poll_interval=poll_interval,
    )

    try:
        await client.start()
    except Exception:
        _LOGGER.exception("Failed to start HK3000 TCP client")
        return False

    hass.data[DOMAIN][entry.entry_id] = manager
    hass.data[DOMAIN][f"{entry.entry_id}_client"] = client

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a HK3000 config entry."""
    mode = hass.data[DOMAIN].get(f"{entry.entry_id}_mode", MODE_CLIENT)

    # Stop server or client
    server: GwhkTcpServer | None = hass.data[DOMAIN].pop(f"{entry.entry_id}_server", None)
    if server:
        await server.stop()

    client: GwhkTcpClient | None = hass.data[DOMAIN].pop(f"{entry.entry_id}_client", None)
    if client:
        await client.stop()

    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unloaded
