"""Sensor platform for the HK3000 integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import GwhkDataManager


@dataclass(frozen=True, kw_only=True)
class GwhkSensorDescription(SensorEntityDescription):
    """Describes a HK3000 sensor."""

    data_key: str


SENSORS: tuple[GwhkSensorDescription, ...] = (
    GwhkSensorDescription(
        key="grid_power",
        data_key="power_export_w",
        name="Grid Power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        icon="mdi:transmission-tower",
    ),
    GwhkSensorDescription(
        key="energy_export_total",
        data_key="energy_export_kwh",
        name="Total Energy Exported",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:transmission-tower-export",
    ),
    GwhkSensorDescription(
        key="energy_generation_total",
        data_key="energy_generation_kwh",
        name="Total Energy Generated",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:solar-power-variant",
    ),
    GwhkSensorDescription(
        key="energy_import_total",
        data_key="energy_import_kwh",
        name="Total Energy Imported",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:transmission-tower-import",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HK3000 sensors from a config entry."""
    manager: GwhkDataManager = hass.data[DOMAIN][entry.entry_id]
    meter_sensors = [GwhkSensor(manager, description, entry) for description in SENSORS]
    status_sensors = [
        GwhkConnectionStatusSensor(manager, entry),
        GwhkLastUpdateSensor(manager, entry),
        GwhkPacketCountSensor(manager, entry),
    ]
    async_add_entities(meter_sensors + status_sensors)


class GwhkSensor(SensorEntity):
    """Represents a single HK3000 meter sensor."""

    entity_description: GwhkSensorDescription
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(
        self,
        manager: GwhkDataManager,
        description: GwhkSensorDescription,
        entry: ConfigEntry,
    ) -> None:
        self.entity_description = description
        self._manager = manager
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="GoodWe HK3000 Smart Meter",
            manufacturer="GoodWe",
            model="HK3000",
        )

    @property
    def native_value(self) -> float | int | None:
        """Return the current sensor value."""
        return self._manager.data.get(self.entity_description.data_key)

    @callback
    def _handle_update(self) -> None:
        """Handle new data from the manager."""
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Register for manager updates when entity is added."""
        self._manager.register_listener(self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister when entity is removed."""
        self._manager.unregister_listener(self._handle_update)


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="GoodWe HK3000 Smart Meter",
        manufacturer="GoodWe",
        model="HK3000",
    )


class GwhkConnectionStatusSensor(SensorEntity):
    """Reports whether the integration is connected to the meter."""

    _attr_has_entity_name = True
    _attr_name = "Connection Status"
    _attr_should_poll = False

    def __init__(self, manager: GwhkDataManager, entry: ConfigEntry) -> None:
        self._manager = manager
        self._attr_unique_id = f"{entry.entry_id}_connection_status"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> str:
        return "Connected" if self._manager.connected else "Disconnected"

    @property
    def icon(self) -> str:
        return "mdi:lan-connect" if self._manager.connected else "mdi:lan-disconnect"

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        self._manager.register_listener(self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        self._manager.unregister_listener(self._handle_update)


class GwhkLastUpdateSensor(SensorEntity):
    """Reports the timestamp of the last received meter packet."""

    _attr_has_entity_name = True
    _attr_name = "Last Update"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_should_poll = False

    def __init__(self, manager: GwhkDataManager, entry: ConfigEntry) -> None:
        self._manager = manager
        self._attr_unique_id = f"{entry.entry_id}_last_update"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> datetime | None:
        return self._manager.last_packet_time

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        self._manager.register_listener(self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        self._manager.unregister_listener(self._handle_update)


class GwhkPacketCountSensor(SensorEntity):
    """Reports the number of meter packets received today."""

    _attr_has_entity_name = True
    _attr_name = "Packets Today"
    _attr_icon = "mdi:counter"
    _attr_native_unit_of_measurement = "packets"
    _attr_should_poll = False

    def __init__(self, manager: GwhkDataManager, entry: ConfigEntry) -> None:
        self._manager = manager
        self._attr_unique_id = f"{entry.entry_id}_packets_today"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> int:
        return self._manager.packet_count_today

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        self._manager.register_listener(self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        self._manager.unregister_listener(self._handle_update)
