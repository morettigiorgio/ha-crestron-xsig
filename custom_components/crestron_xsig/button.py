"""Button platform for Crestron XSIG — digital pulse outputs (KI-028)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity

from .const import (
    CONF_BUTTON_JOIN,
    CONF_ID,
    CONF_NAME,
    DATA_HUB,
    DOMAIN,
    OPT_BUTTONS,
)
from .entity import CrestronEntity, build_device_info


async def async_setup_entry(hass, entry, async_add_entities):
    hub = hass.data[DOMAIN][entry.entry_id][DATA_HUB]
    entities = [
        CrestronButton(hub, entry.entry_id, item, build_device_info(hass, entry, item))
        for item in entry.options.get(OPT_BUTTONS, [])
    ]
    async_add_entities(entities)


class CrestronButton(CrestronEntity, ButtonEntity):
    """Pressing the button pulses a digital join (momentary on/off),
    the same shape as the pulse commands used by covers and services."""

    def __init__(self, hub, entry_id, item: dict, device_info=None):
        unique_id = f"{entry_id}_button_{item[CONF_ID]}"
        super().__init__(hub, entry_id, unique_id, item[CONF_NAME], device_info, item)
        self._join = item[CONF_BUTTON_JOIN]

    async def async_press(self) -> None:
        self._pulse(self._join)
