# GoodWe HK3000 Smart Meter — Home Assistant Integration

Local integration for the **GoodWe HK3000** 3-Phase Smart Meter.

Intercepts the proprietary **POSTGW** protocol between the device and GoodWe cloud, decrypts the AES-128-CBC payload, and exposes live meter data as Home Assistant sensor entities — with no cloud dependency for the readings.

SEMS cloud access continues to work unchanged via a transparent relay.

## How it works

The HK3000 speaks GoodWe's binary POSTGW protocol over TCP. This integration:

1. Acts as a TCP proxy listening on a configurable port (default `20001`)
2. The HK3000 must be pointed at your HA host's IP on that port (via the HF-A21 web UI at `http://<device-ip>/pages/app_config.html`)
3. Each incoming POSTGW packet is decrypted (AES-128-CBC, key=`0xFF×16`, IV=packet timestamp) and parsed
4. Readings are published to HA sensor entities immediately
5. The raw packet is simultaneously relayed to `tcp.goodwe-power.com:20001` so SEMS continues working

## Sensors

| Entity | Description | Unit |
|---|---|---|
| Grid Power | Export positive / import negative | W |
| PV Power | Solar generation | W |
| Total Energy Exported | Lifetime export | kWh |
| Total Energy Generated | Lifetime generation | kWh |
| Total Energy Imported | Lifetime import | kWh |

## Installation

### Manual

Copy the `custom_components/goodwe_hk3000` folder into your HA `config/custom_components/` directory and restart Home Assistant.

### HACS

Add this repository as a custom HACS repository (type: Integration), then install **GoodWe HK3000 Smart Meter**.

## Configuration

The integration supports two modes:

### Client Mode (Default)
The HK3000 pushes data to HA on a configurable port.

1. In HA go to **Settings → Devices & Services → Add Integration → GoodWe HK3000 Smart Meter**
2. Select **Client Mode** and set:
   - **Listen Port**: port this HA instance will listen on (default `20001`)
   - **GoodWe Cloud Host**: `tcp.goodwe-power.com` (default)
   - **GoodWe Cloud Port**: `20001` (default)
3. Point the HK3000 device at your HA host IP on that port via its web UI

### Server Mode
HA polls the HK3000 device on a configurable interval.

1. In HA go to **Settings → Devices & Services → Add Integration → GoodWe HK3000 Smart Meter**
2. Select **Server Mode** and set:
   - **Meter Host**: IP address of the HK3000 device (default `192.168.0.200`)
   - **Poll Interval**: how often to poll for updates in seconds (default `15`, range `5-300`)
3. No changes needed on the meter device

## Initial Data Updates

When you first add the integration, **values may take a few minutes to appear or update**. This is normal behavior:
- **Client Mode**: Waits for the first POSTGW packet from the meter (typically arrives within 60 seconds)
- **Server Mode**: Begins polling on the configured interval, with the first update arriving within that interval

If no values appear after 5 minutes, check your network connection and meter configuration.

## Supported devices

- **GoodWe HK3000** (serial prefix `93000HKU`) — tested and verified
- **GoodWe HK1000** — should work, but untested

## Credits

Protocol reverse engineering based on [smlx/goodwe-exporters](https://github.com/smlx/goodwe-exporters) and the teardown at [smlx.dev](https://smlx.dev/posts/goodwe-sems-protocol-teardown/).
