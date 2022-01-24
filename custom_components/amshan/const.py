"""Constants for the AMS HAN meter integration."""
from __future__ import annotations

DOMAIN = "amshan"

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
