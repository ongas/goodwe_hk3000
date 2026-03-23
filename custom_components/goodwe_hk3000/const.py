"""Constants for the HK3000 integration."""

DOMAIN = "goodwe_hk3000"

CONF_MODE = "mode"
CONF_LISTEN_PORT = "listen_port"
CONF_CLOUD_HOST = "cloud_host"
CONF_CLOUD_PORT = "cloud_port"
CONF_METER_HOST = "meter_host"
CONF_POLL_INTERVAL = "poll_interval"

MODE_CLIENT = "client"
MODE_SERVER = "server"

DEFAULT_MODE = MODE_CLIENT
DEFAULT_LISTEN_PORT = 20001
DEFAULT_CLOUD_HOST = "tcp.goodwe-power.com"
DEFAULT_CLOUD_PORT = 20001
DEFAULT_METER_HOST = ""  # User must provide their meter IP
DEFAULT_POLL_INTERVAL = 15

# Sensor data keys
KEY_POWER_EXPORT_W = "power_export_w"
KEY_POWER_GENERATION_W = "power_generation_w"
KEY_ENERGY_EXPORT_KWH = "energy_export_kwh"
KEY_ENERGY_GENERATION_KWH = "energy_generation_kwh"
KEY_ENERGY_IMPORT_KWH = "energy_import_kwh"
