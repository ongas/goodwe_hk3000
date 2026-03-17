"""The GWHK3000 integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

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

    # Disable SEMS integration entities that are now superseded by gwhk3000,
    # so they don't create duplicate data on a fresh install.
    _disable_superseded_sems_entities(hass)

    return True


# Entities from the SEMS custom integration that are fully covered by gwhk3000.
# Marked disabled-by-user automatically so they don't show up as duplicates.
_SEMS_SUPERSEDED_ENTITIES = {
    "sensor.homekit_homekit_pv",  # → gwhk3000_smart_meter_pv_power
    "sensor.homekit_homekit_grid",  # → gwhk3000_smart_meter_grid_power
    "sensor.homekit_homekit_load",  # → sensor.corrected_load (template)
    "sensor.homekit_homekit_93000hku22b50003",  # legacy load duplicate
    "sensor.homekit_homekit_load_status",  # derivable from grid_power sign
    "sensor.homekit_homekit_battery",  # always 0 — no battery
    "sensor.homekit_homekit_generator",  # always 0 — no generator
    "sensor.homekit_homekit_state_of_charge",  # unavailable — no battery
    "sensor.homekit_93000hku22b50003_export",  # incremental charts kWh
    "sensor.homekit_93000hku22b50003_import",  # incremental charts kWh
}


def _disable_superseded_sems_entities(hass: HomeAssistant) -> None:
    """Disable SEMS entities that duplicate gwhk3000 data, if they exist."""
    registry = er.async_get(hass)
    for entity_id in _SEMS_SUPERSEDED_ENTITIES:
        entry = registry.async_get(entity_id)
        if entry is not None and entry.disabled_by is None:
            registry.async_update_entity(
                entity_id, disabled_by=er.RegistryEntryDisabler.USER
            )
            _LOGGER.info("gwhk3000: disabled superseded SEMS entity %s", entity_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a GWHK3000 config entry."""
    server: GwhkTcpServer = hass.data[DOMAIN].pop(f"{entry.entry_id}_server", None)
    if server:
        await server.stop()

    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unloaded
