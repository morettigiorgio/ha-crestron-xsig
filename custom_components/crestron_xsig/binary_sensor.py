"""Binary sensor platform for Crestron XSIG."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import EntityCategory

from .const import CONF_DEVICE_CLASS, CONF_ID, CONF_IS_ON_JOIN, CONF_NAME, DATA_HUB, DOMAIN, OPT_BINARY_SENSORS
from .entity import CrestronEntity, build_device_info


async def async_setup_entry(hass, entry, async_add_entities):
    hub = hass.data[DOMAIN][entry.entry_id][DATA_HUB]

    entities = [
        CrestronConnectionSensor(hub, entry.entry_id, build_device_info(hass, entry, None))
    ]
    entities += [
        CrestronBinarySensor(hub, entry.entry_id, item, build_device_info(hass, entry, item))
        for item in entry.options.get(OPT_BINARY_SENSORS, [])
    ]
    async_add_entities(entities)


class CrestronBinarySensor(CrestronEntity, BinarySensorEntity):
    def __init__(self, hub, entry_id, item: dict, device_info=None):
        unique_id = f"{entry_id}_binary_sensor_{item[CONF_ID]}"
        super().__init__(hub, entry_id, unique_id, item[CONF_NAME], device_info, item)
        self._attr_device_class = item.get(CONF_DEVICE_CLASS)
        self._join = item[CONF_IS_ON_JOIN]

    @property
    def is_on(self) -> bool:
        return self._hub.get_digital(self._join)


class CrestronConnectionSensor(CrestronEntity, BinarySensorEntity):
    """Reports whether the Crestron processor is currently connected."""

    _attr_device_class = "connectivity"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hub, entry_id, device_info=None):
        super().__init__(
            hub, entry_id, f"{entry_id}_connection", "Connection", device_info
        )

    async def _process_callback(self, cbtype, value):
        # Only update on availability changes, no need to react to every join.
        if cbtype == "available":
            self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        return self._hub.is_available()

    @property
    def available(self) -> bool:
        # This entity IS the availability indicator, so it's always "available"
        # itself even when the processor is disconnected.
        return True
