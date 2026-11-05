"""Constants for the Crestron XSIG integration."""

from __future__ import annotations

import re
import uuid

import voluptuous as vol

DOMAIN = "crestron_xsig"

# hass.data[DOMAIN][entry_id] keys
DATA_HUB = "hub"
DATA_EXPOSES = "exposes"
DATA_ACTIONS = "actions"

# Config entry data (connection)
CONF_PORT = "port"

# Options top-level keys -- each holds a list of entity definitions
OPT_SWITCHES = "switches"
OPT_LIGHTS = "lights"
OPT_COVERS = "covers"
OPT_SENSORS = "sensors"
OPT_BINARY_SENSORS = "binary_sensors"
OPT_CLIMATES = "climates"
OPT_MEDIA_PLAYERS = "media_players"
OPT_TEXTS = "texts"
OPT_NUMBERS = "numbers"
OPT_BUTTONS = "buttons"
OPT_EXPOSES = "exposes"   # HA -> Crestron rules (legacy crestron.yaml "to_joins")
OPT_ACTIONS = "actions"   # Crestron -> HA rules (legacy crestron.yaml "from_joins")
OPT_DEVICES = "devices"   # user-defined devices, for grouping entities in the UI

# NOTE: OPT_DEVICES is intentionally NOT in the lists below: device
# definitions are managed from their own options-flow pages and never
# appear in the entity add/edit/remove lists.

ALL_ENTITY_OPTION_KEYS = [
    OPT_SWITCHES,
    OPT_LIGHTS,
    OPT_COVERS,
    OPT_SENSORS,
    OPT_BINARY_SENSORS,
    OPT_CLIMATES,
    OPT_MEDIA_PLAYERS,
    OPT_TEXTS,
    OPT_NUMBERS,
    OPT_BUTTONS,
]

# Non-entity bridge rules; edited/removed alongside the entity lists.
ALL_OPTION_KEYS = ALL_ENTITY_OPTION_KEYS + [OPT_EXPOSES, OPT_ACTIONS]

# Common entity definition fields
CONF_ID = "id"  # internal stable id generated when the entity is added
CONF_NAME = "name"
CONF_DEVICE_CLASS = "device_class"
CONF_ENTITY_CATEGORY = "entity_category"
ENTITY_CATEGORY_NONE = "none"
ENTITY_CATEGORY_CONFIG = "config"
ENTITY_CATEGORY_DIAGNOSTIC = "diagnostic"


def normalize_option_ids(options: dict) -> int:
    """Add stable persisted IDs to option records that predate CONF_ID.

    IDs are generated once during migration/setup and then stored in entry
    options; callers should persist the options mapping whenever this returns
    a non-zero count.
    """
    repaired = 0
    for key in ALL_OPTION_KEYS + [OPT_DEVICES]:
        items = options.get(key, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and not item.get(CONF_ID):
                item[CONF_ID] = uuid.uuid4().hex
                repaired += 1
    return repaired

# Device assignment (per entity) and device definition fields.
# CONF_DEVICE holds a "device reference":
#   "processor"        -> this entry's main device (the Crestron processor)
#   "custom:<id>"      -> a user-defined device (OPT_DEVICES definition)
#   "existing:<id>"    -> an already existing Home Assistant device
CONF_DEVICE = "device"
CONF_MANUFACTURER = "manufacturer"
CONF_MODEL = "model"
CONF_SUGGESTED_AREA = "suggested_area"

DEVICE_REF_PROCESSOR = "processor"
DEVICE_REF_CUSTOM_PREFIX = "custom:"
DEVICE_REF_EXISTING_PREFIX = "existing:"


def custom_device_ref(device_id: str) -> str:
    """Device reference for a user-defined device."""
    return f"{DEVICE_REF_CUSTOM_PREFIX}{device_id}"


def existing_device_ref(device_id: str) -> str:
    """Device reference for an existing Home Assistant device."""
    return f"{DEVICE_REF_EXISTING_PREFIX}{device_id}"


def custom_device_identifier(entry_id: str, device_id: str) -> str:
    """Registry identifier of a user-defined device of this entry."""
    return f"{entry_id}:dev:{device_id}"
CONF_OPTIMISTIC = "optimistic"  # update local state on send (no echo needed)
CONF_STATE_SYNC = "state_sync"  # re-send state to the join on every state change

# Switch
CONF_SWITCH_JOIN = "switch_join"

# Light
CONF_BRIGHTNESS_JOIN = "brightness_join"
CONF_BRIGHTNESS_DEFAULT = "brightness_default"
CONF_RED_JOIN = "red_join"
CONF_GREEN_JOIN = "green_join"
CONF_BLUE_JOIN = "blue_join"

# Cover
CONF_COVER_TYPE = "cover_type"
CONF_POS_JOIN = "pos_join"
CONF_POSITION_SCALE = "position_scale"
POSITION_SCALE_16BIT = "16bit"
POSITION_SCALE_PERCENT = "percent"
CONF_OPEN_JOIN = "open_join"
CONF_CLOSE_JOIN = "close_join"
CONF_IS_OPENED_JOIN = "is_opened_join"
CONF_POSITION_COMMANDS = "position_commands"  # also send pos on open/close
CONF_IS_OPENING_JOIN = "is_opening_join"
CONF_IS_CLOSING_JOIN = "is_closing_join"
CONF_IS_CLOSED_JOIN = "is_closed_join"
CONF_STOP_JOIN = "stop_join"

# Sensor
CONF_VALUE_JOIN = "value_join"
CONF_UNIT_OF_MEASUREMENT = "unit_of_measurement"
CONF_DIVISOR = "divisor"

# Binary sensor
CONF_IS_ON_JOIN = "is_on_join"

# Climate
CONF_HEAT_SP_JOIN = "heat_sp_join"
CONF_COOL_SP_JOIN = "cool_sp_join"
CONF_REG_TEMP_JOIN = "reg_temp_join"
CONF_MIN_TEMP = "min_temp"
CONF_MAX_TEMP = "max_temp"
CONF_TEMP_STEP = "temp_step"
CONF_PRESETS = "presets"  # stored as dict {name: digital join}, edited as "Home:12,Away:13"
CONF_MODE_HEAT_JOIN = "mode_heat_join"
CONF_MODE_COOL_JOIN = "mode_cool_join"
CONF_MODE_AUTO_JOIN = "mode_auto_join"
CONF_MODE_OFF_JOIN = "mode_off_join"
CONF_MODE_FAN_ONLY_JOIN = "mode_fan_only_join"
CONF_MODE_DRY_JOIN = "mode_dry_join"
CONF_FAN_ON_JOIN = "fan_on_join"
CONF_FAN_AUTO_JOIN = "fan_auto_join"
CONF_HUMIDITY_JOIN = "humidity_join"
CONF_TARGET_HUMIDITY_JOIN = "target_humidity_join"
CONF_TEMP_DIVISOR = "temp_divisor"      # raw = degrees * divisor (default 10)
CONF_TEMP_UNIT = "temp_unit"  # processor temperature unit (C or F, or Home Assistant default)
TEMP_UNIT_HA = "ha"
CONF_HUMIDITY_DIVISOR = "humidity_divisor"  # raw = percent * divisor (default 1)
CONF_H1_JOIN = "h1_join"
CONF_H2_JOIN = "h2_join"
CONF_C1_JOIN = "c1_join"
CONF_C2_JOIN = "c2_join"
CONF_FA_JOIN = "fa_join"

# Text (serial output)
CONF_SERIAL_JOIN = "serial_join"

# Number (analog output)
CONF_MIN_VALUE = "min_value"
CONF_MAX_VALUE = "max_value"
CONF_STEP = "step"

# Button (digital pulse output)
CONF_BUTTON_JOIN = "button_join"

# Expose rule (HA -> Crestron, legacy "to_joins"). Exactly one source:
# a value_template, or an entity_id (+ optional attribute). The result is
# pushed to the join, converted per join type (d/a/s).
CONF_VALUE_TEMPLATE = "value_template"
CONF_ENTITY_ID = "entity_id"
CONF_ATTRIBUTE = "attribute"

# Action rule (Crestron -> HA, legacy "from_joins"). When the join is
# received, the script sequence runs with {{ value }} in its variables.
CONF_SCRIPT = "script"
CONF_TRIGGER_ON = "trigger_on"

TRIGGER_ON_PRESS = "press"      # digital goes high (default, legacy behavior)
TRIGGER_ON_RELEASE = "release"  # digital goes low
TRIGGER_ON_BOTH = "both"        # any digital change
TRIGGER_ON_OPTIONS = [TRIGGER_ON_PRESS, TRIGGER_ON_RELEASE, TRIGGER_ON_BOTH]

# Events
EVENT_JOIN_RECEIVED = f"{DOMAIN}_join_received"

# Media player
CONF_MUTE_JOIN = "mute_join"
CONF_MUTE_MODE = "mute_mode"
MUTE_MODE_TOGGLE_PULSE = "toggle_pulse"
MUTE_MODE_SET_STATE = "set_state"
CONF_VOLUME_UP_JOIN = "volume_up_join"
CONF_VOLUME_DOWN_JOIN = "volume_down_join"
CONF_VOLUME_JOIN = "volume_join"
CONF_SOURCE_NUM_JOIN = "source_number_join"
CONF_SOURCES = "sources"  # stored as dict {int: str}, edited as "1:TV,2:Radio" text

# Services
SERVICE_SET_DIGITAL = "set_digital"
SERVICE_SET_ANALOG = "set_analog"
SERVICE_SET_SERIAL = "set_serial"
SERVICE_RELOAD_CONNECTION = "reload_connection"

CONF_JOIN = "join"
CONF_VALUE = "value"
CONF_ENTRY_ID = "entry_id"  # optional service target: which processor to use

# Device class choices offered in the "add entity" forms. Kept as plain
# strings (rather than importing HA's SensorDeviceClass/BinarySensorDeviceClass
# enums) so this file has zero Home Assistant imports and stays easy to
# read/update. Sourced from Home Assistant's core enums.
SENSOR_DEVICE_CLASSES = [
    "apparent_power", "aqi", "atmospheric_pressure", "battery",
    "carbon_dioxide", "carbon_monoxide", "current", "data_rate",
    "data_size", "date", "distance", "duration", "energy",
    "energy_storage", "enum", "frequency", "gas", "humidity",
    "illuminance", "irradiance", "moisture", "monetary",
    "nitrogen_dioxide", "nitrogen_monoxide", "nitrous_oxide", "ozone",
    "ph", "pm1", "pm10", "pm25", "power", "power_factor",
    "precipitation", "precipitation_intensity", "pressure",
    "reactive_power", "signal_strength", "sound_pressure", "speed",
    "sulphur_dioxide", "temperature", "timestamp",
    "volatile_organic_compounds", "volatile_organic_compounds_parts",
    "voltage", "volume", "volume_flow_rate", "volume_storage", "water",
    "weight", "wind_speed",
]

BINARY_SENSOR_DEVICE_CLASSES = [
    "battery", "battery_charging", "carbon_monoxide", "cold",
    "connectivity", "door", "garage_door", "gas", "heat", "light",
    "lock", "moisture", "motion", "moving", "occupancy", "opening",
    "plug", "power", "presence", "problem", "running", "safety",
    "smoke", "sound", "tamper", "update", "vibration", "window",
]

SWITCH_DEVICE_CLASSES = ["switch", "outlet"]

# ---------------------------------------------------------------------------
# Typed join strings. Expose/action rules use the legacy YAML notation,
# e.g. "d451" (digital), "a101" (analog), "s7" (serial).
# ---------------------------------------------------------------------------
# XSIG protocol limits (docs/Xsig documentation.docx): the digital join
# number is 12 bit (1..4096), the analog/serial join number is 10 bit
# (1..1024) and the analog value is 16 bit (0..65535). Joins are 1-based:
# join 0 does not exist. Validated everywhere (forms, services, parser).
MIN_JOIN = 1
MAX_DIGITAL_JOIN = 4096
MAX_ANALOG_JOIN = 1024
MAX_SERIAL_JOIN = 1024
MIN_ANALOG_VALUE = 0
MAX_ANALOG_VALUE = 65535

MAX_JOIN_BY_TYPE = {
    "d": MAX_DIGITAL_JOIN,
    "a": MAX_ANALOG_JOIN,
    "s": MAX_SERIAL_JOIN,
}

# Service schemas: explicit rejection of out-of-range joins and analog
# values (no silent clamping). Kept as voluptuous nodes so they stay
# serializable for the frontend tooling (see tools/check_flows.py).
VALIDATE_DIGITAL_JOIN = vol.All(
    vol.Coerce(int), vol.Range(min=MIN_JOIN, max=MAX_DIGITAL_JOIN)
)
VALIDATE_ANALOG_JOIN = vol.All(
    vol.Coerce(int), vol.Range(min=MIN_JOIN, max=MAX_ANALOG_JOIN)
)
VALIDATE_SERIAL_JOIN = vol.All(
    vol.Coerce(int), vol.Range(min=MIN_JOIN, max=MAX_SERIAL_JOIN)
)
VALIDATE_ANALOG_VALUE = vol.All(
    vol.Coerce(int), vol.Range(min=MIN_ANALOG_VALUE, max=MAX_ANALOG_VALUE)
)

JOIN_PATTERN = re.compile(r"^([das])(\d{1,5})$")


def parse_join(join: str) -> tuple[str, int] | None:
    """Parse a typed join like "a101" into ("a", 101), or None if invalid."""
    match = JOIN_PATTERN.match(str(join).strip().lower())
    if match is None:
        return None
    number = int(match.group(2))
    if number < MIN_JOIN or number > MAX_JOIN_BY_TYPE[match.group(1)]:
        return None
    return match.group(1), number


def join_error_key(join: str) -> str | None:
    """Return the error key of an invalid typed join, None when it is valid.

    Used by the config flow so the user gets a translatable message:
    "invalid_join" for a bad format ("x9", "abc", "d"), "join_out_of_range"
    for a well-formed join outside the XSIG limits of its type.
    """
    if JOIN_PATTERN.match(str(join).strip().lower()) is None:
        return "invalid_join"
    return None if parse_join(join) is not None else "join_out_of_range"


def format_join(join_type: str, number: int) -> str:
    """Format a typed join, e.g. ("a", 101) -> "a101"."""
    return f"{join_type}{number}"


def native_join_value(join_type: str, value: str) -> bool | int | str:
    """Convert a raw hub notification string to a natural Python value."""
    if join_type == "d":
        return str(value) in ("True", "true", "1")
    if join_type == "a":
        return int(float(str(value)))
    return str(value)

PLATFORMS = [
    "switch",
    "light",
    "cover",
    "sensor",
    "binary_sensor",
    "climate",
    "media_player",
    "text",
    "number",
    "button",
]
