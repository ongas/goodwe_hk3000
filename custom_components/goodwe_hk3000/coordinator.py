"""HK3000 data coordinator: TCP server, POSTGW relay and meter packet parser."""

from __future__ import annotations

import asyncio
import logging
import struct
import time
from collections.abc import Callable

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

_LOGGER = logging.getLogger(__name__)


# -- Protocol constants --------------------------------------------------------

POSTGW_MAGIC = b"POSTGW"

# Packet framing:
#   [0:6]   POSTGW magic
#   [6:8]   0x0000 (padding)
#   [8:10]  body length as uint16 BE  (value L; actual body bytes = L + 1)
#   [10:]   body (L+1 bytes)
#   [-2:]   Modbus CRC-16 (not counted in L)
# Total packet = 10 + (L+1) + 2 = 13 + L
# For L=153 → total = 166 bytes
HEADER_SIZE = 10
CRC_SIZE = 2

# Within the 112-byte decrypted OutboundMeterMetrics payload (big-endian int32):
_OFF_ENERGY_EXPORT = 7  # EnergyExportDecawattHoursTotal
_OFF_ENERGY_GEN = 13  # EnergyGenerationDecawattHoursTotal
_OFF_ENERGY_IMPORT = 31  # EnergyImportDecawattHoursTotal
_OFF_POWER_EXPORT = 75  # PowerExportWatts  (negative = importing from grid)
_OFF_POWER_GEN = 79  # PowerGenerationWatts

# AES-128-CBC key: 16 × 0xFF
_AES_KEY = bytes([0xFF] * 16)

# Expected cleartext size for a meter metrics packet
_METER_CLEARTEXT_SIZE = 112

# First byte of cleartext PacketType for meter metrics
_METER_PACKET_TYPE_BYTE = 0x04


# -- Decryption / parsing ------------------------------------------------------


def _total_packet_size(data: bytes, offset: int) -> int | None:
    """Return expected total byte length of the POSTGW packet starting at offset.

    Returns None if there are not enough bytes yet to read the length field.
    """
    if offset + HEADER_SIZE > len(data):
        return None
    (body_len,) = struct.unpack_from(">H", data, offset + 8)
    return HEADER_SIZE + body_len + 1 + CRC_SIZE


def _decrypt_meter_payload(raw: bytes) -> dict | None:
    """Decrypt and parse a POSTGW meter metrics packet.

    Returns a dict of sensor readings, or None if the packet is not a
    recognised meter metrics packet or if decryption fails.
    """
    if len(raw) < 166 or not raw.startswith(POSTGW_MAGIC):
        return None

    # IV = bytes [30:46]: 6-byte timestamp zero-padded to 16 bytes
    iv = raw[30:46]
    # Ciphertext = bytes [52:164]: 112 bytes (7 × 16-byte AES blocks)
    ciphertext = raw[52:164]
    if len(ciphertext) != _METER_CLEARTEXT_SIZE:
        _LOGGER.debug("Unexpected ciphertext length %d", len(ciphertext))
        return None

    try:
        cipher = Cipher(algorithms.AES(_AES_KEY), modes.CBC(iv))
        plaintext = cipher.decryptor().update(ciphertext)
    except Exception:  # pylint: disable=broad-except
        _LOGGER.exception("AES decryption failed")
        return None

    if len(plaintext) != _METER_CLEARTEXT_SIZE:
        return None

    # Sanity check: first byte should be the meter metrics packet-type marker
    if plaintext[0] != _METER_PACKET_TYPE_BYTE:
        _LOGGER.debug("Skipping non-meter packet (type byte 0x%02x)", plaintext[0])
        return None

    energy_export = struct.unpack_from(">i", plaintext, _OFF_ENERGY_EXPORT)[0]
    energy_gen = struct.unpack_from(">i", plaintext, _OFF_ENERGY_GEN)[0]
    energy_import = struct.unpack_from(">i", plaintext, _OFF_ENERGY_IMPORT)[0]
    power_export = struct.unpack_from(">i", plaintext, _OFF_POWER_EXPORT)[0]
    power_gen = struct.unpack_from(">i", plaintext, _OFF_POWER_GEN)[0]

    # DIAG: log raw int32 values at offsets 67–91 to help verify field mapping.
    # Compare "grid_raw" with SEMS grid power and "pv_raw" with SEMS PV power.
    _diag = {
        f"off{o}": struct.unpack_from(">i", plaintext, o)[0] for o in range(67, 92, 4)
    }
    _LOGGER.info(
        "DIAG raw power region (W): %s  | grid_raw(off75)=%d  pv_raw(off79)=%d"
        "  energy_exp_dWh=%d  energy_gen_dWh=%d  energy_imp_dWh=%d",
        _diag,
        power_export,
        power_gen,
        energy_export,
        energy_gen,
        energy_import,
    )

    return {
        # Decawatt-hours → kWh (1 dWh = 0.01 kWh)
        "energy_export_kwh": round(energy_export / 100.0, 2),
        "energy_generation_kwh": round(energy_gen / 100.0, 2),
        "energy_import_kwh": round(energy_import / 100.0, 2),
        # Watts (signed; negative export = grid import)
        "power_export_w": power_export,
        "power_generation_w": power_gen,
    }


# -- Data manager (shared between TCP server and sensors) ----------------------


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

    async def async_refresh(self) -> None:
        """Async refresh method for DataUpdateCoordinator.

        Since we receive updates from the meter passively, this is a no-op
        but it allows the coordinator to enforce its update_interval.
        """
        # Data is already updated by the TCP client via update() callback
        pass


# -- TCP relay + packet handler ------------------------------------------------


class GwhkTcpServer:
    """Asyncio TCP server that relays POSTGW traffic and extracts meter data."""

    def __init__(
        self,
        manager: GwhkDataManager,
        listen_host: str,
        listen_port: int,
        cloud_host: str,
        cloud_port: int,
    ) -> None:
        self._manager = manager
        self._listen_host = listen_host
        self._listen_port = listen_port
        self._cloud_host = cloud_host
        self._cloud_port = cloud_port
        self._server: asyncio.Server | None = None
        self._client_tasks: set[asyncio.Task] = set()

    async def start(self) -> None:
        """Start listening for device connections."""
        self._server = await asyncio.start_server(
            self._client_handler,
            self._listen_host,
            self._listen_port,
        )
        _LOGGER.info(
            "HK3000 TCP server listening on %s:%d (relay → %s:%d)",
            self._listen_host,
            self._listen_port,
            self._cloud_host,
            self._cloud_port,
        )

    async def stop(self) -> None:
        """Stop the TCP server and cancel all active client connections."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        for task in list(self._client_tasks):
            task.cancel()
        if self._client_tasks:
            await asyncio.gather(*self._client_tasks, return_exceptions=True)
        _LOGGER.info("HK3000 TCP server stopped")

    async def _client_handler(
        self, device_reader: asyncio.StreamReader, device_writer: asyncio.StreamWriter
    ) -> None:
        """Wrap _handle_client in a tracked task so stop() can cancel it."""
        task = asyncio.current_task()
        self._client_tasks.add(task)
        try:
            await self._handle_client(device_reader, device_writer)
        except Exception:  # pylint: disable=broad-except
            # CancelledError is BaseException (not Exception) so it propagates naturally.
            _LOGGER.debug("Unexpected error in client handler", exc_info=True)
        finally:
            self._client_tasks.discard(task)

    async def _handle_client(
        self, device_reader: asyncio.StreamReader, device_writer: asyncio.StreamWriter
    ) -> None:
        peer = device_writer.get_extra_info("peername")
        _LOGGER.info("HK3000 device connected from %s", peer)

        # Open relay connection to GoodWe cloud
        try:
            cloud_reader, cloud_writer = await asyncio.open_connection(
                self._cloud_host, self._cloud_port
            )
        except RuntimeError as exc:
            # Raised when HA's thread-pool executor is already shut down (e.g.
            # the device reconnected just as HA was stopping).  Close cleanly.
            _LOGGER.debug("Cloud connection skipped during shutdown: %s", exc)
            device_writer.close()
            return
        except OSError:
            _LOGGER.warning(
                "Cannot connect to GoodWe cloud %s:%d — data will still be parsed "
                "but SEMS relay is inactive",
                self._cloud_host,
                self._cloud_port,
            )
            cloud_reader, cloud_writer = None, None

        try:
            await asyncio.gather(
                self._device_to_cloud(device_reader, cloud_writer),
                self._cloud_to_device(cloud_reader, device_writer),
            )
        except Exception:  # pylint: disable=broad-except
            _LOGGER.debug("Connection from %s closed", peer, exc_info=True)
        finally:
            device_writer.close()
            if cloud_writer:
                cloud_writer.close()
            _LOGGER.info("HK3000 device disconnected: %s", peer)

    async def _device_to_cloud(
        self,
        device_reader: asyncio.StreamReader,
        cloud_writer: asyncio.StreamWriter | None,
    ) -> None:
        """Read packets from device, parse them, relay to cloud."""
        buf = bytearray()
        while True:
            chunk = await device_reader.read(4096)
            if not chunk:
                break
            buf.extend(chunk)

            # Process all complete POSTGW packets in the buffer
            offset = 0
            while True:
                # Find next POSTGW magic in buffer
                idx = buf.find(POSTGW_MAGIC, offset)
                if idx == -1:
                    # No magic — discard everything before last 5 bytes
                    buf = buf[max(0, len(buf) - (len(POSTGW_MAGIC) - 1)) :]
                    offset = 0
                    break

                size = _total_packet_size(buf, idx)
                if size is None:
                    # Not enough bytes yet for the length field
                    buf = buf[idx:]
                    offset = 0
                    break

                if idx + size > len(buf):
                    # Have the header but packet not yet complete
                    buf = buf[idx:]
                    offset = 0
                    break

                packet = bytes(buf[idx : idx + size])
                _LOGGER.debug("Device→Cloud packet: %d bytes", len(packet))

                # Parse meter readings
                values = _decrypt_meter_payload(packet)
                if values:
                    _LOGGER.debug("Meter readings: %s", values)
                    self._manager.update(values)

                # Relay raw packet to cloud
                if cloud_writer and not cloud_writer.is_closing():
                    cloud_writer.write(packet)
                    await cloud_writer.drain()

                offset = idx + size

            # Trim processed bytes
            if offset:
                buf = buf[offset:]

    async def _cloud_to_device(
        self,
        cloud_reader: asyncio.StreamReader | None,
        device_writer: asyncio.StreamWriter,
    ) -> None:
        """Relay cloud responses back to the device."""
        if cloud_reader is None:
            return
        while True:
            chunk = await cloud_reader.read(4096)
            if not chunk:
                break
            _LOGGER.debug("Cloud→Device: %d bytes", len(chunk))
            if not device_writer.is_closing():
                device_writer.write(chunk)
                await device_writer.drain()


# -- POSTGW passive listener (server mode) ------------------------------------
#
# In server mode the HF-A21 module acts as a TCP server on port 8899.
# After HA connects, the meter pushes encrypted POSTGW packets periodically
# (~every 30-60 s).  Each packet is 166 bytes structured as:
#
#   [0:6]    "POSTGW" magic
#   [6:10]   version  (00 00 00 99)
#   [10:14]  packet type (03 04 00 00 observed)
#   [14:30]  device serial number (16 ASCII bytes)
#   [30:46]  IV  — 6-byte BCD timestamp zero-padded to 16 bytes
#   [46:52]  timestamp repeated (6 bytes, ignored)
#   [52:164] AES-128-CBC ciphertext (112 bytes)
#   [164:166] CRC (2 bytes, not verified here — packet integrity implied by decryption)
#
# After AES-128-CBC decryption the plaintext is 112 bytes starting with 0x04.
# Confirmed plaintext field map (from live packet analysis, big-endian INT32U/S):
#   [31:35]  energy_import  (INT32U, ×0.01 kWh)
#   [37:41]  energy_export  (INT32U, ×0.01 kWh)
#   [43:47]  energy_gen     (INT32U, ×0.01 kWh)
#   [57:59]  voltage_l1     (INT16U, ×0.1 V)
#   [59:61]  voltage_l2     (INT16U, ×0.1 V)
#   [61:63]  voltage_l3     (INT16U, ×0.1 V)
#   [75:79]  power_l1       (INT32S, ×1 W, negative = importing)
#   [79:83]  power_l2       (INT32S, ×1 W)
#   [83:87]  power_l3       (INT32S, ×1 W)
#   [87:91]  total_power    (INT32S, ×1 W, negative = importing from grid)

_SM_PKT_LEN = 166
_SM_IV_START = 30
_SM_CT_START = 52
_SM_CT_END = 164  # 112 bytes of ciphertext
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
    """Decrypt and parse a POSTGW packet pushed by the meter in server mode.

    Returns a sensor-value dict on success, None on any validation failure.
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
        _LOGGER.debug("Server-mode AES decryption failed", exc_info=True)
        return None

    if len(plaintext) < 92 or plaintext[0] != _SM_PT_TYPE_BYTE:
        _LOGGER.debug(
            "Server-mode packet type mismatch: expected 0x%02x, got 0x%02x",
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

    _LOGGER.debug(
        "Server-mode packet decoded: "
        "import=%.2fkWh  export=%.2fkWh  gen=%.2fkWh  "
        "V=[%.1f,%.1f,%.1f]V  P=[%d,%d,%d]W  total=%dW",
        energy_import * 0.01,
        energy_export * 0.01,
        energy_gen * 0.01,
        voltage_l1 * 0.1,
        voltage_l2 * 0.1,
        voltage_l3 * 0.1,
        power_l1,
        power_l2,
        power_l3,
        total_power,
    )

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
        # power_export_w: positive = exporting to grid, negative = importing
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
