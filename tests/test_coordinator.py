"""Tests for coordinator module."""

import unittest

from goodwe_hk3000.coordinator import (
    _parse_server_mode_packet,
    GwhkDataManager,
)


class TestPacketParsing(unittest.TestCase):
    """Test POSTGW packet decryption and parsing."""

    def test_parse_invalid_packet_too_short(self):
        """Test that packets shorter than 166 bytes return None."""
        short_packet = b"POSTGW" + b"\x00" * 100
        result = _parse_server_mode_packet(short_packet)
        self.assertIsNone(result, "Short packet should return None")

    def test_parse_invalid_packet_no_magic(self):
        """Test that packets without POSTGW magic return None."""
        no_magic = b"\x00" * 166
        result = _parse_server_mode_packet(no_magic)
        self.assertIsNone(result, "Packet without POSTGW magic should return None")

    def test_parse_invalid_packet_wrong_type(self):
        """Test that packets with wrong packet type byte return None."""
        valid_packet_hex = (
            "504f5354475700000000030400003933303030484b553232423530303033"
            "323032353033323531323030303030000000"
            "323032353033323531323030303030000000"
            "04000000000000ec000000000000000000000000000000004b0000000000000000"
            "00000000000000000000000000000018600000000000005a000000f6000000f9"
            "00000001000000010000000100000001"
        )
        packet = bytearray.fromhex(valid_packet_hex)

        # Modify the first byte of ciphertext (at offset 52) to simulate wrong plaintext
        # This would produce a plaintext that doesn't start with 0x04
        packet[52] = 0xFF

        result = _parse_server_mode_packet(bytes(packet))
        # With wrong type byte, decryption verification will fail
        self.assertIsNone(result, "Packet with wrong type should return None")


class TestDataManager(unittest.TestCase):
    """Test GwhkDataManager."""

    def test_data_manager_init(self):
        """Test DataManager initialization."""
        manager = GwhkDataManager()
        self.assertEqual(manager.data, {}, "Data should be empty on init")

    def test_data_manager_update(self):
        """Test updating manager data."""
        manager = GwhkDataManager()
        test_data = {
            "energy_import_kwh": 100.5,
            "power_export_w": 500,
        }

        manager.update(test_data)
        self.assertEqual(manager.data, test_data, "Data should be updated")

    def test_data_manager_listeners(self):
        """Test registering and triggering listeners."""
        manager = GwhkDataManager()
        callback_count = 0

        def test_callback():
            nonlocal callback_count
            callback_count += 1

        manager.register_listener(test_callback)
        manager.update({"test": "data"})

        self.assertEqual(callback_count, 1, "Callback should be called once")

        manager.unregister_listener(test_callback)
        manager.update({"test": "data2"})

        self.assertEqual(
            callback_count, 1, "Callback should not be called after unregister"
        )


if __name__ == "__main__":
    unittest.main()
