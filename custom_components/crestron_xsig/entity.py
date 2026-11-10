"""Base classes for Crestron XSIG entities."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo, Entity, EntityCategory

from .const import (
    CONF_DEVICE,
    CONF_ENTITY_CATEGORY,
    ENTITY_CATEGORY_CONFIG,
    ENTITY_CATEGORY_DIAGNOSTIC,
    CONF_ID,
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_NAME,
    CONF_SUGGESTED_AREA,
    DEVICE_REF_CUSTOM_PREFIX,
    DEVICE_REF_EXISTING_PREFIX,
    DEVICE_REF_PROCESSOR,
    DOMAIN,
    OPT_DEVICES,
    custom_device_identifier,
)

_LOGGER = logging.getLogger(__name__)


def processor_device_info(entry) -> DeviceInfo:
    """DeviceInfo of the entry's main device (the Crestron processor)."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title or "Crestron Processor",
        manufacturer="Crestron",
    )


def _device_entry_by_id(hass, device_id: str):
    """Find a registry device through the supported config-entry lookup API."""
    device_registry = dr.async_get(hass)
    for config_entry in hass.config_entries.async_entries():
        for device in dr.async_entries_for_config_entry(
            device_registry, config_entry.entry_id
        ):
            if device.id == device_id:
                return device
    return None


def build_device_info(hass, entry, item: dict | None) -> DeviceInfo:
    """Resolve the DeviceInfo for one entity definition.

    The entity's ``CONF_DEVICE`` field decides where it is attached:

    * unset / ``"processor"``: the entry's main device (the processor);
    * ``"custom:<id>"``: a user-defined device created in the options
      flow (``OPT_DEVICES``); the entity shows up under that device;
    * ``"existing:<id>"``: an already existing Home Assistant device,
      whatever integration owns it -- the entity joins that device.

    Unknown/dangling references fall back to the processor device.
    """
    ref = (item or {}).get(CONF_DEVICE) or DEVICE_REF_PROCESSOR

    if ref.startswith(DEVICE_REF_CUSTOM_PREFIX):
        device_id = ref[len(DEVICE_REF_CUSTOM_PREFIX):]
        for dev in entry.options.get(OPT_DEVICES, []):
            if dev.get(CONF_ID) == device_id:
                info = {
                    "identifiers": {
                        (DOMAIN, custom_device_identifier(entry.entry_id, device_id))
                    },
                    "name": dev.get(CONF_NAME),
                    "manufacturer": dev.get(CONF_MANUFACTURER) or "Crestron",
                }
                device_registry = dr.async_get(hass)
                processor_device = next(
                    (
                        device
                        for device in dr.async_entries_for_config_entry(
                            device_registry, entry.entry_id
                        )
                        if (DOMAIN, entry.entry_id) in device.identifiers
                    ),
                    None,
                )
                if processor_device is not None:
                    info["via_device_id"] = processor_device.id
                else:
                    _LOGGER.warning(
                        "Processor device for entry %s not found; custom device %s "
                        "will have no parent",
                        entry.entry_id,
                        device_id,
                    )
                if dev.get(CONF_MODEL):
                    info["model"] = dev[CONF_MODEL]
                if dev.get(CONF_SUGGESTED_AREA):
                    info["suggested_area"] = dev[CONF_SUGGESTED_AREA]
                return DeviceInfo(**info)
        _LOGGER.warning(
            "Entity %r references unknown custom device %s; "
            "attaching it to the integration device instead",
            (item or {}).get(CONF_NAME),
            device_id,
        )

    elif ref.startswith(DEVICE_REF_EXISTING_PREFIX):
        device_id = ref[len(DEVICE_REF_EXISTING_PREFIX):]
        device = _device_entry_by_id(hass, device_id)
        if device is not None and (device.identifiers or device.connections):
            # Identifiers/connections of the existing device only: adding
            # a name/manufacturer here would overwrite the device's own.
            return DeviceInfo(
                identifiers=set(device.identifiers),
                connections=set(device.connections),
            )
        _LOGGER.warning(
            "Entity %r references unknown existing device %s; "
            "attaching it to the integration device instead",
            (item or {}).get(CONF_NAME),
            device_id,
        )

    elif ref != DEVICE_REF_PROCESSOR:
        _LOGGER.warning(
            "Entity %r has invalid device reference %r; "
            "attaching it to the integration device instead",
            (item or {}).get(CONF_NAME),
            ref,
        )

    return processor_device_info(entry)


class CrestronEntity(Entity):
    """Mixin for common Crestron XSIG entity behavior.

    Entities are attached to one of three devices (see
    ``build_device_info``): the Crestron processor, a user-defined device
    of this config entry, or an already existing Home Assistant device.
    Because entities are only ever created from ``async_setup_entry``,
    Home Assistant can correctly associate them with this config entry --
    this avoids the "device without a config entry" deprecation warning
    that legacy YAML-created entities used to trigger.
    """

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(
        self,
        hub,
        entry_id: str,
        unique_id: str,
        name: str,
        device_info: DeviceInfo | None = None,
        item: dict | None = None,
    ):
        self._hub = hub
        self._entry_id = entry_id
        self._attr_unique_id = unique_id
        self._attr_name = name
        self._device_info = device_info
        category = (item or {}).get(CONF_ENTITY_CATEGORY)
        if category is not None:
            self._attr_entity_category = {
                ENTITY_CATEGORY_CONFIG: EntityCategory.CONFIG,
                ENTITY_CATEGORY_DIAGNOSTIC: EntityCategory.DIAGNOSTIC,
            }.get(category)
        self._pulse_handles: dict[int, asyncio.TimerHandle] = {}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._hub.register_callback(self._process_callback)

    async def async_will_remove_from_hass(self) -> None:
        for handle in self._pulse_handles.values():
            handle.cancel()
        self._pulse_handles.clear()
        self._hub.remove_callback(self._process_callback)
        await super().async_will_remove_from_hass()

    async def _process_callback(self, cbtype, value) -> None:
        # Any join change (or availability change) triggers a refresh.
        # Entities that only care about specific joins can override this
        # to filter and avoid unnecessary state writes.
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return self._hub.is_available()

    def _set_digital(self, join: int, value: bool) -> bool:
        """Set a digital join, cancelling any pending pulse release first."""
        handle = self._pulse_handles.pop(join, None)
        if handle is not None:
            handle.cancel()
        return self._hub.set_digital(join, value)

    def _pulse(self, join: int, seconds: float = 0.2) -> None:
        """Momentary pulse on a digital join, without blocking."""
        self._set_digital(join, True)

        def release() -> None:
            self._pulse_handles.pop(join, None)
            self._hub.set_digital(join, False)

        self._pulse_handles[join] = asyncio.get_running_loop().call_later(
            seconds, release
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Device this entity belongs to (resolved at setup time)."""
        return self._device_info or DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="Crestron Processor",
            manufacturer="Crestron",
        )
