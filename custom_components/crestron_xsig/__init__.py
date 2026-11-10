"""The Crestron XSIG integration."""

from __future__ import annotations

import copy
import logging
from functools import partial

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, device_registry as dr

from .const import (
    CONF_ENTRY_ID,
    CONF_ID,
    CONF_JOIN,
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_NAME,
    CONF_PORT,
    CONF_SUGGESTED_AREA,
    CONF_VALUE,
    custom_device_identifier,
    normalize_option_ids,
    OPT_DEVICES,
    DATA_ACTIONS,
    DATA_EXPOSES,
    DATA_HUB,
    DOMAIN,
    EVENT_JOIN_RECEIVED,
    OPT_ACTIONS,
    OPT_EXPOSES,
    PLATFORMS,
    SERVICE_RELOAD_CONNECTION,
    SERVICE_SET_ANALOG,
    SERVICE_SET_DIGITAL,
    SERVICE_SET_SERIAL,
    VALIDATE_ANALOG_JOIN,
    VALIDATE_ANALOG_VALUE,
    VALIDATE_DIGITAL_JOIN,
    VALIDATE_SERIAL_JOIN,
    native_join_value,
    parse_join,
)
from .actions import ActionManager
from .expose import ExposeManager
from .xsig_hub import CrestronXsigHub

_LOGGER = logging.getLogger(__name__)

# Joins and analog values are validated per type against the XSIG limits
# (digital 1..4096, analog/serial 1..1024, analog value 0..65535): invalid
# calls are explicitly rejected, never silently clamped (KI-011).
SET_DIGITAL_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_JOIN): VALIDATE_DIGITAL_JOIN,
        vol.Required(CONF_VALUE): cv.boolean,
        vol.Optional(CONF_ENTRY_ID): vol.Any(None, cv.string),
    }
)
SET_ANALOG_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_JOIN): VALIDATE_ANALOG_JOIN,
        vol.Required(CONF_VALUE): VALIDATE_ANALOG_VALUE,
        vol.Optional(CONF_ENTRY_ID): vol.Any(None, cv.string),
    }
)
SET_SERIAL_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_JOIN): VALIDATE_SERIAL_JOIN,
        vol.Required(CONF_VALUE): cv.string,
        vol.Optional(CONF_ENTRY_ID): vol.Any(None, cv.string),
    }
)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate legacy option records to include stable entity IDs."""
    target_version = 2
    if entry.version > target_version:
        _LOGGER.error(
            "Cannot migrate Crestron XSIG entry %s from newer version %s",
            entry.entry_id,
            entry.version,
        )
        return False

    options = copy.deepcopy(dict(entry.options))
    repaired = normalize_option_ids(options)
    if repaired:
        _LOGGER.warning(
            "Migrating %s missing option IDs for Crestron XSIG entry %s",
            repaired,
            entry.entry_id,
        )
    hass.config_entries.async_update_entry(
        entry, options=options, version=target_version
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Crestron XSIG from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Also repair options edited after the version migration. Persist before
    # platform setup because all entity platforms consume item[CONF_ID].
    options = copy.deepcopy(dict(entry.options))
    repaired = normalize_option_ids(options)
    if repaired:
        _LOGGER.warning(
            "Generated %s missing option IDs before setup for entry %s",
            repaired,
            entry.entry_id,
        )
        hass.config_entries.async_update_entry(entry, options=options)

    hub = CrestronXsigHub(unique_id=entry.entry_id)
    expose_manager = ExposeManager(hass, hub, entry.options.get(OPT_EXPOSES, []))
    action_manager = ActionManager(hass, hub, entry.options.get(OPT_ACTIONS, []))
    hass.data[DOMAIN][entry.entry_id] = {
        DATA_HUB: hub,
        DATA_EXPOSES: expose_manager,
        DATA_ACTIONS: action_manager,
    }

    # Raw join telemetry, for native HA automations.
    hub.register_callback(partial(_async_fire_join_event, hass, entry.entry_id))

    await expose_manager.async_setup()
    await action_manager.async_setup()

    # Register the processor as a device right away so it shows up even
    # before the first TCP connection arrives, then the user-defined
    # devices (OPT_DEVICES) used to group entities in the UI.
    device_registry = dr.async_get(hass)
    processor_device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="Crestron",
    )

    wanted_devices = set()
    for dev in entry.options.get(OPT_DEVICES, []):
        dev_id = dev.get(CONF_ID)
        if not dev_id:
            continue
        identifier = custom_device_identifier(entry.entry_id, dev_id)
        wanted_devices.add(identifier)
        kwargs = {
            "config_entry_id": entry.entry_id,
            "identifiers": {(DOMAIN, identifier)},
            "via_device_id": processor_device.id,
            "name": dev.get(CONF_NAME),
            "manufacturer": dev.get(CONF_MANUFACTURER) or "Crestron",
        }
        if dev.get(CONF_MODEL):
            kwargs["model"] = dev[CONF_MODEL]
        if dev.get(CONF_SUGGESTED_AREA):
            kwargs["suggested_area"] = dev[CONF_SUGGESTED_AREA]
        device_registry.async_get_or_create(**kwargs)

    # Drop user-defined devices that were deleted from the options, so
    # empty leftovers don't linger in the devices list.
    for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
        for domain, identifier in device.identifiers:
            if (
                domain == DOMAIN
                and identifier != entry.entry_id
                and identifier not in wanted_devices
            ):
                device_registry.async_update_device(
                    device.id, remove_config_entry_id=entry.entry_id
                )
                break

    entry.async_create_background_task(
        hass, hub.listen(entry.data[CONF_PORT]), "crestron_xsig_listen"
    )

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _async_register_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    data = hass.data[DOMAIN].pop(entry.entry_id, None)
    if data is not None:
        expose_manager = data.get(DATA_EXPOSES)
        if expose_manager is not None:
            await expose_manager.async_unload()
        action_manager = data.get(DATA_ACTIONS)
        if action_manager is not None:
            await action_manager.async_unload()
        await data[DATA_HUB].stop()

    if not hass.data[DOMAIN]:
        _async_unregister_services(hass)
        hass.data.pop(DOMAIN)

    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options (entity list) change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_fire_join_event(
    hass: HomeAssistant, entry_id: str, cbtype: str, value: str
) -> None:
    """Fire a ``crestron_xsig_join_received`` event for every received join.

    Lets automations react to raw Crestron traffic without configuring an
    entity or an action rule.
    """
    if cbtype == "available":
        return
    parsed = parse_join(cbtype)
    if parsed is None:
        return
    hass.bus.async_fire(
        EVENT_JOIN_RECEIVED,
        {
            "entry_id": entry_id,
            "join": cbtype,
            "join_type": parsed[0],
            "join_number": parsed[1],
            "value": native_join_value(parsed[0], value),
        },
    )


def _async_register_services(hass: HomeAssistant) -> None:
    """Register the join-manipulation services once, shared by all entries."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_DIGITAL):
        return

    def _get_hub(call: ServiceCall) -> CrestronXsigHub:
        """Resolve the target hub. No magic: with more than one processor
        the caller must say which one via entry_id."""
        entries = hass.data.get(DOMAIN, {})
        if not entries:
            raise HomeAssistantError("No Crestron XSIG processor is configured")
        entry_id = call.data.get(CONF_ENTRY_ID) or None
        if entry_id:
            data = entries.get(entry_id)
            if data is None:
                raise HomeAssistantError(
                    f"Unknown Crestron XSIG processor (entry_id {entry_id}). "
                    f"Configured: {', '.join(entries)}"
                )
            return data[DATA_HUB]
        if len(entries) > 1:
            raise HomeAssistantError(
                "More than one Crestron XSIG processor is configured: "
                "fill in the 'Processor' (entry_id) field to choose which "
                "one to talk to."
            )
        return next(iter(entries.values()))[DATA_HUB]

    async def async_set_digital(call: ServiceCall) -> None:
        hub = _get_hub(call)
        if hub:
            hub.set_digital(call.data[CONF_JOIN], call.data[CONF_VALUE])

    async def async_set_analog(call: ServiceCall) -> None:
        hub = _get_hub(call)
        if hub:
            hub.set_analog(call.data[CONF_JOIN], call.data[CONF_VALUE])

    async def async_set_serial(call: ServiceCall) -> None:
        hub = _get_hub(call)
        if hub:
            hub.set_serial(call.data[CONF_JOIN], str(call.data[CONF_VALUE]))

    async def async_reload_connection(call: ServiceCall) -> None:
        entry_id = call.data.get(CONF_ENTRY_ID)
        entries = hass.config_entries.async_entries(DOMAIN)
        if entry_id:
            entries = [entry for entry in entries if entry.entry_id == entry_id]
            if not entries:
                raise HomeAssistantError(
                    f"Unknown Crestron XSIG config entry {entry_id}"
                )
        for entry in entries:
            await hass.config_entries.async_reload(entry.entry_id)

    hass.services.async_register(DOMAIN, SERVICE_SET_DIGITAL, async_set_digital, schema=SET_DIGITAL_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SET_ANALOG, async_set_analog, schema=SET_ANALOG_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SET_SERIAL, async_set_serial, schema=SET_SERIAL_SCHEMA)
    hass.services.async_register(
        DOMAIN,
        SERVICE_RELOAD_CONNECTION,
        async_reload_connection,
        schema=vol.Schema({vol.Optional(CONF_ENTRY_ID): vol.Any(None, cv.string)}),
    )


def _async_unregister_services(hass: HomeAssistant) -> None:
    """Remove shared join services after the last config entry unloads."""
    for service in (
        SERVICE_SET_DIGITAL,
        SERVICE_SET_ANALOG,
        SERVICE_SET_SERIAL,
        SERVICE_RELOAD_CONNECTION,
    ):
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)
