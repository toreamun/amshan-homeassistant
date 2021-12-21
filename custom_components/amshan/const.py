"""Constants for the AMS HAN meter integration."""
from __future__ import annotations

import homeassistant.const as hassconst

DOMAIN = "amshan"

ENTRY_DATA_MEASURE_QUEUE = "measure_queue"
ENTRY_DATA_MEASURE_CONNECTION = "connection"
ENTRY_DATA_UPDATE_LISTENER_UNSUBSCRIBE = "update_listener_unsubscribe"

ICON_POWER_IMPORT = "mdi:flash"
ICON_POWER_EXPORT = "mdi:flash-outline"
ICON_CURRENT = "mdi:current-ac"
ICON_VOLTAGE = "mdi:alpha-v-box-outline"
ICON_COUNTER = "mdi:counter"

UNIT_KILO_VOLT_AMPERE_REACTIVE = "kVAr"
UNIT_KILO_VOLT_AMPERE_REACTIVE_HOURS = "kVArh"

IPV4_ADR_REGEX = (
    "(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\\.){3}"
    "([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])"
)
IPV6_ADR_REGEX = "(?:[A-F0-9]{1,4}:){7}[A-F0-9]{1,4}"
HOSTNAME_REGEX = (
    "(([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\\-]*[a-zA-Z0-9])\\.)*"
    "([A-Za-z0-9]|[A-Za-z0-9][A-Za-z0-9\\-]*[A-Za-z0-9])"
)
HOSTNAME_IP4_IP6_REGEX = (
    "^(" + IPV4_ADR_REGEX + ")|(" + HOSTNAME_REGEX + ")|(" + IPV6_ADR_REGEX + ")$"
)

# Configuration and options
CONF_SERIAL_PORT = hassconst.CONF_PORT
CONF_SERIAL_BAUDRATE = "baudrate"
CONF_SERIAL_PARITY = "parity"
CONF_SERIAL_BYTESIZE = "bytesize"
CONF_SERIAL_STOPBITS = "stopbits"
CONF_SERIAL_XONXOFF = "xonxoff"
CONF_SERIAL_RTSCTS = "rtscts"
CONF_SERIAL_DSRDTR = "dsrdtr"

CONF_TCP_HOST = hassconst.CONF_HOST
CONF_TCP_PORT = hassconst.CONF_PORT

CONF_OPTIONS_SCALE_FACTOR = "scale_factor"
