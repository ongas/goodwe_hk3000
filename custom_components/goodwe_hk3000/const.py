"""Constants for the HK3000 integration."""

DOMAIN = "goodwe_hk3000"

CONF_METER_HOST = "meter_host"
CONF_METER_PORT = "meter_port"
CONF_CLOUD_RELAY = "cloud_relay"
CONF_CLOUD_USERNAME = "cloud_username"
CONF_CLOUD_PASSWORD = "cloud_password"
CONF_CLOUD_HOST = "cloud_host"
CONF_CLOUD_PORT = "cloud_port"
CONF_UPDATE_INTERVAL = "update_interval"

DEFAULT_CLOUD_HOST = "tcp.goodwe-power.com"
DEFAULT_CLOUD_PORT = 20001
DEFAULT_METER_HOST = ""  # User must provide their meter IP
DEFAULT_METER_PORT = 20001  # HF-A21 server mode default port
DEFAULT_UPDATE_INTERVAL = 20  # seconds; coordinator refresh interval

# Sensor data keys
KEY_POWER_EXPORT_W = "power_export_w"
KEY_POWER_GENERATION_W = "power_generation_w"
KEY_ENERGY_EXPORT_KWH = "energy_export_kwh"
KEY_ENERGY_GENERATION_KWH = "energy_generation_kwh"
KEY_ENERGY_IMPORT_KWH = "energy_import_kwh"
