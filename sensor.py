"""Sensor platform for Crestron XSIG."""

from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity, SensorStateClass

from .const import (
    CONF_DEVICE_CLASS,
    CONF_DIVISOR,
    CONF_ID,
    CONF_NAME,
    CONF_UNIT_OF_MEASUREMENT,
    CONF_VALUE_JOIN,
    DATA_HUB,
    DOMAIN,
    OPT_SENSORS,
)
from .entity import CrestronEntity, build_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    hub = hass.data[DOMAIN][entry.entry_id][DATA_HUB]
    entities = [
        CrestronSensor(hub, entry.entry_id, item, build_device_info(hass, entry, item))
        for item in entry.options.get(OPT_SENSORS, [])
    ]
    async_add_entities(entities)


class CrestronSensor(CrestronEntity, SensorEntity):
    def __init__(self, hub, entry_id, item: dict, device_info=None):
        unique_id = f"{entry_id}_sensor_{item[CONF_ID]}"
        super().__init__(hub, entry_id, unique_id, item[CONF_NAME], device_info, item)
        self._attr_device_class = item.get(CONF_DEVICE_CLASS)
        if self._attr_device_class in {"energy", "gas", "water"}:
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        elif self._attr_device_class not in {"date", "timestamp", "enum"}:
            self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = item.get(CONF_UNIT_OF_MEASUREMENT)
        self._join = item[CONF_VALUE_JOIN]
        # Defensive clamp (KI-034): options edited by hand can hold a divisor
        # of 0 / negative / non-numeric and every state read would crash.
        divisor = item.get(CONF_DIVISOR, 1)
        if (
            isinstance(divisor, bool)
            or not isinstance(divisor, (int, float))
            or divisor <= 0
        ):
            _LOGGER.warning(
                "Sensor %r: invalid divisor %r, falling back to 1",
                item[CONF_NAME],
                divisor,
            )
            divisor = 1
        self._divisor = divisor

    @property
    def native_value(self):
        return self._hub.get_analog(self._join) / self._divisor
