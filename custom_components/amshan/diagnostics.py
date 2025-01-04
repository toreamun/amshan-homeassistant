"""AMSHAN diagnostics."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from . import AmsHanConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,  # noqa: ARG001
    config_entry: AmsHanConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    return {"config_entry": config_entry.as_dict()}
