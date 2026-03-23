"""HK3000 data coordinator: TCP server, POSTGW relay and meter packet parser."""

from __future__ import annotations

import asyncio
import logging
import struct
from collections.abc import Callable

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

_LOGGER = logging.getLogger(__name__)
# File-based diagnostic logger (bypasses HA log filtering)
_RELAY_LOG = "/config/hk3000_relay.log"
def _flog(msg: str) -> None:
    try:
        import datetime
        with open(_RELAY_LOG, "a") as _f:
            _f.write(f"{datetime.datetime.now().isoformat()} {msg}\n")
    except Exception:
        pass


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

# -- TCP client (server mode polling) ------------------------------------------


class GwhkTcpClient:
    """Asyncio TCP client that polls the meter periodically."""

    def __init__(
        self,
        manager: GwhkDataManager,
        meter_host: str,
        meter_port: int,
        poll_interval: int,
    ) -> None:
        self._manager = manager
        self._meter_host = meter_host
        self._meter_port = meter_port
        self._poll_interval = poll_interval
        self._running = False

    async def start(self) -> None:
        """Start polling the meter."""
        self._running = True
        _LOGGER.info(
            "HK3000 TCP client polling %s:%d every %d seconds",
            self._meter_host,
            self._meter_port,
            self._poll_interval,
        )
        asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        """Stop polling the meter."""
        self._running = False
        _LOGGER.info("HK3000 TCP client stopped")

    async def _poll_loop(self) -> None:
        """Periodically connect to meter and read POSTGW packets."""
        while self._running:
            try:
                await self._poll_once()
            except Exception:  # pylint: disable=broad-except
                _LOGGER.debug("Poll failed, retrying", exc_info=True)
            
            if self._running:
                await asyncio.sleep(self._poll_interval)

    async def _poll_once(self) -> None:
        """Connect to meter, read one POSTGW packet, and update sensors."""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self._meter_host, self._meter_port),
                timeout=10
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

        try:
            buf = bytearray()
            while True:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=5)
                if not chunk:
                    break
                buf.extend(chunk)

                # Find and process POSTGW packets
                offset = 0
                while True:
                    idx = buf.find(POSTGW_MAGIC, offset)
                    if idx == -1:
                        buf = buf[max(0, len(buf) - (len(POSTGW_MAGIC) - 1)) :]
                        offset = 0
                        break

                    size = _total_packet_size(buf, idx)
                    if size is None:
                        buf = buf[idx:]
                        offset = 0
                        break

                    if idx + size > len(buf):
                        buf = buf[idx:]
                        offset = 0
                        break

                    packet = bytes(buf[idx : idx + size])
                    _LOGGER.debug("Meter→HA packet: %d bytes", len(packet))

                    # Parse meter readings
                    values = _decrypt_meter_payload(packet)
                    if values:
                        _LOGGER.debug("Meter readings: %s", values)
                        self._manager.update(values)
                        _flog(f"POLL_RECEIVED: {len(packet)} bytes  values={values}")
                        # After receiving one good packet, stop and reconnect next cycle
                        return

                    offset = idx + size

        finally:
            writer.close()
            await writer.wait_closed()