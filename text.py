"""Text platform for Crestron XSIG — serial join outputs (KI-026)."""

from __future__ import annotations

from homeassistant.components.text import TextEntity

from .const import (
    CONF_ID,
    CONF_NAME,
    CONF_OPTIMISTIC,
    CONF_SERIAL_JOIN,
    DATA_HUB,
    DOMAIN,
    OPT_TEXTS,
)
from .entity import CrestronEntity, build_device_info

MAX_SERIAL_CHARS = 252  # XSIG serial join limit


async def async_setup_entry(hass, entry, async_add_entities):
    hub = hass.data[DOMAIN][entry.entry_id][DATA_HUB]
    entities = [
        CrestronText(hub, entry.entry_id, item, build_device_info(hass, entry, item))
        for item in entry.options.get(OPT_TEXTS, [])
    ]
    async_add_entities(entities)


class CrestronText(CrestronEntity, TextEntity):
    """A write-capable text bound to a serial join.

    Setting the value sends the string to the processor; the current
    value is whatever was last sent (optimistic) or received on the
    join.
    """

    _attr_native_min = 0
    _attr_native_max = MAX_SERIAL_CHARS
    # mode defaults to TEXT on TextEntity — no enum import needed
    # (TextEntityMode/TextMode moved between HA versions).

    def __init__(self, hub, entry_id, item: dict, device_info=None):
        unique_id = f"{entry_id}_text_{item[CONF_ID]}"
        super().__init__(hub, entry_id, unique_id, item[CONF_NAME], device_info, item)
        self._join = item[CONF_SERIAL_JOIN]
        self._optimistic = item.get(CONF_OPTIMISTIC, True)

    @property
    def native_value(self):
        return self._hub.get_serial(self._join)

    async def async_set_value(self, value: str) -> None:
        sent = self._hub.set_serial(self._join, value)
        if sent and self._optimistic:
            self._hub.update_serial(self._join, value)
            self.async_write_ha_state()
