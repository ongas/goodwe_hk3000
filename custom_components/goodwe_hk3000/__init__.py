"""The HK3000 integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

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
    DEFAULT_METER_PORT,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from .coordinator import GwhkDataManager, GwhkTcpClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HK3000 from a config entry."""
    _LOGGER.info("HK3000 setup_entry called for entry %s", entry.entry_id)
    hass.data.setdefault(DOMAIN, {})

    manager = GwhkDataManager()

    meter_host = entry.data.get(CONF_METER_HOST)
    if not meter_host:
        _LOGGER.error("Meter host not configured")
        return False

    meter_port = entry.data.get(CONF_METER_PORT, DEFAULT_METER_PORT)
    cloud_relay = entry.data.get(CONF_CLOUD_RELAY, False)
    cloud_host = entry.data.get(CONF_CLOUD_HOST, DEFAULT_CLOUD_HOST)
    cloud_port = entry.data.get(CONF_CLOUD_PORT, DEFAULT_CLOUD_PORT)
    cloud_username = entry.data.get(CONF_CLOUD_USERNAME, "")
    cloud_password = entry.data.get(CONF_CLOUD_PASSWORD, "")
    update_interval = entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)

    _LOGGER.info(
        "HK3000 server-mode: meter=%s:%d  cloud_relay=%s  update_interval=%ds",
        meter_host,
        meter_port,
        cloud_relay,
        update_interval,
    )

    client = GwhkTcpClient(
        manager=manager,
        meter_host=meter_host,
        meter_port=meter_port,
        cloud_relay=cloud_relay,
        cloud_host=cloud_host,
        cloud_port=cloud_port,
        cloud_username=cloud_username,
        cloud_password=cloud_password,
    )

    try:
        await client.start()
    except Exception:
        _LOGGER.exception("Failed to start HK3000 client")
        return False

    # Create coordinator with configurable update interval
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=manager.async_refresh,
        update_interval=timedelta(seconds=update_interval),
    )

    hass.data[DOMAIN][entry.entry_id] = coordinator
    hass.data[DOMAIN][f"{entry.entry_id}_client"] = client
    hass.data[DOMAIN][f"{entry.entry_id}_manager"] = manager

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a HK3000 config entry."""
    client: GwhkTcpClient | None = hass.data[DOMAIN].pop(
        f"{entry.entry_id}_client", None
    )
    if client:
        await client.stop()

    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unloaded
