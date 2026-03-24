# GoodWe HK3000 Smart Meter — Home Assistant Integration

Local integration for the **GoodWe HK3000** 3-Phase Smart Meter with Home Assistant.

Intercepts the proprietary **POSTGW** protocol between the HF-A21 module and GoodWe cloud, decrypts the AES-128-CBC payload, and exposes live meter data as Home Assistant sensor entities — with no cloud dependency for the readings.

SEMS cloud access continues to work unchanged via a transparent relay.

## How it works

The HK3000 meter module (HF-A21) acts as a TCP server that **passively pushes** encrypted POSTGW packets at intervals between **~20–40 seconds**. This integration:

1. **Connects to the meter** as a TCP client on port 20001 (meter's default TCP server port)
2. **Receives POSTGW packets** pushed by the meter on its own ~20-40second schedule
3. **Decrypts each packet** (AES-128-CBC, key=`0xFF×16`, IV extracted from packet header)
4. **Parses the plaintext** structure to extract meter readings (power, energy, voltages)
5. **Updates HA sensors** immediately upon receiving new data
6. **Relays packets to GoodWe cloud** (`tcp.goodwe-power.com:20001`) every 60 seconds to keep SEMS app functional

### Update Frequency

The meter's push frequency varies between **~20–40 seconds** and is controlled by the HF-A21 module firmware. This cannot be changed via HA configuration.

To potentially improve responsiveness:
- **AutoFrame Time**: Set to 100ms on the meter's web UI to ensure TCP packets flush immediately
- **AutoFrame Length**: Keep at 128 bytes or higher to fit POSTGW packets in single TCP frames

## Sensors

| Entity | Description | Unit |
|---|---|---|
| Grid Power | Sign: positive=exporting to grid, negative=importing from grid | W |
| Total Energy Exported | Cumulative energy exported to grid | kWh |
| Total Energy Generated | Cumulative solar generation | kWh |
| Total Energy Imported | Cumulative energy imported from grid | kWh |

## Installation

### Prerequisites
- **GoodWe HK3000 Smart Meter** (with HF-A21 Wi-Fi module)
- Meter must be reachable on your LAN via TCP (check firewall)
- Home Assistant must have network access to the meter

### Manual

Copy the `custom_components/goodwe_hk3000` folder into your HA `config/custom_components/` directory and restart Home Assistant.

### HACS

Add this repository as a custom HACS repository (type: Integration), then install **GoodWe HK3000 Smart Meter**.

## Configuration

1. In HA go to **Settings → Devices & Services → Add Integration → GoodWe HK3000 Smart Meter**
2. Enter the meter's **IP address** (e.g., `192.168.0.200`)
3. Confirm the meter's **port** (default `20001`, usually correct)
4. (Optional) Enable **Cloud Relay** to keep SEMS app synchronized

### Meter Setup

Before adding to HA, ensure the HF-A21 module is set to **Server Mode**:
1. Open the meter's web UI: `http://<meter-ip>/pages/app_config.html`
2. Navigate to **Mode → Server**
3. Click Save and wait for reboot
4. Return to HA and complete the setup

## Expected Behavior

### First-Time Setup
When you first add the integration:
- **Connection established** within a few seconds
- **First sensor reading** arrives within ~40 seconds (on the meter's next push)
- **Updates continue** every ~20–40 seconds thereafter (meter-controlled)

If no readings appear after 1 minute:
1. Verify meter is in **Server Mode** (see Meter Setup above)
2. Check network connectivity: `ping <meter-ip>`
3. Verify firewall allows HA ↔ Meter TCP traffic on port 20001

### Data Granularity
- Meter readings are **atomic** per push (all values update together)
- Power measurements update with each 20-second push
- Energy values (cumulative) only increment when meter detects changes
- Time between updates is **fixed by meter firmware** (~20 seconds)

## Supported Devices

- **GoodWe HK3000** (serial prefix `93000HKU`) — fully tested and verified
- **GoodWe HK1000** — untested, may work with similar hardware
- **Other GoodWe meters with HF-A21 module** — likely compatible if they use POSTGW protocol

## Troubleshooting

### "No meters responding" or "No data"
- Verify meter is in **Server Mode** (not Client Mode)
- Check meter is reachable: `telnet <meter-ip> 20001`
- Restart the integration in HA (Developer Tools → Check Config → Restart)

### Connection drops frequently
- Set **AutoFrame Time** to 100ms on meter (web UI)
- Reduce network congestion
- Check meter's TCP timeout setting (default 600 seconds is fine)

### SEMS app stops showing data
- Cloud relay should continue to work automatically
- If relay fails, disable and re-enable **Cloud Relay** in HA setup

## Credits

Protocol reverse engineering, packet structure analysis, and testing based on:
- [smlx/goodwe-exporters](https://github.com/smlx/goodwe-exporters)
- [smlx.dev exhaustive protocol teardown](https://smlx.dev/posts/goodwe-sems-protocol-teardown/)
