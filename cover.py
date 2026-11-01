"""Cover platform for Crestron XSIG."""

from __future__ import annotations

from homeassistant.components.cover import CoverDeviceClass, CoverEntity, CoverEntityFeature

from .const import (
    CONF_CLOSE_JOIN,
    CONF_COVER_TYPE,
    CONF_ID,
    CONF_IS_CLOSED_JOIN,
    CONF_IS_CLOSING_JOIN,
    CONF_IS_OPENED_JOIN,
    CONF_IS_OPENING_JOIN,
    CONF_NAME,
    CONF_OPEN_JOIN,
    CONF_OPTIMISTIC,
    CONF_POS_JOIN,
    CONF_POSITION_COMMANDS,
    CONF_STOP_JOIN,
    DATA_HUB,
    DOMAIN,
    OPT_COVERS,
)
from .entity import CrestronEntity, build_device_info

_DEVICE_CLASS_MAP = {
    "shade": CoverDeviceClass.SHADE,
    "blind": CoverDeviceClass.BLIND,
    "curtain": CoverDeviceClass.CURTAIN,
}


async def async_setup_entry(hass, entry, async_add_entities):
    hub = hass.data[DOMAIN][entry.entry_id][DATA_HUB]
    entities = [
        CrestronCover(hub, entry.entry_id, item, build_device_info(hass, entry, item))
        for item in entry.options.get(OPT_COVERS, [])
    ]
    async_add_entities(entities)


class CrestronCover(CrestronEntity, CoverEntity):
    """Cover with freely combinable command/feedback joins (KI-023).

    All joins are optional: a setup can mix digital pulses (open/close/
    stop), an analog position command, and feedback joins in any
    combination. Commands are sent on every configured channel: e.g.
    "open" pulses the open join AND writes 65535 to the position join
    when both are configured. On the SIMPL side the XSIG in/out signals
    are separate: wire only what you use.
    """

    def __init__(self, hub, entry_id, item: dict, device_info=None):
        unique_id = f"{entry_id}_cover_{item[CONF_ID]}"
        super().__init__(hub, entry_id, unique_id, item[CONF_NAME], device_info, item)
        self._attr_device_class = _DEVICE_CLASS_MAP.get(item.get(CONF_COVER_TYPE))
        self._optimistic = item.get(CONF_OPTIMISTIC, False)
        self._position_commands = item.get(CONF_POSITION_COMMANDS, False)
        self._pos_join = item.get(CONF_POS_JOIN)
        self._open_join = item.get(CONF_OPEN_JOIN)
        self._close_join = item.get(CONF_CLOSE_JOIN)
        self._stop_join = item.get(CONF_STOP_JOIN)
        self._is_opening_join = item.get(CONF_IS_OPENING_JOIN)
        self._is_closing_join = item.get(CONF_IS_CLOSING_JOIN)
        self._is_closed_join = item.get(CONF_IS_CLOSED_JOIN)
        self._is_opened_join = item.get(CONF_IS_OPENED_JOIN)

        features = CoverEntityFeature(0)
        if self._open_join or self._pos_join:
            features |= CoverEntityFeature.OPEN
        if self._close_join or self._pos_join:
            features |= CoverEntityFeature.CLOSE
        if self._stop_join:
            features |= CoverEntityFeature.STOP
        if self._pos_join:
            features |= CoverEntityFeature.SET_POSITION
        self._attr_supported_features = features

    def _digital(self, join):
        """State of a feedback join, or None when not configured."""
        if join is None:
            return None
        return self._hub.get_digital(join)

    @property
    def current_cover_position(self):
        if self._pos_join is None:
            return None
        raw_position = max(0, min(65535, self._hub.get_analog(self._pos_join)))
        return round(raw_position * 100 / 65535)

    @property
    def is_opening(self):
        return self._digital(self._is_opening_join)

    @property
    def is_closing(self):
        return self._digital(self._is_closing_join)

    @property
    def is_closed(self):
        """Closed state from the feedback joins.

        HA derives "open" from not-closed: the optional is_opened join is
        used to confirm the open state (it wins), and to determine the
        state when no is_closed join is configured.
        """
        opened = self._digital(self._is_opened_join)
        if opened:
            return False  # definitively open
        closed = self._digital(self._is_closed_join)
        if closed is not None:
            return closed
        if opened is not None:
            return not opened
        if self._pos_join is not None:
            return self._hub.get_analog(self._pos_join) <= 0
        return None

    def _set_position(self, value: int) -> None:
        """Send a new position value (and mirror it locally if optimistic)."""
        if self._hub.set_analog(self._pos_join, value) and self._optimistic:
            self._hub.update_analog(self._pos_join, value)
            self.async_write_ha_state()

    async def async_set_cover_position(self, **kwargs):
        if self._pos_join is not None:
            self._set_position(round(kwargs["position"] * 65535 / 100))

    async def async_open_cover(self, **kwargs):
        if self._open_join:
            self._pulse(self._open_join)
        # The position command is only sent when explicitly enabled (or
        # when there is no pulse join to command with).
        if self._pos_join is not None and (
            self._position_commands or not self._open_join
        ):
            self._set_position(0xFFFF)

    async def async_close_cover(self, **kwargs):
        if self._close_join:
            self._pulse(self._close_join)
        if self._pos_join is not None and (
            self._position_commands or not self._close_join
        ):
            self._set_position(0)

    async def async_stop_cover(self, **kwargs):
        if self._stop_join:
            self._pulse(self._stop_join)
