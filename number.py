"""Number platform for Crestron XSIG — analog join outputs (KI-026)."""

from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity

from .const import (
    CONF_ID,
    CONF_MAX_VALUE,
    CONF_MIN_VALUE,
    CONF_NAME,
    CONF_OPTIMISTIC,
    CONF_STEP,
    CONF_UNIT_OF_MEASUREMENT,
    CONF_VALUE_JOIN,
    DATA_HUB,
    DOMAIN,
    OPT_NUMBERS,
)
from .entity import CrestronEntity, build_device_info

_LOGGER = logging.getLogger(__name__)


def _safe_float(value, fallback: float, field: str, item: dict) -> float:
    """Defensive clamp (KI-035): hand-edited options can hold non-numeric
    values, which would crash entity setup."""
    try:
        return float(value)
    except (TypeError, ValueError):
        _LOGGER.warning(
            "Number %r: invalid %s %r, falling back to %s",
            item.get(CONF_NAME),
            field,
            value,
            fallback,
        )
        return float(fallback)


def _safe_integer_float(value, fallback: float, field: str, item: dict) -> float:
    """Keep Number config integral for the integer-only XSIG analog protocol."""
    number = _safe_float(value, fallback, field, item)
    if not number.is_integer():
        _LOGGER.warning(
            "Number %r: non-integer %s %r, falling back to %s",
            item.get(CONF_NAME),
            field,
            value,
            fallback,
        )
        return float(fallback)
    return number


async def async_setup_entry(hass, entry, async_add_entities):
    hub = hass.data[DOMAIN][entry.entry_id][DATA_HUB]
    entities = [
        CrestronNumber(hub, entry.entry_id, item, build_device_info(hass, entry, item))
        for item in entry.options.get(OPT_NUMBERS, [])
    ]
    async_add_entities(entities)


class CrestronNumber(CrestronEntity, NumberEntity):
    """A number slider bound to an analog join (raw XSIG range by
    default: 0-65535). Setting the value sends it to the processor; the
    shown value is whatever was last sent (optimistic) or received on
    the join."""

    _attr_mode = "box"  # plain string: NumberMode moved between HA versions

    def __init__(self, hub, entry_id, item: dict, device_info=None):
        unique_id = f"{entry_id}_number_{item[CONF_ID]}"
        super().__init__(hub, entry_id, unique_id, item[CONF_NAME], device_info, item)
        self._join = item[CONF_VALUE_JOIN]
        # Defensive clamps (KI-035): hand-edited options can hold an
        # incoherent range (max <= min, step <= 0) or values outside the
        # XSIG analog range 0..65535.
        min_value = _safe_integer_float(
            item.get(CONF_MIN_VALUE), 0.0, CONF_MIN_VALUE, item
        )
        max_value = _safe_integer_float(
            item.get(CONF_MAX_VALUE), 65535.0, CONF_MAX_VALUE, item
        )
        step = _safe_integer_float(item.get(CONF_STEP), 1.0, CONF_STEP, item)
        if min_value < 0 or max_value > 65535:
            _LOGGER.warning(
                "Number %r: range %s..%s outside the analog range 0..65535, clamping",
                item[CONF_NAME],
                min_value,
                max_value,
            )
            min_value = max(min_value, 0.0)
            max_value = min(max_value, 65535.0)
        if max_value <= min_value:
            _LOGGER.warning(
                "Number %r: invalid range min=%s max=%s, falling back to 0..65535",
                item[CONF_NAME],
                min_value,
                max_value,
            )
            min_value, max_value = 0.0, 65535.0
        if step <= 0:
            _LOGGER.warning(
                "Number %r: invalid step %s, falling back to 1",
                item[CONF_NAME],
                step,
            )
            step = 1.0
        self._attr_native_min_value = min_value
        self._attr_native_max_value = max_value
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = item.get(CONF_UNIT_OF_MEASUREMENT)
        self._optimistic = item.get(CONF_OPTIMISTIC, True)

    @property
    def native_value(self):
        return self._hub.get_analog(self._join)

    async def async_set_native_value(self, value: float) -> None:
        try:
            numeric_value = float(value)
        except (TypeError, ValueError) as err:
            raise ValueError(
                "Number value must be an integer XSIG analog value"
            ) from err
        if not numeric_value.is_integer():
            raise ValueError(
                "Number value must be an integer XSIG analog value"
            )
        int_value = int(numeric_value)
        sent = self._hub.set_analog(self._join, int_value)
        if sent and self._optimistic:
            self._hub.update_analog(self._join, int_value)
            self.async_write_ha_state()
