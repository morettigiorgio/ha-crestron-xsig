"""Diagnostics and JSON export for Crestron XSIG."""

from __future__ import annotations

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

# Configured scripts and templates are included as they are part of the user's
# export. Redact commonly named credentials if they occur in nested service data.
TO_REDACT = {
    "access_token",
    "api_key",
    "authorization",
    "password",
    "secret",
    "token",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    """Return the complete integration configuration as a downloadable JSON."""
    return {"config_entry": async_redact_data(entry.as_dict(), TO_REDACT)}
