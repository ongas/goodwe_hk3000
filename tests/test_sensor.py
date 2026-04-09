"""Tests for HK3000 status sensor classes."""

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from goodwe_hk3000.coordinator import GwhkDataManager
from goodwe_hk3000.sensor import (
    GwhkConnectionStatusSensor,
    GwhkLastUpdateSensor,
    GwhkPacketCountSensor,
    GwhkRelayCountSensor,
)


def _make_entry(cloud_relay: bool = False) -> MagicMock:
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.data = {"cloud_relay": cloud_relay}
    entry.options = {}
    return entry


class TestConnectionStatusSensor(unittest.TestCase):
    """Tests for GwhkConnectionStatusSensor."""

    def test_disconnected_by_default(self):
        manager = GwhkDataManager()
        sensor = GwhkConnectionStatusSensor(manager, _make_entry())
        self.assertEqual(sensor.native_value, "Disconnected")

    def test_connected_when_manager_connected(self):
        manager = GwhkDataManager()
        manager.set_connected(True)
        sensor = GwhkConnectionStatusSensor(manager, _make_entry())
        self.assertEqual(sensor.native_value, "Connected")

    def test_disconnected_after_disconnect(self):
        manager = GwhkDataManager()
        manager.set_connected(True)
        manager.set_connected(False)
        sensor = GwhkConnectionStatusSensor(manager, _make_entry())
        self.assertEqual(sensor.native_value, "Disconnected")

    def test_icon_changes_with_state(self):
        manager = GwhkDataManager()
        sensor = GwhkConnectionStatusSensor(manager, _make_entry())
        self.assertEqual(sensor.icon, "mdi:lan-disconnect")
        manager.set_connected(True)
        self.assertEqual(sensor.icon, "mdi:lan-connect")

    def test_unique_id(self):
        sensor = GwhkConnectionStatusSensor(GwhkDataManager(), _make_entry())
        self.assertEqual(sensor._attr_unique_id, "test_entry_connection_status")


class TestLastUpdateSensor(unittest.TestCase):
    """Tests for GwhkLastUpdateSensor."""

    def test_none_before_first_packet(self):
        manager = GwhkDataManager()
        sensor = GwhkLastUpdateSensor(manager, _make_entry())
        self.assertIsNone(sensor.native_value)

    def test_returns_last_packet_time(self):
        manager = GwhkDataManager()
        manager.update({"power_export_w": 0})
        sensor = GwhkLastUpdateSensor(manager, _make_entry())
        self.assertIsNotNone(sensor.native_value)
        self.assertEqual(sensor.native_value.tzinfo, timezone.utc)

    def test_unique_id(self):
        sensor = GwhkLastUpdateSensor(GwhkDataManager(), _make_entry())
        self.assertEqual(sensor._attr_unique_id, "test_entry_last_update")


class TestPacketCountSensor(unittest.TestCase):
    """Tests for GwhkPacketCountSensor."""

    def test_zero_before_any_packets(self):
        manager = GwhkDataManager()
        sensor = GwhkPacketCountSensor(manager, _make_entry())
        self.assertEqual(sensor.native_value, 0)

    def test_increments_with_updates(self):
        manager = GwhkDataManager()
        sensor = GwhkPacketCountSensor(manager, _make_entry())
        manager.update({"power_export_w": 100})
        manager.update({"power_export_w": 200})
        self.assertEqual(sensor.native_value, 2)

    def test_unit_of_measurement(self):
        sensor = GwhkPacketCountSensor(GwhkDataManager(), _make_entry())
        self.assertEqual(sensor._attr_native_unit_of_measurement, "readings")

    def test_unique_id(self):
        sensor = GwhkPacketCountSensor(GwhkDataManager(), _make_entry())
        self.assertEqual(sensor._attr_unique_id, "test_entry_packets_today")


class TestRelayCountSensor(unittest.TestCase):
    """Tests for GwhkRelayCountSensor."""

    def test_zero_before_any_relays(self):
        manager = GwhkDataManager()
        sensor = GwhkRelayCountSensor(manager, _make_entry(cloud_relay=True))
        self.assertEqual(sensor.native_value, 0)

    def test_increments_with_record_relay(self):
        manager = GwhkDataManager()
        sensor = GwhkRelayCountSensor(manager, _make_entry(cloud_relay=True))
        manager.record_relay()
        manager.record_relay()
        manager.record_relay()
        self.assertEqual(sensor.native_value, 3)

    def test_unit_of_measurement(self):
        sensor = GwhkRelayCountSensor(GwhkDataManager(), _make_entry(cloud_relay=True))
        self.assertEqual(sensor._attr_native_unit_of_measurement, "syncs")

    def test_unique_id(self):
        sensor = GwhkRelayCountSensor(GwhkDataManager(), _make_entry(cloud_relay=True))
        self.assertEqual(sensor._attr_unique_id, "test_entry_relay_count_today")


if __name__ == "__main__":
    unittest.main()
