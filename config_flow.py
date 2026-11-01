"""Config flow for Crestron XSIG.

Two flows are implemented:

* ConfigFlow: one-time setup of the TCP connection (port the Crestron
  processor connects to).
* OptionsFlow: add or remove entities (switches, lights, covers, sensors,
  binary sensors, climates, media players) entirely from the UI. Every
  change reloads the config entry automatically (see ``__init__.py``'s
  update listener), no YAML and no restart required.
"""

from __future__ import annotations

import copy
import logging
import uuid
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.selector import selector

from .const import (
    ALL_ENTITY_OPTION_KEYS,
    ALL_OPTION_KEYS,
    BINARY_SENSOR_DEVICE_CLASSES,
    CONF_ATTRIBUTE,
    CONF_BRIGHTNESS_DEFAULT,
    CONF_BRIGHTNESS_JOIN,
    CONF_BLUE_JOIN,
    CONF_GREEN_JOIN,
    CONF_RED_JOIN,
    CONF_BUTTON_JOIN,
    CONF_C1_JOIN,
    CONF_C2_JOIN,
    CONF_CLOSE_JOIN,
    CONF_COOL_SP_JOIN,
    CONF_COVER_TYPE,
    CONF_DEVICE,
    CONF_DEVICE_CLASS,
    CONF_ENTITY_CATEGORY,
    ENTITY_CATEGORY_CONFIG,
    ENTITY_CATEGORY_DIAGNOSTIC,
    ENTITY_CATEGORY_NONE,
    CONF_DIVISOR,
    CONF_ENTITY_ID,
    CONF_FA_JOIN,
    CONF_FAN_AUTO_JOIN,
    CONF_FAN_ON_JOIN,
    CONF_H1_JOIN,
    CONF_H2_JOIN,
    CONF_HEAT_SP_JOIN,
    CONF_HUMIDITY_JOIN,
    CONF_ID,
    CONF_IS_CLOSED_JOIN,
    CONF_IS_CLOSING_JOIN,
    CONF_IS_ON_JOIN,
    CONF_IS_OPENED_JOIN,
    CONF_IS_OPENING_JOIN,
    CONF_JOIN,
    CONF_MANUFACTURER,
    CONF_MAX_TEMP,
    CONF_MAX_VALUE,
    CONF_MIN_TEMP,
    CONF_MIN_VALUE,
    CONF_MODEL,
    CONF_MODE_AUTO_JOIN,
    CONF_MODE_COOL_JOIN,
    CONF_MODE_DRY_JOIN,
    CONF_MODE_FAN_ONLY_JOIN,
    CONF_MODE_HEAT_JOIN,
    CONF_MODE_OFF_JOIN,
    CONF_MUTE_JOIN,
    CONF_MUTE_MODE,
    CONF_NAME,
    CONF_OPEN_JOIN,
    CONF_OPTIMISTIC,
    CONF_POS_JOIN,
    CONF_PORT,
    CONF_POSITION_COMMANDS,
    CONF_PRESETS,
    CONF_REG_TEMP_JOIN,
    CONF_SERIAL_JOIN,
    CONF_SOURCE_NUM_JOIN,
    CONF_SOURCES,
    CONF_STATE_SYNC,
    CONF_STEP,
    CONF_STOP_JOIN,
    CONF_SUGGESTED_AREA,
    CONF_SWITCH_JOIN,
    CONF_TARGET_HUMIDITY_JOIN,
    CONF_TEMP_DIVISOR,
    CONF_TEMP_STEP,
    CONF_TEMP_UNIT,
    MUTE_MODE_SET_STATE,
    MUTE_MODE_TOGGLE_PULSE,
    TEMP_UNIT_HA,
    CONF_HUMIDITY_DIVISOR,
    CONF_SCRIPT,
    CONF_TRIGGER_ON,
    CONF_UNIT_OF_MEASUREMENT,
    CONF_VALUE_JOIN,
    CONF_VALUE_TEMPLATE,
    CONF_VOLUME_DOWN_JOIN,
    CONF_VOLUME_JOIN,
    CONF_VOLUME_UP_JOIN,
    DOMAIN,
    OPT_BINARY_SENSORS,
    OPT_ACTIONS,
    OPT_BUTTONS,
    OPT_CLIMATES,
    OPT_COVERS,
    OPT_DEVICES,
    OPT_EXPOSES,
    OPT_LIGHTS,
    OPT_MEDIA_PLAYERS,
    OPT_NUMBERS,
    OPT_SENSORS,
    OPT_SWITCHES,
    OPT_TEXTS,
    SENSOR_DEVICE_CLASSES,
    SWITCH_DEVICE_CLASSES,
    TRIGGER_ON_OPTIONS,
    TRIGGER_ON_PRESS,
    MAX_ANALOG_JOIN,
    MAX_ANALOG_VALUE,
    MAX_DIGITAL_JOIN,
    MAX_SERIAL_JOIN,
    MIN_ANALOG_VALUE,
    MIN_JOIN,
    DEVICE_REF_PROCESSOR,
    normalize_option_ids,
    custom_device_ref,
    existing_device_ref,
    join_error_key,
)
from . import legacy_import as _legacy_import

_LOGGER = logging.getLogger(__name__)

_HELP_DOCS = {
    OPT_SWITCHES: "switch",
    OPT_LIGHTS: "light",
    OPT_COVERS: "cover",
    OPT_SENSORS: "sensor",
    OPT_BINARY_SENSORS: "binary-sensor",
    OPT_CLIMATES: "climate",
    OPT_MEDIA_PLAYERS: "media-player",
    OPT_TEXTS: "text",
    OPT_NUMBERS: "number",
    OPT_BUTTONS: "button",
    OPT_EXPOSES: "expose",
    OPT_ACTIONS: "action",
}
_HELP_BASE_URL = "https://github.com/morettigiorgio/ha-crestron-xsig/blob/main/docs/help"
_ADD_STEP_OPTION_KEYS = {
    "add_switch": OPT_SWITCHES,
    "add_light": OPT_LIGHTS,
    "add_cover": OPT_COVERS,
    "add_sensor": OPT_SENSORS,
    "add_binary_sensor": OPT_BINARY_SENSORS,
    "add_climate": OPT_CLIMATES,
    "add_media_player": OPT_MEDIA_PLAYERS,
    "add_text": OPT_TEXTS,
    "add_number": OPT_NUMBERS,
    "add_button": OPT_BUTTONS,
    "add_expose": OPT_EXPOSES,
    "add_action": OPT_ACTIONS,
}


def _help_url(option_key: str) -> str:
    """Public GitHub guide for an entity/rule type."""
    slug = _HELP_DOCS.get(option_key, "")
    return f"{_HELP_BASE_URL}/{slug}.md"


def _device_class_options(classes: list[str]):
    """Build the (sorted, human-readable) options list for a select selector."""
    return [{"value": c, "label": c.replace("_", " ").title()} for c in sorted(classes)]


def _device_choices(hass, entry, options: dict) -> list[dict]:
    """Select options for the per-entity "device" field.

    Three kinds of choices: this integration's processor device (the
    default, entities stay attached to the integration), user-defined
    devices created in the options flow, and any other device already
    present in Home Assistant (the entity joins that device).
    """
    choices = [
        {
            "value": DEVICE_REF_PROCESSOR,
            "label": f"Integration device ({entry.title})",
        }
    ]
    for dev in options.get(OPT_DEVICES, []):
        if not dev.get(CONF_ID):
            continue
        choices.append(
            {
                "value": custom_device_ref(dev[CONF_ID]),
                "label": f"Device: {dev.get(CONF_NAME, dev[CONF_ID])}",
            }
        )
    if hass is not None:
        existing = []
        # The registry no longer exposes its full devices mapping. Collect
        # devices through the supported config-entry-scoped API instead.
        device_registry = dr.async_get(hass)
        devices = {
            device.id: device
            for config_entry in hass.config_entries.async_entries()
            for device in dr.async_entries_for_config_entry(
                device_registry, config_entry.entry_id
            )
        }
        for device in devices.values():
            if device.config_entry_id == entry.entry_id:
                continue  # devices of this entry are listed above already
            name = device.name_by_user or device.name or device.id
            existing.append(
                {
                    "value": existing_device_ref(device.id),
                    "label": f"{name} (existing device)",
                }
            )
        existing.sort(key=lambda choice: choice["label"].lower())
        choices.extend(existing)
    return choices


def _device_field(entry, options: dict, item: dict | None = None, hass=None) -> dict:
    """Shared device and entity-category fields for real entities."""
    item = item or {}
    current = item.get(CONF_DEVICE) or DEVICE_REF_PROCESSOR
    choices = _device_choices(hass, entry, options)
    if not any(choice["value"] == current for choice in choices):
        # The assigned device was deleted meanwhile (stale reference):
        # keep it as an option so the form still shows the stored value.
        choices.append({"value": current, "label": "Missing device"})
    category_choices = [
        {"value": ENTITY_CATEGORY_NONE, "label": "None"},
        {"value": ENTITY_CATEGORY_CONFIG, "label": "Configuration"},
        {"value": ENTITY_CATEGORY_DIAGNOSTIC, "label": "Diagnostic"},
    ]
    return {
        vol.Optional(CONF_DEVICE, default=current): selector(
            {"select": {"options": choices, "mode": "dropdown"}}
        ),
        vol.Optional(
            CONF_ENTITY_CATEGORY,
            default=item.get(CONF_ENTITY_CATEGORY, ENTITY_CATEGORY_NONE),
        ): selector({"select": {"options": category_choices, "mode": "dropdown"}}),
    }


def _device_def_schema(hass, item: dict | None = None) -> vol.Schema:
    """Add/edit form for a user-defined device (entity grouping)."""
    item = item or {}
    areas = ar.async_get(hass).areas.values()
    area_options = [
        {"value": area.name, "label": area.name}
        for area in sorted(areas, key=lambda area: area.name.lower())
    ]
    current_area = item.get(CONF_SUGGESTED_AREA)
    if current_area and not any(
        option["value"] == current_area for option in area_options
    ):
        # Keep a previously configured value visible if its area was renamed or
        # removed, so editing the device doesn't silently discard the setting.
        area_options.append(
            {"value": current_area, "label": f"{current_area} (unavailable)"}
        )

    area_field = (
        vol.Optional(CONF_SUGGESTED_AREA, default=current_area)
        if current_area
        else vol.Optional(CONF_SUGGESTED_AREA)
    )
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=item.get(CONF_NAME, "")): cv.string,
            vol.Optional(
                CONF_MANUFACTURER, default=item.get(CONF_MANUFACTURER, "Crestron")
            ): cv.string,
            vol.Optional(CONF_MODEL, default=item.get(CONF_MODEL, "")): cv.string,
            area_field: selector(
                {"select": {"options": area_options, "mode": "dropdown"}}
            ),
        }
    )


def _device_from_form(user_input: dict, device_id: str | None = None) -> dict:
    """Build an OPT_DEVICES definition from the add/edit form data."""
    device = {CONF_ID: device_id or uuid.uuid4().hex, CONF_NAME: user_input[CONF_NAME]}
    for field in (CONF_MANUFACTURER, CONF_MODEL, CONF_SUGGESTED_AREA):
        if user_input.get(field):
            device[field] = user_input[field]
    return device

# Human readable labels for the "add entity" menu / removal list.
_TYPE_LABELS = {
    OPT_SWITCHES: "Switch",
    OPT_LIGHTS: "Light",
    OPT_COVERS: "Cover",
    OPT_SENSORS: "Sensor",
    OPT_BINARY_SENSORS: "Binary sensor",
    OPT_CLIMATES: "Climate",
    OPT_MEDIA_PLAYERS: "Media player",
    OPT_TEXTS: "Text",
    OPT_NUMBERS: "Number",
    OPT_BUTTONS: "Button",
    OPT_EXPOSES: "Expose (HA -> Crestron)",
    OPT_ACTIONS: "Action (Crestron -> HA)",
}


def _expose_fields(item: dict | None = None) -> dict:
    """Fields for the expose (HA -> Crestron) add/edit form.

    join is a typed string ("a101", "d451", "s7"). Exactly one source is
    required: a value_template, or an entity_id (optionally + attribute).
    """
    item = item or {}

    def reqv(field, fallback=None):
        value = item.get(field, fallback)
        return (
            vol.Required(field, default=value)
            if value is not None
            else vol.Required(field)
        )

    def optv(field, fallback=None):
        value = item.get(field, fallback)
        return (
            vol.Optional(field, default=value)
            if value is not None
            else vol.Optional(field)
        )

    fields = {
        reqv(CONF_NAME): cv.string,
        reqv(CONF_JOIN): cv.string,
        optv(CONF_VALUE_TEMPLATE): cv.string,
        optv(CONF_ENTITY_ID): selector({"entity": {}}),
        optv(CONF_ATTRIBUTE): cv.string,
    }
    return fields


# ---------------------------------------------------------------------------
# Submit-time validation of the entity forms (Lotto 2). Every invalid value
# is rejected with a translatable error key (strings.json -> options.error):
# nothing is silently skipped or clamped.
# ---------------------------------------------------------------------------

# Join fields of the entity forms, mapped to the maximum join number of their
# type (XSIG: digital 1..4096, analog/serial 1..1024).
_DIGITAL_JOIN_FIELDS = (
    CONF_SWITCH_JOIN,
    CONF_BUTTON_JOIN,
    CONF_IS_ON_JOIN,
    CONF_OPEN_JOIN,
    CONF_CLOSE_JOIN,
    CONF_STOP_JOIN,
    CONF_IS_OPENING_JOIN,
    CONF_IS_CLOSING_JOIN,
    CONF_IS_CLOSED_JOIN,
    CONF_IS_OPENED_JOIN,
    CONF_MUTE_JOIN,
    CONF_VOLUME_UP_JOIN,
    CONF_VOLUME_DOWN_JOIN,
    CONF_MODE_HEAT_JOIN,
    CONF_MODE_COOL_JOIN,
    CONF_MODE_AUTO_JOIN,
    CONF_MODE_OFF_JOIN,
    CONF_MODE_FAN_ONLY_JOIN,
    CONF_MODE_DRY_JOIN,
    CONF_FAN_ON_JOIN,
    CONF_FAN_AUTO_JOIN,
    CONF_H1_JOIN,
    CONF_H2_JOIN,
    CONF_C1_JOIN,
    CONF_C2_JOIN,
    CONF_FA_JOIN,
)
_ANALOG_JOIN_FIELDS = (
    CONF_POS_JOIN,
    CONF_BRIGHTNESS_JOIN,
    CONF_RED_JOIN,
    CONF_GREEN_JOIN,
    CONF_BLUE_JOIN,
    CONF_VOLUME_JOIN,
    CONF_SOURCE_NUM_JOIN,
    CONF_VALUE_JOIN,
    CONF_REG_TEMP_JOIN,
    CONF_HEAT_SP_JOIN,
    CONF_COOL_SP_JOIN,
    CONF_HUMIDITY_JOIN,
    CONF_TARGET_HUMIDITY_JOIN,
)
_SERIAL_JOIN_FIELDS = (CONF_SERIAL_JOIN,)

_JOIN_LIMITS = {
    **dict.fromkeys(_DIGITAL_JOIN_FIELDS, MAX_DIGITAL_JOIN),
    **dict.fromkeys(_ANALOG_JOIN_FIELDS, MAX_ANALOG_JOIN),
    **dict.fromkeys(_SERIAL_JOIN_FIELDS, MAX_SERIAL_JOIN),
}


def _is_blank(value) -> bool:
    """True for the empty values an untouched/optional form field sends."""
    return value is None or (isinstance(value, str) and not value.strip())


def _join_field_error(value, maximum: int) -> str | None:
    """Error key for a numeric join field of the forms (None when valid)."""
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return "invalid_join"
    if number < MIN_JOIN or number > maximum:
        return "join_out_of_range"
    return None


def _divisor_error(value, minimum: float) -> str | None:
    """Error key for a divisor field (None when valid)."""
    try:
        divisor = float(value)
    except (TypeError, ValueError):
        return "invalid_divisor"
    return "invalid_divisor" if divisor < minimum else None


def _brightness_default_error(value) -> str | None:
    """Error key for a light's default brightness (None when valid)."""
    if isinstance(value, bool):
        return "brightness_out_of_range"
    try:
        brightness = float(value)
    except (TypeError, ValueError):
        return "brightness_out_of_range"
    if not brightness.is_integer() or not 0 <= brightness <= 255:
        return "brightness_out_of_range"
    return None


def _number_range_error(data: dict) -> str | None:
    """Error key for the number entity range fields (None when valid)."""
    values: dict[str, float] = {}
    try:
        for field, fallback in (
            (CONF_MIN_VALUE, MIN_ANALOG_VALUE),
            (CONF_MAX_VALUE, MAX_ANALOG_VALUE),
            (CONF_STEP, 1),
        ):
            raw = data.get(field)
            values[field] = float(fallback) if _is_blank(raw) else float(raw)
    except (TypeError, ValueError):
        return "invalid_number_range"
    min_value, max_value, step = (
        values[CONF_MIN_VALUE],
        values[CONF_MAX_VALUE],
        values[CONF_STEP],
    )
    if not all(value.is_integer() for value in values.values()):
        return "invalid_number_range"
    if step < 1 or max_value <= min_value:
        return "invalid_number_range"
    if min_value < MIN_ANALOG_VALUE or max_value > MAX_ANALOG_VALUE:
        return "value_out_of_range"
    return None


def _name_join_map_error(raw: str, maximum: int, format_key: str) -> str | None:
    """Error key for a "Name:join" free text field (climate presets).

    Empty entries ("Home:21,,Away:13") are tolerated as formatting; every
    non-empty entry must be a valid join of the given type.
    """
    for part in str(raw).split(","):
        part = part.strip()
        if not part:
            continue
        name, sep, join = part.partition(":")
        if not sep or not name.strip():
            return format_key
        error = _join_field_error(join, maximum)
        if error:
            return error if error == "join_out_of_range" else format_key
    return None


def _sources_error(raw: str) -> str | None:
    """Error key for the media player "number:name" free text field.

    The numbers are the analog values sent to the source join, so they must
    fit the XSIG analog range 0..65535.
    """
    for part in str(raw).split(","):
        part = part.strip()
        if not part:
            continue
        num, sep, name = part.partition(":")
        if not sep or not name.strip():
            return "invalid_sources"
        try:
            value = int(num.strip())
        except (TypeError, ValueError):
            return "invalid_sources"
        if value < MIN_ANALOG_VALUE or value > MAX_ANALOG_VALUE:
            return "value_out_of_range"
    return None


def _validate_entity_form(key: str, data: dict) -> str | None:
    """Return an error key if the entity form data is invalid (None = ok).

    Runs at submit time for every add/edit form, so the user always sees
    what is wrong instead of an invalid value reaching entry.options.
    """
    for field, maximum in _JOIN_LIMITS.items():
        if not _is_blank(data.get(field)):
            error = _join_field_error(data[field], maximum)
            if error:
                return error
    if key == OPT_EXPOSES:
        return _validate_expose(data)
    if key == OPT_ACTIONS:
        return join_error_key(data.get(CONF_JOIN, ""))
    if not _is_blank(data.get(CONF_DIVISOR)):
        error = _divisor_error(data[CONF_DIVISOR], 1)  # int divisor, >= 1
        if error:
            return error
    for field in (CONF_TEMP_DIVISOR, CONF_HUMIDITY_DIVISOR):
        if not _is_blank(data.get(field)):
            error = _divisor_error(data[field], 0.1)  # float divisor, > 0
            if error:
                return error
    if key == OPT_CLIMATES and not _is_blank(data.get(CONF_TEMP_UNIT)):
        if data[CONF_TEMP_UNIT] not in (TEMP_UNIT_HA, "C", "F"):
            return "invalid_temp_unit"
    if key == OPT_MEDIA_PLAYERS and not _is_blank(data.get(CONF_MUTE_MODE)):
        if data[CONF_MUTE_MODE] not in (
            MUTE_MODE_TOGGLE_PULSE,
            MUTE_MODE_SET_STATE,
        ):
            return "invalid_mute_mode"
    if key == OPT_LIGHTS:
        rgb_joins = (
            data.get(CONF_RED_JOIN),
            data.get(CONF_GREEN_JOIN),
            data.get(CONF_BLUE_JOIN),
        )
        if any(not _is_blank(join) for join in rgb_joins) and not all(
            not _is_blank(join) for join in rgb_joins
        ):
            return "rgb_joins_incomplete"
        light_joins = [
            int(data[field])
            for field in (
                CONF_BRIGHTNESS_JOIN,
                CONF_RED_JOIN,
                CONF_GREEN_JOIN,
                CONF_BLUE_JOIN,
            )
            if not _is_blank(data.get(field))
        ]
        if len(light_joins) != len(set(light_joins)):
            return "duplicate_light_joins"
        if not _is_blank(data.get(CONF_BRIGHTNESS_DEFAULT)):
            error = _brightness_default_error(data[CONF_BRIGHTNESS_DEFAULT])
            if error:
                return error
    if key == OPT_NUMBERS:
        error = _number_range_error(data)
        if error:
            return error
    if not _is_blank(data.get("presets_text")):
        # Preset modes pulse digital joins (see climate.py).
        error = _name_join_map_error(
            data["presets_text"], MAX_DIGITAL_JOIN, "invalid_presets"
        )
        if error:
            return error
    if not _is_blank(data.get("sources_text")):
        return _sources_error(data["sources_text"])
    return None


def _validate_expose(data: dict) -> str | None:
    """Return an error key if the expose form data is incomplete/invalid."""
    if not data.get(CONF_JOIN):
        return "missing_join"
    error = join_error_key(data[CONF_JOIN])
    if error:
        return error
    if not data.get(CONF_VALUE_TEMPLATE) and not data.get(CONF_ENTITY_ID):
        return "missing_source"
    return None


def _script_default(item: dict) -> list:
    """Return a normalized action list for the form default value."""
    script = item.get(CONF_SCRIPT) or []
    if isinstance(script, dict):
        return [script]
    if isinstance(script, list):
        return script
    return []


def _action_fields(item: dict | None = None) -> dict:
    """Fields for the action (Crestron -> HA) add/edit form."""
    item = item or {}
    return {
        vol.Required(
            CONF_NAME, default=item.get(CONF_NAME, "")
        ): cv.string,
        vol.Required(
            CONF_JOIN, default=item.get(CONF_JOIN, "")
        ): cv.string,
        vol.Required(
            CONF_TRIGGER_ON,
            default=item.get(CONF_TRIGGER_ON, TRIGGER_ON_PRESS),
        ): selector(
            {
                "select": {
                    "options": [
                        {"value": t, "label": t} for t in TRIGGER_ON_OPTIONS
                    ]
                }
            }
        ),
        vol.Required(
            CONF_SCRIPT, default=_script_default(item)
        ): selector({"action": {}}),
    }


def _parse_name_join_map(raw: str) -> dict[str, int]:
    """Parse validated climate preset pairs; log malformed parts defensively."""
    result: dict[str, int] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        name, separator, join = part.partition(":")
        if not separator or not name.strip():
            _LOGGER.warning("Skipping malformed climate preset %r", part)
            continue
        try:
            result[name.strip()] = int(join.strip())
        except ValueError:
            _LOGGER.warning("Skipping climate preset with invalid join %r", part)
    return result


def _parse_sources(raw: str) -> dict[int, str]:
    """Parse validated media-player source pairs; log malformed parts."""
    sources: dict[int, str] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        number, separator, name = part.partition(":")
        if not separator or not name.strip():
            _LOGGER.warning("Skipping malformed media-player source %r", part)
            continue
        try:
            sources[int(number.strip())] = name.strip()
        except ValueError:
            _LOGGER.warning("Skipping media-player source with invalid number %r", part)
    return sources


def _cover_schema(item: dict | None = None, device_field: dict | None = None) -> vol.Schema:
    """Cover form: only the name is required. All joins are optional so
    digital pulses, analog position and feedback can be combined
    freely; directions are spelled out in the field labels."""
    item = item or {}

    def opt(field, fallback=None):
        value = item.get(field, fallback)
        return (
            vol.Optional(field, default=value)
            if value is not None
            else vol.Optional(field)
        )

    name = item.get(CONF_NAME)
    name_marker = (
        vol.Required(CONF_NAME, default=name)
        if name is not None
        else vol.Required(CONF_NAME)
    )
    return vol.Schema(
        {
            **(device_field or {}),
            name_marker: cv.string,
            opt(CONF_COVER_TYPE): selector(
                {"select": {"options": ["shade", "blind", "curtain", "generic"]}}
            ),
            opt(CONF_POS_JOIN): cv.positive_int,
            opt(CONF_OPEN_JOIN): cv.positive_int,
            opt(CONF_CLOSE_JOIN): cv.positive_int,
            opt(CONF_STOP_JOIN): cv.positive_int,
            opt(CONF_IS_OPENING_JOIN): cv.positive_int,
            opt(CONF_IS_CLOSING_JOIN): cv.positive_int,
            opt(CONF_IS_CLOSED_JOIN): cv.positive_int,
            opt(CONF_IS_OPENED_JOIN): cv.positive_int,
            vol.Optional(
                CONF_POSITION_COMMANDS,
                default=item.get(CONF_POSITION_COMMANDS, False),
            ): cv.boolean,
            vol.Optional(
                CONF_OPTIMISTIC, default=item.get(CONF_OPTIMISTIC, False)
            ): cv.boolean,
        }
    )


def _climate_schema(item: dict | None = None, device_field: dict | None = None) -> vol.Schema:
    """Climate form: only the name and the current temperature join are
    required. Setpoints (one = single setpoint, two = range), modes,
    fan, stages, humidity and presets are all optional."""
    item = item or {}

    def opt(field, fallback=None):
        value = item.get(field, fallback)
        return (
            vol.Optional(field, default=value)
            if value is not None
            else vol.Optional(field)
        )

    name = item.get(CONF_NAME)
    reg = item.get(CONF_REG_TEMP_JOIN)
    presets_text = item.get("presets_text") or ",".join(
        f"{name}:{join}" for name, join in (item.get(CONF_PRESETS) or {}).items()
    )
    temp_unit = item.get(CONF_TEMP_UNIT, TEMP_UNIT_HA)
    if temp_unit not in (TEMP_UNIT_HA, "C", "F"):
        temp_unit = TEMP_UNIT_HA
    return vol.Schema(
        {
            **(device_field or {}),
            (
                vol.Required(CONF_NAME, default=name)
                if name is not None
                else vol.Required(CONF_NAME)
            ): cv.string,
            (
                vol.Required(CONF_REG_TEMP_JOIN, default=reg)
                if reg is not None
                else vol.Required(CONF_REG_TEMP_JOIN)
            ): cv.positive_int,
            opt(CONF_HEAT_SP_JOIN): cv.positive_int,
            opt(CONF_COOL_SP_JOIN): cv.positive_int,
            opt(CONF_TEMP_DIVISOR, fallback=10): vol.Coerce(float),
            vol.Optional(CONF_TEMP_UNIT, default=temp_unit): selector(
                {
                    "select": {
                        "options": [
                            {"value": TEMP_UNIT_HA, "label": "Home Assistant unit"},
                            {"value": "C", "label": "Celsius (°C)"},
                            {"value": "F", "label": "Fahrenheit (°F)"},
                        ],
                        "mode": "dropdown",
                    }
                }
            ),
            opt(CONF_HUMIDITY_DIVISOR, fallback=1): vol.Coerce(float),
            opt(CONF_MIN_TEMP): vol.Coerce(float),
            opt(CONF_MAX_TEMP): vol.Coerce(float),
            opt(CONF_TEMP_STEP): vol.Coerce(float),
            opt(CONF_MODE_HEAT_JOIN): cv.positive_int,
            opt(CONF_MODE_COOL_JOIN): cv.positive_int,
            opt(CONF_MODE_AUTO_JOIN): cv.positive_int,
            opt(CONF_MODE_OFF_JOIN): cv.positive_int,
            opt(CONF_MODE_FAN_ONLY_JOIN): cv.positive_int,
            opt(CONF_MODE_DRY_JOIN): cv.positive_int,
            opt(CONF_FAN_ON_JOIN): cv.positive_int,
            opt(CONF_FAN_AUTO_JOIN): cv.positive_int,
            opt(CONF_H1_JOIN): cv.positive_int,
            opt(CONF_H2_JOIN): cv.positive_int,
            opt(CONF_C1_JOIN): cv.positive_int,
            opt(CONF_C2_JOIN): cv.positive_int,
            opt(CONF_FA_JOIN): cv.positive_int,
            opt(CONF_HUMIDITY_JOIN): cv.positive_int,
            opt(CONF_TARGET_HUMIDITY_JOIN): cv.positive_int,
            vol.Optional("presets_text", default=presets_text): cv.string,
        }
    )


def _edit_schema(key: str, item: dict, device_field: dict | None = None) -> vol.Schema:
    """Build the edit form for an existing entity, pre-filled with its
    current values. The stable ``CONF_ID`` is never part of the form."""

    def req(field, fallback=None):
        value = item.get(field, fallback)
        return (
            vol.Required(field, default=value)
            if value is not None
            else vol.Required(field)
        )

    def opt(field, fallback=None):
        value = item.get(field, fallback)
        return (
            vol.Optional(field, default=value)
            if value is not None
            else vol.Optional(field)
        )

    def dev_select(classes):
        return selector(
            {
                "select": {
                    "options": _device_class_options(classes),
                    "mode": "dropdown",
                }
            }
        )

    if key == OPT_SWITCHES:
        fields = {
            req(CONF_NAME): cv.string,
            req(CONF_SWITCH_JOIN): cv.positive_int,
            opt(CONF_DEVICE_CLASS): dev_select(SWITCH_DEVICE_CLASSES),
            opt(CONF_OPTIMISTIC, fallback=False): cv.boolean,
            opt(CONF_STATE_SYNC, fallback=False): cv.boolean,
        }
    elif key == OPT_LIGHTS:
        fields = {
            req(CONF_NAME): cv.string,
            req(CONF_BRIGHTNESS_JOIN): cv.positive_int,
            opt(CONF_BRIGHTNESS_DEFAULT, fallback=128): selector(
                {"number": {"min": 0, "max": 255, "step": 1, "mode": "box"}}
            ),
            opt(CONF_RED_JOIN): cv.positive_int,
            opt(CONF_GREEN_JOIN): cv.positive_int,
            opt(CONF_BLUE_JOIN): cv.positive_int,
            opt(CONF_OPTIMISTIC, fallback=False): cv.boolean,
        }
    elif key == OPT_COVERS:
        return _cover_schema(item, device_field)
    elif key == OPT_SENSORS:
        fields = {
            req(CONF_NAME): cv.string,
            req(CONF_VALUE_JOIN): cv.positive_int,
            opt(CONF_DEVICE_CLASS): dev_select(SENSOR_DEVICE_CLASSES),
            opt(CONF_UNIT_OF_MEASUREMENT): cv.string,
            opt(CONF_DIVISOR, fallback=1): cv.positive_int,
        }
    elif key == OPT_BINARY_SENSORS:
        fields = {
            req(CONF_NAME): cv.string,
            req(CONF_IS_ON_JOIN): cv.positive_int,
            opt(CONF_DEVICE_CLASS): dev_select(BINARY_SENSOR_DEVICE_CLASSES),
        }
    elif key == OPT_CLIMATES:
        return _climate_schema(item, device_field)
    elif key == OPT_TEXTS:
        fields = {
            req(CONF_NAME): cv.string,
            req(CONF_SERIAL_JOIN): cv.positive_int,
            opt(CONF_OPTIMISTIC, fallback=True): cv.boolean,
        }
    elif key == OPT_NUMBERS:
        fields = {
            req(CONF_NAME): cv.string,
            req(CONF_VALUE_JOIN): cv.positive_int,
            opt(CONF_MIN_VALUE, fallback=0): vol.Coerce(float),
            opt(CONF_MAX_VALUE, fallback=65535): vol.Coerce(float),
            opt(CONF_STEP, fallback=1): vol.Coerce(float),
            opt(CONF_UNIT_OF_MEASUREMENT): cv.string,
            opt(CONF_OPTIMISTIC, fallback=True): cv.boolean,
        }
    elif key == OPT_MEDIA_PLAYERS:
        mute_mode_default = item.get(CONF_MUTE_MODE, MUTE_MODE_TOGGLE_PULSE)
        if mute_mode_default not in (MUTE_MODE_TOGGLE_PULSE, MUTE_MODE_SET_STATE):
            mute_mode_default = MUTE_MODE_TOGGLE_PULSE
        sources_text = item.get("sources_text") or ",".join(
            f"{num}:{name}" for num, name in (item.get(CONF_SOURCES) or {}).items()
        )
        fields = {
            req(CONF_NAME): cv.string,
            req(CONF_MUTE_JOIN): cv.positive_int,
            vol.Optional(CONF_MUTE_MODE, default=mute_mode_default): selector(
                {
                    "select": {
                        "options": [
                            {
                                "value": MUTE_MODE_TOGGLE_PULSE,
                                "label": "Toggle pulse",
                            },
                            {
                                "value": MUTE_MODE_SET_STATE,
                                "label": "Set requested state",
                            },
                        ],
                        "mode": "dropdown",
                    }
                }
            ),
            req(CONF_VOLUME_UP_JOIN): cv.positive_int,
            req(CONF_VOLUME_DOWN_JOIN): cv.positive_int,
            req(CONF_VOLUME_JOIN): cv.positive_int,
            req(CONF_SOURCE_NUM_JOIN): cv.positive_int,
            vol.Required("sources_text", default=sources_text): cv.string,
        }
    elif key == OPT_BUTTONS:
        fields = {
            req(CONF_NAME): cv.string,
            req(CONF_BUTTON_JOIN): cv.positive_int,
        }
    elif key == OPT_EXPOSES:
        fields = _expose_fields(item)
    elif key == OPT_ACTIONS:
        fields = _action_fields(item)
    else:
        fields = {}
    if key not in (OPT_EXPOSES, OPT_ACTIONS):
        fields.update(device_field or {})
    return vol.Schema(fields)


class CrestronXsigConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial connection setup."""

    VERSION = 2

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(f"{DOMAIN}_{user_input[CONF_PORT]}")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"Crestron ({user_input[CONF_PORT]})", data=user_input
            )

        schema = vol.Schema({vol.Required(CONF_PORT, default=49200): cv.port})
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reconfigure(self, user_input=None):
        """Change the listener port without replacing the config entry."""
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            return self.async_update_reload_and_abort(
                entry, data_updates={CONF_PORT: user_input[CONF_PORT]}
            )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_PORT, default=entry.data.get(CONF_PORT, 49200)
                ): cv.port
            }
        )
        return self.async_show_form(step_id="reconfigure", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        # HA 2024.11+: config_entry is provided as an OptionsFlow property.
        return CrestronXsigOptionsFlow()


class CrestronXsigOptionsFlow(config_entries.OptionsFlow):
    """Add / remove entities backed by this Crestron processor."""

    def __init__(self, config_entry: config_entries.ConfigEntry | None = None):
        super().__init__()
        # The optional fallback is only for standalone flow tooling; Home
        # Assistant supplies self.config_entry on supported versions.
        self._entry_fallback = config_entry
        self._options: dict[str, list] = {}
        self._options_loaded = False
        if config_entry is not None:
            # Used by standalone flow tooling; HA binds config_entry after
            # construction, so production initialization is lazy.
            self._load_options()
        self._pending: dict | None = None   # partial cover def between steps
        self._edit_key: str | None = None   # option key of the entity being edited
        self._edit_item: dict | None = None
        self._edit_device_id: str | None = None
        self._imported: _legacy_import.LegacyImportResult | None = None
        self._imported_port_mismatch: bool = False
        self._import_overwrite: bool = False

    @property
    def _entry(self):
        """Use the modern OptionsFlow property, with a tooling-only fallback."""
        try:
            return self.config_entry
        except AttributeError:
            return self._entry_fallback

    def _load_options(self) -> None:
        """Load the snapshot once the framework has bound config_entry."""
        if self._options_loaded:
            return
        entry = self._entry
        self._options = {
            key: copy.deepcopy(entry.options.get(key, []))
            for key in ALL_OPTION_KEYS + [OPT_DEVICES]
        }
        repaired = normalize_option_ids(self._options)
        if repaired:
            _LOGGER.warning(
                "Generated %s missing option IDs in config flow snapshot for %s",
                repaired,
                entry.entry_id,
            )
        self._options_loaded = True

    def _commit_options(self, mutation) -> config_entries.FlowResult:
        """Apply one targeted options mutation against the latest stored data."""
        options = copy.deepcopy(dict(self._entry.options))
        for key in ALL_OPTION_KEYS + [OPT_DEVICES]:
            options.setdefault(key, [])
        repaired = normalize_option_ids(options)
        if repaired:
            _LOGGER.warning(
                "Generated %s missing option IDs while saving config entry %s",
                repaired,
                self._entry.entry_id,
            )
        mutation(options)
        self._options = options
        return self.async_create_entry(title="", data=options)

    # ------------------------------------------------------------------
    # Menu
    # ------------------------------------------------------------------
    async def async_step_init(self, user_input=None):
        self._load_options()
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "add_switch",
                "add_light",
                "add_cover",
                "add_sensor",
                "add_binary_sensor",
                "add_climate",
                "add_media_player",
                "add_text",
                "add_number",
                "add_button",
                "add_expose",
                "add_action",
                "import_legacy",
                "edit_entity",
                "remove_entity",
                "manage_devices",
            ],
        )

    def _save(self, key: str, entry: dict) -> config_entries.FlowResult:
        entry[CONF_ID] = uuid.uuid4().hex
        if entry.get(CONF_ENTITY_CATEGORY) == ENTITY_CATEGORY_NONE:
            entry.pop(CONF_ENTITY_CATEGORY, None)
        return self._commit_options(lambda options: options[key].append(entry))

    def _show_form_error(
        self, step_id: str, key: str, user_input: dict, error: str
    ) -> config_entries.FlowResult:
        """Re-show a form with the submitted values and a translatable error
        (error key resolved from options.error in strings.json)."""
        return self._show_add_form(
            step_id,
            _edit_schema(key, user_input, self._dev_field(user_input)),
            errors={"base": error},
        )

    def _show_add_form(
        self,
        step_id: str,
        data_schema: vol.Schema,
        *,
        errors: dict[str, str] | None = None,
    ) -> config_entries.FlowResult:
        """Show an Add form with its type-specific external help URL."""
        kwargs = {
            "step_id": step_id,
            "data_schema": data_schema,
            "description_placeholders": {
                "help_url": _help_url(_ADD_STEP_OPTION_KEYS[step_id])
            },
        }
        if errors is not None:
            kwargs["errors"] = errors
        return self.async_show_form(**kwargs)

    def _dev_field(self, item: dict | None = None) -> dict:
        """Shared device and category fields for entity add/edit forms."""
        return _device_field(
            self._entry, self._options, item, getattr(self, "hass", None)
        )

    def _import_confirm_schema(self) -> vol.Schema:
        """Confirmation selector, preserving the choice from the YAML form."""
        return vol.Schema(
            {vol.Required("overwrite", default=self._import_overwrite): cv.boolean}
        )

    def _import_confirm_placeholders(self) -> dict[str, str]:
        """Always provide all placeholders used by the confirmation form."""
        result = self._imported
        if result is None:
            return {
                "exposes": "0",
                "actions": "0",
                "warnings": "No import data is available. Start the import again.",
                "port_note": "",
            }
        return {
            "exposes": str(len(result.exposes)),
            "actions": str(len(result.actions)),
            "warnings": "\n".join(result.warnings) if result.warnings else "None",
            "port_note": (
                f"The file says port {result.port}, but this entry uses "
                f"{self._entry.data.get(CONF_PORT)}. The port is NOT imported "
                "automatically; change it in the initial setup if needed."
                if self._imported_port_mismatch
                else ""
            ),
        }

    # ------------------------------------------------------------------
    # Add: Switch
    # ------------------------------------------------------------------
    async def async_step_add_switch(self, user_input=None):
        if user_input is not None:
            error = _validate_entity_form(OPT_SWITCHES, user_input)
            if error:
                return self._show_form_error(
                    "add_switch", OPT_SWITCHES, user_input, error
                )
            return self._save(OPT_SWITCHES, user_input)
        schema = vol.Schema(
            {
                **self._dev_field(),
                vol.Required(CONF_NAME): cv.string,
                vol.Required(CONF_SWITCH_JOIN): cv.positive_int,
                vol.Optional(CONF_DEVICE_CLASS, default="switch"): selector(
                    {"select": {"options": _device_class_options(SWITCH_DEVICE_CLASSES), "mode": "dropdown"}}
                ),
                vol.Optional(CONF_OPTIMISTIC, default=False): cv.boolean,
                vol.Optional(CONF_STATE_SYNC, default=False): cv.boolean,
            }
        )
        return self._show_add_form("add_switch", schema)

    # ------------------------------------------------------------------
    # Add: Expose (HA -> Crestron bridge rule, legacy "to_joins")
    # ------------------------------------------------------------------
    async def async_step_add_expose(self, user_input=None):
        if user_input is not None:
            error = _validate_expose(user_input)
            if error:
                return self._show_add_form(
                    "add_expose",
                    vol.Schema(_expose_fields(user_input)),
                    errors={"base": error},
                )
            return self._save(OPT_EXPOSES, user_input)
        return self._show_add_form(
            "add_expose", vol.Schema(_expose_fields())
        )

    # ------------------------------------------------------------------
    # Add: Action (Crestron -> HA bridge rule, legacy "from_joins")
    # ------------------------------------------------------------------
    async def async_step_add_action(self, user_input=None):
        if user_input is not None:
            error = join_error_key(user_input.get("join", ""))
            if error:
                return self._show_add_form(
                    "add_action",
                    vol.Schema(_action_fields(user_input)),
                    errors={"base": error},
                )
            return self._save(OPT_ACTIONS, user_input)
        return self._show_add_form(
            "add_action", vol.Schema(_action_fields())
        )

    # ------------------------------------------------------------------
    # Import legacy crestron.yaml (to_joins / from_joins)
    # ------------------------------------------------------------------
    async def async_step_import_legacy(self, user_input=None):
        if user_input is not None:
            self._import_overwrite = bool(user_input.get("overwrite", False))
            self._imported = None
            self._imported_port_mismatch = False
            text = user_input.get("yaml_text", "")
            result = await self.hass.async_add_executor_job(
                _legacy_import.map_legacy_yaml, text
            )
            if result.error:
                return self.async_show_form(
                    step_id="import_legacy",
                    errors={"base": "invalid_legacy_yaml"},
                    data_schema=vol.Schema(
                        {
                            vol.Required(
                                "yaml_text", default=user_input.get("yaml_text", "")
                            ): cv.string,
                            vol.Required(
                                "overwrite", default=self._import_overwrite
                            ): cv.boolean,
                        }
                    ),
                    description_placeholders={"error": result.error},
                )
            if not result.exposes and not result.actions:
                return self.async_abort(reason="no_rules_found")

            self._imported = result
            self._imported_port_mismatch = (
                result.port is not None
                and result.port != self._entry.data.get(CONF_PORT)
            )
            return self.async_show_form(
                step_id="import_confirm",
                data_schema=self._import_confirm_schema(),
                description_placeholders=self._import_confirm_placeholders(),
            )
        return self.async_show_form(
            step_id="import_legacy",
            data_schema=vol.Schema(
                {
                    vol.Required("yaml_text"): cv.string,
                    vol.Required("overwrite", default=False): cv.boolean,
                }
            ),
        )

    async def async_step_import_confirm(self, user_input=None):
        result = self._imported
        if result is None:
            if user_input is not None:
                return self.async_abort(reason="import_cancelled")
            return self.async_show_form(
                step_id="import_confirm",
                data_schema=self._import_confirm_schema(),
                description_placeholders=self._import_confirm_placeholders(),
            )
        if user_input is None:
            return self.async_show_form(
                step_id="import_confirm",
                data_schema=self._import_confirm_schema(),
                description_placeholders=self._import_confirm_placeholders(),
            )

        overwrite = user_input.get("overwrite", self._import_overwrite)

        def apply_import(options):
            if overwrite:
                options[OPT_EXPOSES] = copy.deepcopy(result.exposes)
                options[OPT_ACTIONS] = copy.deepcopy(result.actions)
                return
            # Stable legacy IDs make a repeated import idempotent rather than
            # creating duplicate entity-registry unique_ids.
            for key, imported in (
                (OPT_EXPOSES, result.exposes),
                (OPT_ACTIONS, result.actions),
            ):
                known_ids = {item.get(CONF_ID) for item in options[key]}
                options[key].extend(
                    copy.deepcopy(item)
                    for item in imported
                    if item.get(CONF_ID) not in known_ids
                )

        return self._commit_options(apply_import)

    # ------------------------------------------------------------------
    # Add: Light
    # ------------------------------------------------------------------
    async def async_step_add_light(self, user_input=None):
        if user_input is not None:
            error = _validate_entity_form(OPT_LIGHTS, user_input)
            if error:
                return self._show_form_error("add_light", OPT_LIGHTS, user_input, error)
            if CONF_BRIGHTNESS_DEFAULT in user_input:
                user_input[CONF_BRIGHTNESS_DEFAULT] = int(
                    user_input[CONF_BRIGHTNESS_DEFAULT]
                )
            return self._save(OPT_LIGHTS, user_input)
        schema = vol.Schema(
            {
                **self._dev_field(),
                vol.Required(CONF_NAME): cv.string,
                vol.Required(CONF_BRIGHTNESS_JOIN): cv.positive_int,
                vol.Optional(CONF_BRIGHTNESS_DEFAULT, default=128): selector(
                    {"number": {"min": 0, "max": 255, "step": 1, "mode": "box"}}
                ),
                vol.Optional(CONF_RED_JOIN): cv.positive_int,
                vol.Optional(CONF_GREEN_JOIN): cv.positive_int,
                vol.Optional(CONF_BLUE_JOIN): cv.positive_int,
                vol.Optional(CONF_OPTIMISTIC, default=False): cv.boolean,
            }
        )
        return self._show_add_form("add_light", schema)

    # ------------------------------------------------------------------
    # Add: Cover (single form: only the name is required, all joins
    # optional so pulses / position / feedback can be combined freely)
    # ------------------------------------------------------------------
    async def async_step_add_cover(self, user_input=None):
        if user_input is not None:
            error = _validate_entity_form(OPT_COVERS, user_input)
            if error:
                return self._show_form_error("add_cover", OPT_COVERS, user_input, error)
            return self._save(OPT_COVERS, user_input)
        return self._show_add_form(
            "add_cover",
            _cover_schema(device_field=self._dev_field()),
        )

    # ------------------------------------------------------------------
    # Add: Sensor
    # ------------------------------------------------------------------
    async def async_step_add_sensor(self, user_input=None):
        if user_input is not None:
            error = _validate_entity_form(OPT_SENSORS, user_input)
            if error:
                return self._show_form_error(
                    "add_sensor", OPT_SENSORS, user_input, error
                )
            return self._save(OPT_SENSORS, user_input)
        schema = vol.Schema(
            {
                **self._dev_field(),
                vol.Required(CONF_NAME): cv.string,
                vol.Required(CONF_VALUE_JOIN): cv.positive_int,
                vol.Optional(CONF_DEVICE_CLASS): selector(
                    {"select": {"options": _device_class_options(SENSOR_DEVICE_CLASSES), "mode": "dropdown"}}
                ),
                vol.Optional(CONF_UNIT_OF_MEASUREMENT): cv.string,
                vol.Optional(CONF_DIVISOR, default=1): cv.positive_int,
            }
        )
        return self._show_add_form("add_sensor", schema)

    # ------------------------------------------------------------------
    # Add: Binary sensor
    # ------------------------------------------------------------------
    async def async_step_add_binary_sensor(self, user_input=None):
        if user_input is not None:
            error = _validate_entity_form(OPT_BINARY_SENSORS, user_input)
            if error:
                return self._show_form_error(
                    "add_binary_sensor", OPT_BINARY_SENSORS, user_input, error
                )
            return self._save(OPT_BINARY_SENSORS, user_input)
        schema = vol.Schema(
            {
                **self._dev_field(),
                vol.Required(CONF_NAME): cv.string,
                vol.Required(CONF_IS_ON_JOIN): cv.positive_int,
                vol.Optional(CONF_DEVICE_CLASS): selector(
                    {"select": {"options": _device_class_options(BINARY_SENSOR_DEVICE_CLASSES), "mode": "dropdown"}}
                ),
            }
        )
        return self._show_add_form("add_binary_sensor", schema)

    # ------------------------------------------------------------------
    # Add: Climate
    # ------------------------------------------------------------------
    async def async_step_add_climate(self, user_input=None):
        if user_input is not None:
            error = _validate_entity_form(OPT_CLIMATES, user_input)
            if error:
                return self._show_form_error(
                    "add_climate", OPT_CLIMATES, user_input, error
                )
            user_input[CONF_PRESETS] = _parse_name_join_map(
                user_input.pop("presets_text", "")
            )
            return self._save(OPT_CLIMATES, user_input)
        return self._show_add_form(
            "add_climate",
            _climate_schema(device_field=self._dev_field()),
        )

    # ------------------------------------------------------------------
    # Add: Media player
    # ------------------------------------------------------------------
    async def async_step_add_media_player(self, user_input=None):
        if user_input is not None:
            error = _validate_entity_form(OPT_MEDIA_PLAYERS, user_input)
            if error:
                return self._show_form_error(
                    "add_media_player", OPT_MEDIA_PLAYERS, user_input, error
                )
            # sources are entered as free text "1:TV,2:Radio,3:AppleTV"
            user_input[CONF_SOURCES] = _parse_sources(
                user_input.pop("sources_text", "")
            )
            return self._save(OPT_MEDIA_PLAYERS, user_input)

        schema = vol.Schema(
            {
                **self._dev_field(),
                vol.Required(CONF_NAME): cv.string,
                vol.Required(CONF_MUTE_JOIN): cv.positive_int,
                vol.Optional(
                    CONF_MUTE_MODE, default=MUTE_MODE_TOGGLE_PULSE
                ): selector(
                    {
                        "select": {
                            "options": [
                                {
                                    "value": MUTE_MODE_TOGGLE_PULSE,
                                    "label": "Toggle pulse",
                                },
                                {
                                    "value": MUTE_MODE_SET_STATE,
                                    "label": "Set requested state",
                                },
                            ],
                            "mode": "dropdown",
                        }
                    }
                ),
                vol.Required(CONF_VOLUME_UP_JOIN): cv.positive_int,
                vol.Required(CONF_VOLUME_DOWN_JOIN): cv.positive_int,
                vol.Required(CONF_VOLUME_JOIN): cv.positive_int,
                vol.Required(CONF_SOURCE_NUM_JOIN): cv.positive_int,
                vol.Required("sources_text", description={"suggested_value": "1:TV,2:Radio"}): cv.string,
            }
        )
        return self._show_add_form("add_media_player", schema)

    # ------------------------------------------------------------------
    # Add: Text (serial output)
    # ------------------------------------------------------------------
    async def async_step_add_text(self, user_input=None):
        if user_input is not None:
            error = _validate_entity_form(OPT_TEXTS, user_input)
            if error:
                return self._show_form_error("add_text", OPT_TEXTS, user_input, error)
            return self._save(OPT_TEXTS, user_input)
        schema = vol.Schema(
            {
                **self._dev_field(),
                vol.Required(CONF_NAME): cv.string,
                vol.Required(CONF_SERIAL_JOIN): cv.positive_int,
                vol.Optional(CONF_OPTIMISTIC, default=True): cv.boolean,
            }
        )
        return self._show_add_form("add_text", schema)

    # ------------------------------------------------------------------
    # Add: Number (analog output)
    # ------------------------------------------------------------------
    async def async_step_add_number(self, user_input=None):
        if user_input is not None:
            error = _validate_entity_form(OPT_NUMBERS, user_input)
            if error:
                return self._show_form_error(
                    "add_number", OPT_NUMBERS, user_input, error
                )
            return self._save(OPT_NUMBERS, user_input)
        schema = vol.Schema(
            {
                **self._dev_field(),
                vol.Required(CONF_NAME): cv.string,
                vol.Required(CONF_VALUE_JOIN): cv.positive_int,
                vol.Optional(CONF_MIN_VALUE, default=0): vol.Coerce(float),
                vol.Optional(CONF_MAX_VALUE, default=65535): vol.Coerce(float),
                vol.Optional(CONF_STEP, default=1): vol.Coerce(float),
                vol.Optional(CONF_UNIT_OF_MEASUREMENT): cv.string,
                vol.Optional(CONF_OPTIMISTIC, default=True): cv.boolean,
            }
        )
        return self._show_add_form("add_number", schema)

    # ------------------------------------------------------------------
    # Add: Button (digital pulse output)
    # ------------------------------------------------------------------
    async def async_step_add_button(self, user_input=None):
        if user_input is not None:
            error = _validate_entity_form(OPT_BUTTONS, user_input)
            if error:
                return self._show_form_error(
                    "add_button", OPT_BUTTONS, user_input, error
                )
            return self._save(OPT_BUTTONS, user_input)
        schema = vol.Schema(
            {
                **self._dev_field(),
                vol.Required(CONF_NAME): cv.string,
                vol.Required(CONF_BUTTON_JOIN): cv.positive_int,
            }
        )
        return self._show_add_form("add_button", schema)

    # ------------------------------------------------------------------
    # Devices (group entities under named devices)
    # ------------------------------------------------------------------
    async def async_step_manage_devices(self, user_input=None):
        return self.async_show_menu(
            step_id="manage_devices",
            menu_options=["add_device", "edit_device", "remove_device"],
        )

    async def async_step_add_device(self, user_input=None):
        if user_input is not None:
            device = _device_from_form(user_input)
            return self._commit_options(
                lambda options: options[OPT_DEVICES].append(device)
            )
        return self.async_show_form(
            step_id="add_device", data_schema=_device_def_schema(self.hass)
        )

    async def async_step_edit_device(self, user_input=None):
        devices = self._options.get(OPT_DEVICES, [])
        if not devices:
            return self.async_abort(reason="no_devices")
        if user_input is not None:
            self._edit_device_id = user_input["device"]
            return await self.async_step_edit_device_form()
        schema = vol.Schema(
            {
                vol.Required("device"): selector(
                    {
                        "select": {
                            "options": [
                                {"value": d[CONF_ID], "label": d[CONF_NAME]}
                                for d in devices
                            ],
                            "mode": "dropdown",
                        }
                    }
                )
            }
        )
        return self.async_show_form(step_id="edit_device", data_schema=schema)

    async def async_step_edit_device_form(self, user_input=None):
        devices = self._options.get(OPT_DEVICES, [])
        device = next(
            (d for d in devices if d.get(CONF_ID) == self._edit_device_id), None
        )
        if device is None:
            return self.async_abort(reason="no_devices")
        if user_input is not None:
            updated = _device_from_form(user_input, device.get(CONF_ID))

            def update_device(options):
                options[OPT_DEVICES] = [
                    updated if d.get(CONF_ID) == device[CONF_ID] else d
                    for d in options[OPT_DEVICES]
                ]

            return self._commit_options(update_device)
        return self.async_show_form(
            step_id="edit_device_form",
            data_schema=_device_def_schema(self.hass, device),
        )

    async def async_step_remove_device(self, user_input=None):
        devices = self._options.get(OPT_DEVICES, [])
        if not devices:
            return self.async_abort(reason="no_devices")
        if user_input is not None:
            removed = set(user_input.get("devices", []))

            def remove_devices(options):
                options[OPT_DEVICES] = [
                    device
                    for device in options[OPT_DEVICES]
                    if device.get(CONF_ID) not in removed
                ]
                # Entities assigned to a removed device fall back to the
                # integration device instead of keeping a dangling reference.
                removed_refs = {custom_device_ref(dev_id) for dev_id in removed}
                for key in ALL_ENTITY_OPTION_KEYS:
                    for item in options[key]:
                        if item.get(CONF_DEVICE) in removed_refs:
                            item[CONF_DEVICE] = DEVICE_REF_PROCESSOR

            return self._commit_options(remove_devices)
        schema = vol.Schema(
            {
                vol.Required("devices"): selector(
                    {
                        "select": {
                            "options": [
                                {"value": d[CONF_ID], "label": d[CONF_NAME]}
                                for d in devices
                            ],
                            "multiple": True,
                        }
                    }
                )
            }
        )
        return self.async_show_form(step_id="remove_device", data_schema=schema)

    # ------------------------------------------------------------------
    # Edit
    # ------------------------------------------------------------------
    async def async_step_edit_entity(self, user_input=None):
        choices = {}
        for key in ALL_OPTION_KEYS:
            for item in self._options[key]:
                choice_key = f"{key}|{item[CONF_ID]}"
                choices[choice_key] = f"{_TYPE_LABELS[key]}: {item[CONF_NAME]}"

        if not choices:
            return self.async_abort(reason="no_entities")

        if user_input is not None:
            key, entity_id = user_input["entity"].split("|", 1)
            self._edit_key = key
            self._edit_item = next(
                item for item in self._options[key] if item[CONF_ID] == entity_id
            )
            return await self.async_step_edit_form()

        schema = vol.Schema(
            {
                vol.Required("entity"): selector(
                    {
                        "select": {
                            "options": [
                                {"value": k, "label": v} for k, v in choices.items()
                            ]
                        }
                    }
                )
            }
        )
        return self.async_show_form(step_id="edit_entity", data_schema=schema)

    async def async_step_edit_form(self, user_input=None):
        key, item = self._edit_key, self._edit_item
        if user_input is not None:
            # The schema identifies optional fields that belong to this form;
            # an omitted one can be cleared without deleting unrelated options.
            form_fields = {
                getattr(marker, "schema", marker)
                for marker in _edit_schema(key, item, self._dev_field(item)).schema
            }
            # Validate before the free text fields are parsed/removed, so a
            # failed submit can be re-shown with everything the user typed.
            error = _validate_entity_form(key, user_input)
            if error:
                return self.async_show_form(
                    step_id="edit_form",
                    errors={"base": error},
                    data_schema=_edit_schema(
                        key, {**item, **user_input}, self._dev_field(user_input)
                    ),
                    description_placeholders={"help_url": _help_url(key)},
                )
            if key == OPT_LIGHTS and CONF_BRIGHTNESS_DEFAULT in user_input:
                user_input[CONF_BRIGHTNESS_DEFAULT] = int(
                    user_input[CONF_BRIGHTNESS_DEFAULT]
                )
            if key == OPT_MEDIA_PLAYERS:
                sources = _parse_sources(user_input.pop("sources_text", ""))
                if sources:
                    user_input[CONF_SOURCES] = sources
                else:
                    user_input.pop(CONF_SOURCES, None)
            if key == OPT_CLIMATES:
                presets = _parse_name_join_map(user_input.pop("presets_text", ""))
                if presets:
                    user_input[CONF_PRESETS] = presets
                else:
                    user_input.pop(CONF_PRESETS, None)
            updated = {**item, **user_input}  # keeps the stable CONF_ID
            for field in form_fields.intersection(item):
                if field not in user_input or _is_blank(user_input[field]):
                    updated.pop(field, None)
            if user_input.get(CONF_ENTITY_CATEGORY) == ENTITY_CATEGORY_NONE:
                updated.pop(CONF_ENTITY_CATEGORY, None)

            def update_entity(options):
                options[key] = [
                    updated if existing.get(CONF_ID) == item[CONF_ID] else existing
                    for existing in options[key]
                ]

            return self._commit_options(update_entity)

        return self.async_show_form(
            step_id="edit_form",
            data_schema=_edit_schema(key, item, self._dev_field(item)),
            description_placeholders={"help_url": _help_url(key)},
        )

    # ------------------------------------------------------------------
    # Remove
    # ------------------------------------------------------------------
    async def async_step_remove_entity(self, user_input=None):
        choices = {}
        for key in ALL_OPTION_KEYS:
            for item in self._options[key]:
                choice_key = f"{key}|{item[CONF_ID]}"
                choices[choice_key] = f"{_TYPE_LABELS[key]}: {item[CONF_NAME]}"

        if not choices:
            return self.async_abort(reason="no_entities")

        if user_input is not None:
            selected = [
                choice_key.split("|", 1)
                for choice_key in user_input.get("entities", [])
            ]

            def remove_entities(options):
                for key, entity_id in selected:
                    options[key] = [
                        item
                        for item in options[key]
                        if item.get(CONF_ID) != entity_id
                    ]

            return self._commit_options(remove_entities)

        schema = vol.Schema(
            {
                vol.Required("entities"): selector(
                    {"select": {"options": [{"value": k, "label": v} for k, v in choices.items()], "multiple": True}}
                )
            }
        )
        return self.async_show_form(step_id="remove_entity", data_schema=schema)
