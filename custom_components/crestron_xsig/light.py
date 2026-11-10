"""Light platform for Crestron XSIG."""

from __future__ import annotations

import logging

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
)

from .const import (
    CONF_BRIGHTNESS_DEFAULT,
    CONF_BRIGHTNESS_JOIN,
    CONF_BLUE_JOIN,
    CONF_GREEN_JOIN,
    CONF_ID,
    CONF_RED_JOIN,
    CONF_NAME,
    CONF_OPTIMISTIC,
    DATA_HUB,
    DOMAIN,
    OPT_LIGHTS,
)
from .entity import CrestronEntity, build_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    hub = hass.data[DOMAIN][entry.entry_id][DATA_HUB]
    entities = [
        CrestronLight(hub, entry.entry_id, item, build_device_info(hass, entry, item))
        for item in entry.options.get(OPT_LIGHTS, [])
    ]
    async_add_entities(entities)


class CrestronLight(CrestronEntity, LightEntity):
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(self, hub, entry_id, item: dict, device_info=None):
        unique_id = f"{entry_id}_light_{item[CONF_ID]}"
        super().__init__(hub, entry_id, unique_id, item[CONF_NAME], device_info, item)
        self._brightness_join = item[CONF_BRIGHTNESS_JOIN]
        rgb_joins = (
            item.get(CONF_RED_JOIN),
            item.get(CONF_GREEN_JOIN),
            item.get(CONF_BLUE_JOIN),
        )
        self._rgb_joins = rgb_joins if all(join is not None for join in rgb_joins) else None
        if self._rgb_joins:
            self._attr_color_mode = ColorMode.RGB
            self._attr_supported_color_modes = {ColorMode.RGB}
        elif any(join is not None for join in rgb_joins):
            _LOGGER.warning(
                "Light %r has incomplete RGB joins; using brightness-only mode",
                item.get(CONF_NAME),
            )
        default_brightness = item.get(CONF_BRIGHTNESS_DEFAULT, 128)
        if (
            isinstance(default_brightness, bool)
            or not isinstance(default_brightness, int)
            or not 0 <= default_brightness <= 255
        ):
            _LOGGER.warning(
                "Light %r: invalid default brightness %r, falling back to 128",
                item.get(CONF_NAME),
                default_brightness,
            )
            default_brightness = 128
        self._default_brightness = default_brightness
        self._optimistic = item.get(CONF_OPTIMISTIC, False)

    @staticmethod
    def _from_xsig(value: int) -> int:
        """Scale a 16-bit XSIG analog value to an 8-bit light value."""
        value = max(0, min(65535, value))
        if value == 0:
            return 0
        return max(1, value * 255 // 65535)

    @staticmethod
    def _to_xsig(value: int) -> int:
        """Scale an 8-bit light value to the 16-bit XSIG analog range."""
        return round(max(0, min(255, int(value))) * 65535 / 255)

    @property
    def brightness(self) -> int:
        return self._from_xsig(self._hub.get_analog(self._brightness_join))

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        if self._rgb_joins is None:
            return None
        return tuple(
            self._from_xsig(self._hub.get_analog(join)) for join in self._rgb_joins
        )

    @property
    def is_on(self) -> bool:
        return bool(self.brightness)

    async def async_turn_on(self, **kwargs):
        rgb_color = kwargs.get(ATTR_RGB_COLOR)
        did_update = False
        if self._rgb_joins is not None and rgb_color is not None:
            try:
                colors = tuple(rgb_color)
            except TypeError:
                colors = ()
            if len(colors) == 3:
                for join, color in zip(self._rgb_joins, colors):
                    value = self._to_xsig(color)
                    if self._hub.set_analog(join, value):
                        if self._optimistic:
                            self._hub.update_analog(join, value)
                        did_update = True
            else:
                _LOGGER.warning(
                    "Light %r received an invalid RGB color %r",
                    self._attr_name,
                    rgb_color,
                )

        brightness = kwargs.get(ATTR_BRIGHTNESS)
        if brightness is None and not (self._rgb_joins and rgb_color is not None):
            brightness = self._default_brightness
        if brightness is not None:
            value = self._to_xsig(brightness)
            if self._hub.set_analog(self._brightness_join, value):
                if self._optimistic:
                    self._hub.update_analog(self._brightness_join, value)
                did_update = True

        if did_update and self._optimistic:
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        if self._hub.set_analog(self._brightness_join, 0) and self._optimistic:
            self._hub.update_analog(self._brightness_join, 0)
            self.async_write_ha_state()
