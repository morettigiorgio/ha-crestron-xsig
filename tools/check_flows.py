"""Dev-only sanity check for the config/options flow schemas.

Builds every form schema the flows can show and verifies that each one is
serializable with ``probatio.to_field_list`` (what HA 2026 uses to send the
schema to the frontend). Catches both Python errors in schema builders and
non-serializable validators (bare ``cv.*`` functions, etc.).

Runs outside Home Assistant: the ``homeassistant`` modules are stubbed and
``voluptuous`` is aliased to ``probatio``, mirroring the HA 2026 runtime.

Usage (any Python >= 3.12 with ``probatio`` and ``pyyaml`` installed):

    python tools/check_flows.py
"""

from __future__ import annotations

import asyncio
import enum
import importlib
import sys
import types
from typing import Any
from pathlib import Path

import probatio

COMPONENT_DIR = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------
# Stub the bits of Home Assistant the component imports
# --------------------------------------------------------------------------
def _make_module(name):
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


# HA 2026 validates with probatio; its voluptuous shim maps 1:1.
sys.modules.setdefault("voluptuous", probatio)

ha = _make_module("homeassistant")
config_entries = _make_module("homeassistant.config_entries")
ha.config_entries = config_entries
core = _make_module("homeassistant.core")
ha.core = core
helpers = _make_module("homeassistant.helpers")
ha.helpers = helpers
cv = _make_module("homeassistant.helpers.config_validation")
selector_mod = _make_module("homeassistant.helpers.selector")


def callback(func):
    return func


core.callback = callback
cv.string = lambda value: str(value)
cv.boolean = lambda value: bool(value)
cv.positive_int = probatio.All(probatio.Coerce(int), probatio.Range(min=0))
cv.port = probatio.Port()
cv.entity_id = lambda value: str(value)  # bare function: NOT serializable
helpers.config_validation = cv


class StubSelector:
    def __init__(self, config: dict) -> None:
        self.config = config

    def serialize(self) -> dict:
        return {"selector": self.config}


def selector(config: dict) -> StubSelector:
    return StubSelector(config)


selector_mod.selector = selector

components = _make_module("homeassistant.components")
ha.components = components
light_mod = _make_module("homeassistant.components.light")
components.light = light_mod
light_mod.ATTR_BRIGHTNESS = "brightness"
light_mod.ATTR_RGB_COLOR = "rgb_color"
light_mod.ColorMode = enum.Enum(
    "ColorMode", {"BRIGHTNESS": "brightness", "RGB": "rgb"}
)
light_mod.LightEntity = type("LightEntity", (), {})
cover_mod = _make_module("homeassistant.components.cover")
components.cover = cover_mod
cover_mod.CoverDeviceClass = enum.Enum(
    "CoverDeviceClass", {"SHADE": "shade", "BLIND": "blind", "CURTAIN": "curtain"}
)
cover_mod.CoverEntityFeature = enum.IntFlag(
    "CoverEntityFeature", {"OPEN": 1, "CLOSE": 2, "STOP": 4, "SET_POSITION": 8}
)
cover_mod.CoverEntity = type("CoverEntity", (), {})

# entity/config flows look up existing devices in the device registry.
device_registry_mod = _make_module("homeassistant.helpers.device_registry")


class StubDeviceRegistry:
    def __init__(self):
        self.devices = {}


def _dr_async_get(hass):
    return hass.device_registry


def _dr_entries_for_config_entry(registry, config_entry_id):
    return [
        device
        for device in registry.devices.values()
        if device.config_entry_id == config_entry_id
    ]


device_registry_mod.async_get = _dr_async_get
device_registry_mod.async_entries_for_config_entry = _dr_entries_for_config_entry
helpers.device_registry = device_registry_mod

# the device form also lists the areas known to Home Assistant.
area_registry_mod = _make_module("homeassistant.helpers.area_registry")


class StubAreaRegistry:
    areas = {}


def _ar_async_get(hass):
    return StubAreaRegistry()


area_registry_mod.async_get = _ar_async_get
helpers.area_registry = area_registry_mod


class ConfigFlow:
    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__()


class OptionsFlow:
    pass


class ConfigEntry:
    def __init__(self, options: dict | None = None) -> None:
        self.entry_id = "test"
        self.options = options or {}
        self.data = {}
        self.title = "test"


class StubConfigEntriesManager:
    def __init__(self, entries=None):
        self.entries = entries or []

    def async_entries(self):
        return self.entries


class StubHass:
    def __init__(self) -> None:
        self.config_entries = StubConfigEntriesManager()
        self.device_registry = StubDeviceRegistry()


class FlowResult(dict):
    pass


config_entries.ConfigFlow = ConfigFlow
config_entries.OptionsFlow = OptionsFlow
config_entries.ConfigEntry = ConfigEntry
config_entries.FlowResult = FlowResult


# --------------------------------------------------------------------------
# Load the component without running its package __init__
# --------------------------------------------------------------------------
package = types.ModuleType("crestron_xsig")
package.__path__ = [str(COMPONENT_DIR)]
sys.modules["crestron_xsig"] = package

config_flow = importlib.import_module("crestron_xsig.config_flow")
const = importlib.import_module("crestron_xsig.const")

# Minimal entity API stub for runtime entity-category checks.
entity_helpers = _make_module("homeassistant.helpers.entity")


class StubEntityCategory(enum.Enum):
    CONFIG = "config"
    DIAGNOSTIC = "diagnostic"


class StubEntity:
    pass


class StubDeviceInfo:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


entity_helpers.Entity = StubEntity
entity_helpers.EntityCategory = StubEntityCategory
entity_helpers.DeviceInfo = StubDeviceInfo
crestron_entity = importlib.import_module("crestron_xsig.entity")
light_platform = importlib.import_module("crestron_xsig.light")
cover_platform = importlib.import_module("crestron_xsig.cover")


# Mimics homeassistant.helpers.config_validation.custom_serializer for the
# validator identities we stubbed above.
def custom_serializer(node: Any) -> Any:
    if node is cv.string:
        return {"type": "string"}
    if node is cv.boolean:
        return {"type": "boolean"}
    if isinstance(node, StubSelector):
        return node.serialize()
    return probatio.UNSUPPORTED


# --------------------------------------------------------------------------
# Collect every schema the flows can show
# --------------------------------------------------------------------------
class DummyView:
    """Captures the data_schema of every async_show_form() call."""

    def __init__(self) -> None:
        self.schemas: list = []

    def async_show_form(self, step_id=None, data_schema=None, errors=None, **kwargs):
        self.schemas.append(data_schema)
        return {"type": "form", "step_id": step_id, "data_schema": data_schema}

    def async_show_menu(self, step_id=None, menu_options=None, **kwargs):
        return {"type": "menu", "step_id": step_id}

    def async_create_entry(self, title=None, data=None, **kwargs):
        return {"type": "create_entry", "data": data}

    def async_abort(self, reason=None, **kwargs):
        return {"type": "abort", "reason": reason}


SAMPLE_ITEM = {
    "name": "Sample",
    "join": "d1",
    "value_join": 1,
    "switch_join": 1,
    "brightness_join": 1,
    "script": [{"action": "light.turn_on"}],
    "presets": {"Home": 1},
    "sources": {"TV": 1},
}


def collect() -> list:
    schemas: list = []

    # Module-level builders, both empty and pre-filled (edit pre-fills).
    for builder, args in (
        (config_flow._expose_fields, ()),
        (config_flow._action_fields, ()),
        (config_flow._cover_schema, ()),
        (config_flow._climate_schema, ()),
        (config_flow._expose_fields, (SAMPLE_ITEM,)),
        (config_flow._action_fields, (SAMPLE_ITEM,)),
        (config_flow._cover_schema, (SAMPLE_ITEM,)),
        (config_flow._climate_schema, (SAMPLE_ITEM,)),
    ):
        schemas.append((builder.__name__, builder(*args)))

    for key in const.ALL_OPTION_KEYS:
        schemas.append(
            (f"_edit_schema[{key}]", config_flow._edit_schema(key, dict(SAMPLE_ITEM)))
        )

    # Every flow step with no input (shows the form).
    flow = config_flow.CrestronXsigOptionsFlow(ConfigEntry())
    flow.hass = StubHass()  # OptionsFlow receives hass from HA at runtime.
    flow._imported = None
    view = DummyView()
    flow.async_show_form = view.async_show_form
    flow.async_show_menu = view.async_show_menu
    flow.async_create_entry = view.async_create_entry
    flow.async_abort = view.async_abort

    steps = [
        name
        for name in dir(flow)
        if name.startswith("async_step_") and name != "async_step_init"
    ]
    for name in steps:
        view.schemas.clear()
        try:
            asyncio.run(getattr(flow, name)(None))
        except Exception as err:  # noqa: BLE001
            print(f"ERROR  {name}(None): {type(err).__name__}: {err}")
            continue
        schemas.extend((f"{name}()", s) for s in view.schemas)

    # Steps that need existing entities in the options.
    sample_entry = dict(SAMPLE_ITEM)
    sample_entry[const.CONF_ID] = "abc123"
    flow2 = config_flow.CrestronXsigOptionsFlow(
        ConfigEntry({key: [dict(sample_entry)] for key in const.ALL_OPTION_KEYS})
    )
    view2 = DummyView()
    flow2.async_show_form = view2.async_show_form
    flow2.async_show_menu = view2.async_show_menu
    flow2.async_create_entry = view2.async_create_entry
    flow2.async_abort = view2.async_abort
    for name in ("async_step_edit_entity", "async_step_remove_entity"):
        view2.schemas.clear()
        try:
            asyncio.run(getattr(flow2, name)(None))
        except Exception as err:  # noqa: BLE001
            print(f"ERROR  {name}(None): {type(err).__name__}: {err}")
            continue
        schemas.extend((f"{name}()", s) for s in view2.schemas)

    cfg_view = DummyView()
    cfg = config_flow.CrestronXsigConfigFlow()
    cfg.async_show_form = cfg_view.async_show_form
    cfg.async_create_entry = cfg_view.async_create_entry
    try:
        asyncio.run(cfg.async_step_user(None))
    except Exception as err:  # noqa: BLE001
        print(f"ERROR  async_step_user(None): {type(err).__name__}: {err}")
    schemas.extend(("async_step_user()", s) for s in cfg_view.schemas)

    return schemas


def test_entity_categories() -> None:
    """Check legacy default, enum mapping, add/edit persistence, and reset."""
    def make_entity(item=None):
        return crestron_entity.CrestronEntity(
            object(), "entry", "unique", "Test", item=item
        )

    assert getattr(make_entity(), "_attr_entity_category", None) is None

    class DiagnosticDefaultEntity(crestron_entity.CrestronEntity):
        _attr_entity_category = StubEntityCategory.DIAGNOSTIC

    diagnostic_default = DiagnosticDefaultEntity(
        object(), "entry", "connection", "Connection", item=None
    )
    assert diagnostic_default._attr_entity_category is StubEntityCategory.DIAGNOSTIC
    assert getattr(
        make_entity({const.CONF_ENTITY_CATEGORY: None}), "_attr_entity_category", None
    ) is None
    assert make_entity({const.CONF_ENTITY_CATEGORY: const.ENTITY_CATEGORY_CONFIG})._attr_entity_category is StubEntityCategory.CONFIG
    assert make_entity({const.CONF_ENTITY_CATEGORY: const.ENTITY_CATEGORY_DIAGNOSTIC})._attr_entity_category is StubEntityCategory.DIAGNOSTIC

    entry = ConfigEntry(
        {
            const.OPT_DEVICES: [
                {const.CONF_ID: "child", const.CONF_NAME: "Child device"}
            ]
        }
    )
    entry.entry_id = "entry"
    other_entry = ConfigEntry()
    other_entry.entry_id = "other-entry"
    hass = StubHass()
    hass.config_entries.entries = [entry, other_entry]
    hass.device_registry.devices = {
        "processor-id": types.SimpleNamespace(
            id="processor-id",
            identifiers={(const.DOMAIN, entry.entry_id)},
            connections=set(),
            config_entry_id=entry.entry_id,
        ),
        "existing-id": types.SimpleNamespace(
            id="existing-id",
            identifiers={("other_domain", "existing")},
            connections=set(),
            config_entry_id=other_entry.entry_id,
        ),
    }
    child_info = crestron_entity.build_device_info(
        hass, entry, {const.CONF_DEVICE: const.custom_device_ref("child")}
    )
    assert child_info.kwargs["via_device_id"] == "processor-id"
    assert "via_device" not in child_info.kwargs
    existing_info = crestron_entity.build_device_info(
        hass,
        entry,
        {
            const.CONF_DEVICE: f"{const.DEVICE_REF_EXISTING_PREFIX}existing-id",
        },
    )
    assert existing_info.kwargs["identifiers"] == {("other_domain", "existing")}

    def make_flow(options=None):
        flow = config_flow.CrestronXsigOptionsFlow(ConfigEntry(options or {}))
        flow.async_create_entry = lambda title="", data=None, **kwargs: {
            "type": "create_entry",
            "data": data,
        }
        flow.async_show_form = lambda step_id=None, data_schema=None, **kwargs: {
            "type": "form",
            "step_id": step_id,
            "data_schema": data_schema,
        }
        return flow

    async def check_forms_and_saves():
        flow = make_flow()
        flow.hass = StubHass()
        real_form = await flow.async_step_add_switch()
        bridge_form = await flow.async_step_add_expose()
        real_keys = {
            getattr(key, "schema", key)
            for key in real_form["data_schema"].schema
        }
        bridge_keys = {
            getattr(key, "schema", key)
            for key in bridge_form["data_schema"].schema
        }
        assert const.CONF_ENTITY_CATEGORY in real_keys
        assert const.CONF_ENTITY_CATEGORY not in bridge_keys
        for step in (
            "add_light", "add_cover", "add_sensor", "add_binary_sensor",
            "add_climate", "add_media_player", "add_text", "add_number",
            "add_button", "add_action",
        ):
            form = await getattr(flow, f"async_step_{step}")()
            keys = {
                getattr(key, "schema", key)
                for key in form["data_schema"].schema
            }
            if step == "add_action":
                assert const.CONF_ENTITY_CATEGORY not in keys
            else:
                assert const.CONF_ENTITY_CATEGORY in keys, step
        for rule_key in (const.OPT_EXPOSES, const.OPT_ACTIONS):
            schema = config_flow._edit_schema(rule_key, dict(SAMPLE_ITEM))
            keys = {
                getattr(key, "schema", key)
                for key in schema.schema
            }
            assert const.CONF_ENTITY_CATEGORY not in keys

        for selected in (const.ENTITY_CATEGORY_CONFIG, const.ENTITY_CATEGORY_DIAGNOSTIC):
            added = await make_flow().async_step_add_switch(
                {
                    const.CONF_NAME: "Test",
                    const.CONF_SWITCH_JOIN: 1,
                    const.CONF_ENTITY_CATEGORY: selected,
                }
            )
            assert added["data"][const.OPT_SWITCHES][0][const.CONF_ENTITY_CATEGORY] == selected

        no_category = await make_flow().async_step_add_switch(
            {
                const.CONF_NAME: "Test",
                const.CONF_SWITCH_JOIN: 1,
                const.CONF_ENTITY_CATEGORY: const.ENTITY_CATEGORY_NONE,
            }
        )
        assert const.CONF_ENTITY_CATEGORY not in no_category["data"][const.OPT_SWITCHES][0]

        item = {
            const.CONF_ID: "stable-id",
            const.CONF_NAME: "Existing",
            const.CONF_SWITCH_JOIN: 5,
            const.CONF_ENTITY_CATEGORY: const.ENTITY_CATEGORY_CONFIG,
            "custom_metadata": {"keep": True},
        }
        edit = make_flow({const.OPT_SWITCHES: [item]})
        edit._edit_key, edit._edit_item = const.OPT_SWITCHES, item
        changed = await edit.async_step_edit_form(
            {
                const.CONF_NAME: "Existing",
                const.CONF_SWITCH_JOIN: 5,
                const.CONF_ENTITY_CATEGORY: const.ENTITY_CATEGORY_DIAGNOSTIC,
            }
        )
        changed_item = changed["data"][const.OPT_SWITCHES][0]
        assert changed_item[const.CONF_ENTITY_CATEGORY] == const.ENTITY_CATEGORY_DIAGNOSTIC
        assert changed_item[const.CONF_ID] == "stable-id"
        assert changed_item["custom_metadata"] == {"keep": True}

        reset = make_flow({const.OPT_SWITCHES: [changed_item]})
        reset._edit_key, reset._edit_item = const.OPT_SWITCHES, changed_item
        reset_result = await reset.async_step_edit_form(
            {
                const.CONF_NAME: "Existing",
                const.CONF_SWITCH_JOIN: 5,
                const.CONF_ENTITY_CATEGORY: const.ENTITY_CATEGORY_NONE,
            }
        )
        reset_item = reset_result["data"][const.OPT_SWITCHES][0]
        assert const.CONF_ENTITY_CATEGORY not in reset_item
        assert reset_item[const.CONF_ID] == "stable-id"
        assert reset_item["custom_metadata"] == {"keep": True}

    asyncio.run(check_forms_and_saves())


def test_rgb_lights() -> None:
    """Check optional RGB forms, all-or-none validation, and join scaling."""
    add_flow = config_flow.CrestronXsigOptionsFlow(ConfigEntry())
    add_flow.hass = StubHass()
    add_flow.async_show_form = lambda **kwargs: kwargs
    add_form = asyncio.run(add_flow.async_step_add_light())
    add_fields = {
        getattr(key, "schema", key)
        for key in add_form["data_schema"].schema
    }
    assert {const.CONF_RED_JOIN, const.CONF_GREEN_JOIN, const.CONF_BLUE_JOIN} <= add_fields

    rgb_item = {
        const.CONF_ID: "rgb-light",
        const.CONF_NAME: "RGB",
        const.CONF_BRIGHTNESS_JOIN: 1,
        const.CONF_RED_JOIN: 2,
        const.CONF_GREEN_JOIN: 3,
        const.CONF_BLUE_JOIN: 4,
    }
    fields = {
        getattr(key, "schema", key)
        for key in config_flow._edit_schema(const.OPT_LIGHTS, rgb_item).schema
    }
    assert {const.CONF_RED_JOIN, const.CONF_GREEN_JOIN, const.CONF_BLUE_JOIN} <= fields
    assert config_flow._validate_entity_form(
        const.OPT_LIGHTS, {const.CONF_BRIGHTNESS_JOIN: 1}
    ) is None
    assert config_flow._validate_entity_form(
        const.OPT_LIGHTS,
        {const.CONF_BRIGHTNESS_JOIN: 1, const.CONF_RED_JOIN: 2},
    ) == "rgb_joins_incomplete"
    assert config_flow._validate_entity_form(
        const.OPT_LIGHTS,
        {
            const.CONF_BRIGHTNESS_JOIN: 1,
            const.CONF_RED_JOIN: 2,
            const.CONF_GREEN_JOIN: 3,
            const.CONF_BLUE_JOIN: 1025,
        },
    ) == "join_out_of_range"
    join_fields = (
        const.CONF_BRIGHTNESS_JOIN,
        const.CONF_RED_JOIN,
        const.CONF_GREEN_JOIN,
        const.CONF_BLUE_JOIN,
    )
    for index, field in enumerate(join_fields):
        for other_field in join_fields[index + 1 :]:
            duplicate_joins = dict(zip(join_fields, (1, 2, 3, 4)))
            duplicate_joins[other_field] = duplicate_joins[field]
            assert config_flow._validate_entity_form(
                const.OPT_LIGHTS, duplicate_joins
            ) == "duplicate_light_joins", (field, other_field)

    class FakeHub:
        def __init__(self):
            self.values = {1: 32768, 2: 0, 3: 32768, 4: 65535}
            self.sent = []

        def get_analog(self, join):
            return self.values[join]

        def set_analog(self, join, value):
            self.sent.append((join, value))
            return True

        def update_analog(self, join, value):
            self.values[join] = value

    async def check_runtime():
        hub = FakeHub()
        light = light_platform.CrestronLight(
            hub,
            "entry",
            {
                **rgb_item,
                const.CONF_OPTIMISTIC: True,
            },
        )
        writes = []
        light.async_write_ha_state = lambda: writes.append(True)
        assert light._attr_color_mode == light_mod.ColorMode.RGB
        assert light._attr_supported_color_modes == {light_mod.ColorMode.RGB}
        assert light.brightness == 127
        assert light.rgb_color == (0, 127, 255)

        await light.async_turn_on(rgb_color=(255, 64, 0))
        assert hub.sent == [(2, 65535), (3, 16448), (4, 0)]
        assert light.rgb_color == (255, 64, 0)
        assert len(writes) == 1

        legacy = light_platform.CrestronLight(
            FakeHub(),
            "entry",
            {
                const.CONF_ID: "legacy",
                const.CONF_NAME: "Legacy",
                const.CONF_BRIGHTNESS_JOIN: 1,
            },
        )
        assert legacy._attr_color_mode == light_mod.ColorMode.BRIGHTNESS
        assert legacy._attr_supported_color_modes == {light_mod.ColorMode.BRIGHTNESS}
        assert legacy.rgb_color is None

    asyncio.run(check_runtime())


def test_cover_position_scales() -> None:
    """Cover joins can use either native percent or the legacy 16-bit range."""
    class FakeHub:
        def __init__(self, value):
            self.value = value
            self.sent = []

        def get_analog(self, join):
            return self.value

        def set_analog(self, join, value):
            self.sent.append((join, value))
            return True

        def update_analog(self, join, value):
            self.value = value

    async def check_runtime():
        legacy_hub = FakeHub(32768)
        legacy = cover_platform.CrestronCover(
            legacy_hub,
            "entry",
            {const.CONF_ID: "legacy-cover", const.CONF_NAME: "Legacy", const.CONF_POS_JOIN: 1},
        )
        assert legacy.current_cover_position == 50
        await legacy.async_set_cover_position(position=50)
        assert legacy_hub.sent == [(1, 32768)]
        await legacy.async_open_cover()
        assert legacy_hub.sent[-1] == (1, 65535)

        percent_hub = FakeHub(45)
        percent = cover_platform.CrestronCover(
            percent_hub,
            "entry",
            {
                const.CONF_ID: "percent-cover",
                const.CONF_NAME: "Percent",
                const.CONF_POS_JOIN: 2,
                const.CONF_POSITION_SCALE: const.POSITION_SCALE_PERCENT,
                const.CONF_OPTIMISTIC: True,
            },
        )
        percent.async_write_ha_state = lambda: None
        assert percent.current_cover_position == 45
        await percent.async_set_cover_position(position=37)
        assert percent_hub.sent == [(2, 37)]
        assert percent.current_cover_position == 37
        await percent.async_open_cover()
        assert percent_hub.sent[-1] == (2, 100)
        await percent.async_close_cover()
        assert percent_hub.sent[-1] == (2, 0)
        percent_hub.value = 101
        assert percent.current_cover_position == 100

        pulses = []
        percent._pulse = pulses.append
        percent._open_join = 3
        percent._close_join = 4
        percent_hub.sent.clear()
        await percent.async_open_cover()
        await percent.async_close_cover()
        assert pulses == [3, 4] and not percent_hub.sent
        percent._position_commands = True
        await percent.async_open_cover()
        await percent.async_close_cover()
        assert percent_hub.sent == [(2, 100), (2, 0)]

        flow = config_flow.CrestronXsigOptionsFlow(ConfigEntry())
        flow.hass = StubHass()
        flow.async_create_entry = lambda title="", data=None, **kwargs: {"data": data}
        flow.async_show_form = lambda **kwargs: kwargs
        form = await flow.async_step_add_cover()
        markers = {getattr(key, "schema", key): key for key in form["data_schema"].schema}
        assert markers[const.CONF_POSITION_SCALE].default() == const.POSITION_SCALE_16BIT
        saved = await flow.async_step_add_cover({
            const.CONF_NAME: "Percent", const.CONF_POS_JOIN: 2,
            const.CONF_POSITION_SCALE: const.POSITION_SCALE_PERCENT,
        })
        item = saved["data"][const.OPT_COVERS][0]
        assert item[const.CONF_POSITION_SCALE] == const.POSITION_SCALE_PERCENT
        edit = config_flow.CrestronXsigOptionsFlow(ConfigEntry(saved["data"]))
        edit.hass = StubHass()
        edit.async_create_entry = flow.async_create_entry
        edit.async_show_form = flow.async_show_form
        edit._edit_key = const.OPT_COVERS
        edit._edit_item = item
        form = await edit.async_step_edit_form()
        markers = {getattr(key, "schema", key): key for key in form["data_schema"].schema}
        assert markers[const.CONF_POSITION_SCALE].default() == const.POSITION_SCALE_PERCENT
        saved = await edit.async_step_edit_form({
            const.CONF_NAME: "Percent", const.CONF_POS_JOIN: 2,
            const.CONF_POSITION_SCALE: const.POSITION_SCALE_16BIT,
        })
        assert saved["data"][const.OPT_COVERS][0][const.CONF_POSITION_SCALE] == const.POSITION_SCALE_16BIT

    assert config_flow._validate_entity_form(
        const.OPT_COVERS, {const.CONF_POSITION_SCALE: "invalid"}
    ) == "invalid_position_scale"
    asyncio.run(check_runtime())


def test_climate_temp_unit_and_media_mute_mode() -> None:
    """Check Add/Edit fields, defaults, validation, and saved option values."""
    def make_flow(options=None):
        flow = config_flow.CrestronXsigOptionsFlow(ConfigEntry(options or {}))
        flow.hass = StubHass()
        flow.async_create_entry = lambda title="", data=None, **kwargs: {
            "type": "create_entry",
            "data": data,
        }
        flow.async_show_form = lambda **kwargs: kwargs
        return flow

    async def check_forms_and_saves():
        flow = make_flow()
        climate_form = await flow.async_step_add_climate()
        climate_keys = {
            getattr(key, "schema", key) for key in climate_form["data_schema"].schema
        }
        assert const.CONF_TEMP_UNIT in climate_keys
        climate_added = await flow.async_step_add_climate(
            {
                const.CONF_NAME: "Climate",
                const.CONF_REG_TEMP_JOIN: 1,
                const.CONF_TEMP_UNIT: "F",
            }
        )
        assert climate_added["data"][const.OPT_CLIMATES][0][const.CONF_TEMP_UNIT] == "F"

        media_form = await flow.async_step_add_media_player()
        media_keys = {
            getattr(key, "schema", key) for key in media_form["data_schema"].schema
        }
        assert const.CONF_MUTE_MODE in media_keys
        media_added = await flow.async_step_add_media_player(
            {
                const.CONF_NAME: "Player",
                const.CONF_MUTE_JOIN: 1,
                const.CONF_MUTE_MODE: const.MUTE_MODE_SET_STATE,
                const.CONF_VOLUME_UP_JOIN: 2,
                const.CONF_VOLUME_DOWN_JOIN: 3,
                const.CONF_VOLUME_JOIN: 4,
                const.CONF_SOURCE_NUM_JOIN: 5,
                "sources_text": "1:TV",
            }
        )
        assert (
            media_added["data"][const.OPT_MEDIA_PLAYERS][0][const.CONF_MUTE_MODE]
            == const.MUTE_MODE_SET_STATE
        )

        climate_item = {
            const.CONF_ID: "climate-id",
            const.CONF_NAME: "Climate",
            const.CONF_REG_TEMP_JOIN: 1,
            const.CONF_TEMP_UNIT: "C",
        }
        edit_climate = make_flow({const.OPT_CLIMATES: [climate_item]})
        edit_climate._edit_key, edit_climate._edit_item = const.OPT_CLIMATES, climate_item
        climate_edit_form = await edit_climate.async_step_edit_form()
        climate_edit_keys = {
            getattr(key, "schema", key)
            for key in climate_edit_form["data_schema"].schema
        }
        assert const.CONF_TEMP_UNIT in climate_edit_keys
        climate_edited = await edit_climate.async_step_edit_form(
            {
                const.CONF_NAME: "Climate",
                const.CONF_REG_TEMP_JOIN: 1,
                const.CONF_TEMP_UNIT: "F",
            }
        )
        assert climate_edited["data"][const.OPT_CLIMATES][0][const.CONF_TEMP_UNIT] == "F"

        media_item = {
            const.CONF_ID: "media-id",
            const.CONF_NAME: "Player",
            const.CONF_MUTE_JOIN: 1,
            const.CONF_MUTE_MODE: const.MUTE_MODE_TOGGLE_PULSE,
            const.CONF_VOLUME_UP_JOIN: 2,
            const.CONF_VOLUME_DOWN_JOIN: 3,
            const.CONF_VOLUME_JOIN: 4,
            const.CONF_SOURCE_NUM_JOIN: 5,
            const.CONF_SOURCES: {1: "TV"},
        }
        edit_media = make_flow({const.OPT_MEDIA_PLAYERS: [media_item]})
        edit_media._edit_key, edit_media._edit_item = const.OPT_MEDIA_PLAYERS, media_item
        media_edit_form = await edit_media.async_step_edit_form()
        media_edit_keys = {
            getattr(key, "schema", key)
            for key in media_edit_form["data_schema"].schema
        }
        assert const.CONF_MUTE_MODE in media_edit_keys
        media_edited = await edit_media.async_step_edit_form(
            {
                const.CONF_NAME: "Player",
                const.CONF_MUTE_JOIN: 1,
                const.CONF_MUTE_MODE: const.MUTE_MODE_SET_STATE,
                const.CONF_VOLUME_UP_JOIN: 2,
                const.CONF_VOLUME_DOWN_JOIN: 3,
                const.CONF_VOLUME_JOIN: 4,
                const.CONF_SOURCE_NUM_JOIN: 5,
                "sources_text": "1:TV",
            }
        )
        assert (
            media_edited["data"][const.OPT_MEDIA_PLAYERS][0][const.CONF_MUTE_MODE]
            == const.MUTE_MODE_SET_STATE
        )

    assert config_flow._validate_entity_form(
        const.OPT_CLIMATES, {const.CONF_TEMP_UNIT: "invalid"}
    ) == "invalid_temp_unit"
    assert config_flow._validate_entity_form(
        const.OPT_MEDIA_PLAYERS, {const.CONF_MUTE_MODE: "invalid"}
    ) == "invalid_mute_mode"
    asyncio.run(check_forms_and_saves())


def main() -> int:
    failures = 0
    for label, schema in collect():
        if schema is None:
            continue
        try:
            probatio.to_field_list(schema, custom_serializer=custom_serializer)
            print(f"ok     {label}")
        except Exception as err:  # noqa: BLE001
            failures += 1
            print(f"FAIL   {label}: {type(err).__name__}: {err}")
    try:
        test_entity_categories()
        print("ok     entity category defaults, add/edit, and reset")
    except Exception as err:  # noqa: BLE001
        failures += 1
        print(f"FAIL   entity category checks: {type(err).__name__}: {err}")
    try:
        test_rgb_lights()
        print("ok     RGB light forms, validation, scaling, and legacy mode")
    except Exception as err:  # noqa: BLE001
        failures += 1
        print(f"FAIL   RGB light checks: {type(err).__name__}: {err}")
    try:
        test_cover_position_scales()
        print("ok     cover position scales, forms, and persistence")
    except Exception as err:  # noqa: BLE001
        failures += 1
        print(f"FAIL   cover position checks: {type(err).__name__}: {err}")
    try:
        test_climate_temp_unit_and_media_mute_mode()
        print("ok     climate temp-unit and media-player mute-mode forms, validation, and persistence")
    except Exception as err:  # noqa: BLE001
        failures += 1
        print(f"FAIL   climate/mute mode checks: {type(err).__name__}: {err}")
    print()
    print("FAILED" if failures else "all schemas and entity-category/RGB/cover/climate/mute checks pass")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
