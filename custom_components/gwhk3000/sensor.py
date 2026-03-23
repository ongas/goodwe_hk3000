"""Sensor platform for the GWHK3000 integration."""

from __future__ import annotations

from dataclasses import dataclass

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
    """Describes a GWHK3000 sensor."""

    data_key: str


SENSORS: tuple[GwhkSensorDescription, ...] = (
    GwhkSensorDescription(
        key="grid_power",
        data_key="grid_power_w",
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
    """Set up GWHK3000 sensors from a config entry."""
    manager: GwhkDataManager = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        GwhkSensor(manager, description, entry) for description in SENSORS
    )


class GwhkSensor(SensorEntity):
    """Represents a single GWHK3000 meter sensor."""

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
