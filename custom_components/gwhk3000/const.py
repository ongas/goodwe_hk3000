"""Constants for the HK3000 integration."""

DOMAIN = "gwhk3000"

CONF_LISTEN_PORT = "listen_port"
CONF_CLOUD_HOST = "cloud_host"
CONF_CLOUD_PORT = "cloud_port"

DEFAULT_LISTEN_PORT = 20001
DEFAULT_CLOUD_HOST = "tcp.goodwe-power.com"
DEFAULT_CLOUD_PORT = 20001

# Sensor data keys
KEY_POWER_EXPORT_W = "power_export_w"
KEY_POWER_GENERATION_W = "power_generation_w"
KEY_ENERGY_EXPORT_KWH = "energy_export_kwh"
KEY_ENERGY_GENERATION_KWH = "energy_generation_kwh"
KEY_ENERGY_IMPORT_KWH = "energy_import_kwh"
