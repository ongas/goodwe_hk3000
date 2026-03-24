"""HK3000 data coordinator: passive POSTGW meter listener."""

from __future__ import annotations

import asyncio
import logging
import struct
import time
from collections.abc import Callable

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

_LOGGER = logging.getLogger(__name__)

POSTGW_MAGIC = b"POSTGW"
_AES_KEY = bytes([0xFF] * 16)


class GwhkDataManager:
    """Holds the most recent decoded meter readings and notifies sensors."""

    def __init__(self) -> None:
        self._data: dict = {}
        self._listeners: list[Callable[[], None]] = []

    @property
    def data(self) -> dict:
        """Return latest readings (may be empty before first packet)."""
        return self._data

    def register_listener(self, callback: Callable[[], None]) -> None:
        """Register a callback to invoke when new data arrives."""
        self._listeners.append(callback)

    def unregister_listener(self, callback: Callable[[], None]) -> None:
        """Unregister a previously registered callback."""
        self._listeners.remove(callback)

    def update(self, values: dict) -> None:
        """Update stored readings and notify all registered listeners."""
        self._data = values
        for callback in list(self._listeners):
            callback()


# -- Packet parsing --------------------------------------------------------


_SM_PKT_LEN = 166
_SM_IV_START = 30
_SM_CT_START = 52
_SM_CT_END = 164
_SM_PT_TYPE_BYTE = 0x04

_SM_OFF_ENERGY_IMPORT = 31
_SM_OFF_ENERGY_EXPORT = 37
_SM_OFF_ENERGY_GEN = 43
_SM_OFF_VOLTAGE_L1 = 57
_SM_OFF_VOLTAGE_L2 = 59
_SM_OFF_VOLTAGE_L3 = 61
_SM_OFF_POWER_L1 = 75
_SM_OFF_POWER_L2 = 79
_SM_OFF_POWER_L3 = 83
_SM_OFF_POWER_TOTAL = 87


def _parse_server_mode_packet(raw: bytes) -> dict | None:
    """Decrypt and parse a POSTGW meter data packet.

    Returns a dict of sensor readings, or None on validation/decryption failure.
    """
    if len(raw) < _SM_PKT_LEN or not raw.startswith(POSTGW_MAGIC):
        return None

    iv = raw[_SM_IV_START : _SM_IV_START + 16]
    ciphertext = raw[_SM_CT_START:_SM_CT_END]
    if len(ciphertext) != (_SM_CT_END - _SM_CT_START):
        return None

    try:
        cipher = Cipher(algorithms.AES(_AES_KEY), modes.CBC(iv))
        plaintext = cipher.decryptor().update(ciphertext)
    except Exception:  # pylint: disable=broad-except
        _LOGGER.debug("AES decryption failed", exc_info=True)
        return None

    if len(plaintext) < 92 or plaintext[0] != _SM_PT_TYPE_BYTE:
        _LOGGER.debug(
            "Packet type mismatch: expected 0x%02x, got 0x%02x",
            _SM_PT_TYPE_BYTE,
            plaintext[0] if plaintext else 0xFF,
        )
        return None

    energy_import = struct.unpack_from(">I", plaintext, _SM_OFF_ENERGY_IMPORT)[0]
    energy_export = struct.unpack_from(">I", plaintext, _SM_OFF_ENERGY_EXPORT)[0]
    energy_gen = struct.unpack_from(">I", plaintext, _SM_OFF_ENERGY_GEN)[0]
    voltage_l1 = struct.unpack_from(">H", plaintext, _SM_OFF_VOLTAGE_L1)[0]
    voltage_l2 = struct.unpack_from(">H", plaintext, _SM_OFF_VOLTAGE_L2)[0]
    voltage_l3 = struct.unpack_from(">H", plaintext, _SM_OFF_VOLTAGE_L3)[0]
    power_l1 = struct.unpack_from(">i", plaintext, _SM_OFF_POWER_L1)[0]
    power_l2 = struct.unpack_from(">i", plaintext, _SM_OFF_POWER_L2)[0]
    power_l3 = struct.unpack_from(">i", plaintext, _SM_OFF_POWER_L3)[0]
    total_power = struct.unpack_from(">i", plaintext, _SM_OFF_POWER_TOTAL)[0]

    return {
        "energy_import_kwh": round(energy_import * 0.01, 2),
        "energy_export_kwh": round(energy_export * 0.01, 2),
        "energy_generation_kwh": round(energy_gen * 0.01, 2),
        "voltage_l1_v": round(voltage_l1 * 0.1, 1),
        "voltage_l2_v": round(voltage_l2 * 0.1, 1),
        "voltage_l3_v": round(voltage_l3 * 0.1, 1),
        "power_l1_w": power_l1,
        "power_l2_w": power_l2,
        "power_l3_w": power_l3,
        "power_export_w": total_power,
    }


# -- TCP client (server mode, POSTGW passive listener) ------------------------


class GwhkTcpClient:
    """Asyncio TCP client that connects to the HF-A21 server port and passively
    receives POSTGW meter-data packets pushed by the meter."""

    # Reconnect delay after connection loss (seconds).
    # Keep short so we reconnect quickly after the meter closes the TCP session
    # (HF-A21 factory TCP timeout may be as short as a few seconds).
    _RECONNECT_DELAY = 2

    # Minimum seconds between consecutive cloud relay forwards (mimic 60s push)
    _CLOUD_RELAY_INTERVAL = 60

    def __init__(
        self,
        manager: GwhkDataManager,
        meter_host: str,
        meter_port: int,
        cloud_relay: bool = False,
        cloud_host: str = "",
        cloud_port: int = 20001,
        cloud_username: str = "",
        cloud_password: str = "",
    ) -> None:
        self._manager = manager
        self._meter_host = meter_host
        self._meter_port = meter_port
        self._cloud_relay = cloud_relay
        self._cloud_host = cloud_host
        self._cloud_port = cloud_port
        self._cloud_username = cloud_username
        self._cloud_password = cloud_password
        self._running = False
        self._last_relay_time: float = 0.0

    async def start(self) -> None:
        """Start the passive listener loop."""
        self._running = True
        _LOGGER.info(
            "HK3000 server-mode listener connecting to %s:%d",
            self._meter_host,
            self._meter_port,
        )
        asyncio.create_task(self._listen_loop())

    async def stop(self) -> None:
        """Stop the listener."""
        self._running = False
        _LOGGER.info("HK3000 server-mode listener stopped")

    async def _listen_loop(self) -> None:
        """Outer loop: reconnect whenever the connection drops."""
        while self._running:
            try:
                await self._connect_and_receive()
            except Exception:  # pylint: disable=broad-except
                _LOGGER.debug("Server-mode listener error", exc_info=True)

            if self._running:
                _LOGGER.info(
                    "HK3000 reconnecting to %s:%d in %ds",
                    self._meter_host,
                    self._meter_port,
                    self._RECONNECT_DELAY,
                )
                await asyncio.sleep(self._RECONNECT_DELAY)

    async def _connect_and_receive(self) -> None:
        """Connect once and receive packets until the connection closes."""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self._meter_host, self._meter_port),
                timeout=10,
            )
        except asyncio.TimeoutError:
            _LOGGER.warning(
                "Timeout connecting to meter %s:%d",
                self._meter_host,
                self._meter_port,
            )
            return
        except OSError as exc:
            _LOGGER.warning(
                "Cannot connect to meter %s:%d: %s",
                self._meter_host,
                self._meter_port,
                exc,
            )
            return

        _LOGGER.info(
            "Connected to meter %s:%d — waiting for POSTGW packets",
            self._meter_host,
            self._meter_port,
        )
        buf = b""
        try:
            while self._running:
                try:
                    chunk = await asyncio.wait_for(reader.read(512), timeout=660)
                except asyncio.TimeoutError:
                    _LOGGER.debug("No data from meter in 660 s — reconnecting")
                    break
                if not chunk:
                    _LOGGER.debug("Connection closed by meter")
                    break

                buf += chunk

                # Parse all complete packets from the buffer
                while len(buf) >= _SM_PKT_LEN:
                    # Re-sync to POSTGW magic if needed
                    magic_pos = buf.find(POSTGW_MAGIC)
                    if magic_pos < 0:
                        buf = b""
                        break
                    if magic_pos > 0:
                        _LOGGER.debug("Discarding %d pre-sync bytes", magic_pos)
                        buf = buf[magic_pos:]

                    if len(buf) < _SM_PKT_LEN:
                        break

                    pkt = buf[:_SM_PKT_LEN]
                    buf = buf[_SM_PKT_LEN:]

                    values = _parse_server_mode_packet(pkt)
                    if values is not None:
                        _LOGGER.info(
                            "Server-mode update: "
                            "import=%.2fkWh  export=%.2fkWh  total_power=%dW",
                            values["energy_import_kwh"],
                            values["energy_export_kwh"],
                            values["power_export_w"],
                        )
                        self._manager.update(values)
                        await self._maybe_relay_to_cloud(pkt)
                    else:
                        _LOGGER.debug(
                            "Could not parse POSTGW packet: %s", pkt[:20].hex()
                        )
        finally:
            writer.close()
            await writer.wait_closed()

    async def _maybe_relay_to_cloud(self, pkt: bytes) -> None:
        """Forward a raw POSTGW packet to the GoodWe cloud at most once per 60 s."""
        if not self._cloud_relay or not self._cloud_host:
            return

        now = time.monotonic()
        if now - self._last_relay_time < self._CLOUD_RELAY_INTERVAL:
            _LOGGER.debug(
                "Cloud relay skipped — %.0fs since last forward (interval %ds)",
                now - self._last_relay_time,
                self._CLOUD_RELAY_INTERVAL,
            )
            return

        try:
            relay_reader, relay_writer = await asyncio.wait_for(
                asyncio.open_connection(self._cloud_host, self._cloud_port),
                timeout=5,
            )
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.warning(
                "Cloud relay connect failed (%s:%d): %s",
                self._cloud_host,
                self._cloud_port,
                exc,
            )
            return

        try:
            relay_writer.write(pkt)
            await relay_writer.drain()
            self._last_relay_time = time.monotonic()
            _LOGGER.debug(
                "Cloud relay: forwarded %d bytes to %s:%d",
                len(pkt),
                self._cloud_host,
                self._cloud_port,
            )
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.warning("Cloud relay write failed: %s", exc)
        finally:
            relay_writer.close()
            await relay_writer.wait_closed()
