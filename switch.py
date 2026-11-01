"""Switch platform for Crestron XSIG."""

from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity

from .const import (
    CONF_DEVICE_CLASS,
    CONF_ID,
    CONF_NAME,
    CONF_OPTIMISTIC,
    CONF_STATE_SYNC,
    CONF_SWITCH_JOIN,
    DATA_HUB,
    DOMAIN,
    OPT_SWITCHES,
)
from .entity import CrestronEntity, build_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    hub = hass.data[DOMAIN][entry.entry_id][DATA_HUB]
    entities = [
        CrestronSwitch(hub, entry.entry_id, item, build_device_info(hass, entry, item))
        for item in entry.options.get(OPT_SWITCHES, [])
    ]
    async_add_entities(entities)


class CrestronSwitch(CrestronEntity, SwitchEntity):
    def __init__(self, hub, entry_id, item: dict, device_info=None):
        unique_id = f"{entry_id}_switch_{item[CONF_ID]}"
        super().__init__(hub, entry_id, unique_id, item[CONF_NAME], device_info, item)
        self._attr_device_class = item.get(CONF_DEVICE_CLASS, "switch")
        self._switch_join = item[CONF_SWITCH_JOIN]
        self._optimistic = item.get(CONF_OPTIMISTIC, False)
        self._state_sync = item.get(CONF_STATE_SYNC, False)

    async def _process_callback(self, cbtype, value) -> None:
        await super()._process_callback(cbtype, value)
        # State sync: keep the XSIG join updated with the REAL state, not
        # only after commands from HA — also when the state changed for
        # any other reason (e.g. feedback from Crestron). Only sent when
        # it differs from the last value actually sent, to avoid echo
        # loops. Use with level-driven programs only (see docs/WIRING.md).
        if self._state_sync and cbtype == f"d{self._switch_join}":
            state = self._hub.get_digital(self._switch_join)
            if state != self._hub.last_sent_digital(self._switch_join):
                self._hub.set_digital(self._switch_join, state)

    @property
    def is_on(self) -> bool:
        return self._hub.get_digital(self._switch_join)

    def _set(self, value: bool) -> None:
        sent = self._set_digital(self._switch_join, value)
        if sent and self._optimistic:
            self._hub.update_digital(self._switch_join, value)
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs):
        self._set(True)

    async def async_turn_off(self, **kwargs):
        self._set(False)
