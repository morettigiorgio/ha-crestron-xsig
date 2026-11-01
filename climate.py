"""Climate platform for Crestron XSIG."""

from __future__ import annotations

import logging

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.components.climate.const import FAN_AUTO, FAN_ON

from .const import (
    CONF_C1_JOIN,
    CONF_C2_JOIN,
    CONF_COOL_SP_JOIN,
    CONF_FA_JOIN,
    CONF_FAN_AUTO_JOIN,
    CONF_FAN_ON_JOIN,
    CONF_H1_JOIN,
    CONF_H2_JOIN,
    CONF_HEAT_SP_JOIN,
    CONF_HUMIDITY_JOIN,
    CONF_ID,
    CONF_MAX_TEMP,
    CONF_MIN_TEMP,
    CONF_NAME,
    CONF_PRESETS,
    CONF_REG_TEMP_JOIN,
    CONF_TARGET_HUMIDITY_JOIN,
    CONF_TEMP_DIVISOR,
    CONF_TEMP_STEP,
    CONF_TEMP_UNIT,
    CONF_HUMIDITY_DIVISOR,
    DATA_HUB,
    DOMAIN,
    OPT_CLIMATES,
)
from .entity import CrestronEntity, build_device_info

_LOGGER = logging.getLogger(__name__)


def _safe_divisor(value, fallback: float, field: str, item: dict) -> float:
    """Defensive clamp (KI-034): hand-edited options can hold a divisor of
    0 / negative / non-numeric and every state read would crash
    (ZeroDivisionError) or flip the sign of temperatures/humidity."""
    try:
        divisor = float(value)
    except (TypeError, ValueError):
        divisor = 0.0
    if divisor <= 0:
        _LOGGER.warning(
            "Climate %r: invalid %s %r, falling back to %s",
            item.get(CONF_NAME),
            field,
            value,
            fallback,
        )
        return float(fallback)
    return divisor


async def async_setup_entry(hass, entry, async_add_entities):
    hub = hass.data[DOMAIN][entry.entry_id][DATA_HUB]
    unit = hass.config.units.temperature_unit
    entities = [
        CrestronThermostat(
            hub, entry.entry_id, item, unit, build_device_info(hass, entry, item)
        )
        for item in entry.options.get(OPT_CLIMATES, [])
    ]
    async_add_entities(entities)


class CrestronThermostat(CrestronEntity, ClimateEntity):
    """Thermostat with joins documented in docs/WIRING.md.

    Everything except name and current temperature is optional: with
    both setpoints HA uses a temperature range, with one a single
    setpoint; hvac/fan modes are derived from the configured joins;
    presets map to one digital join each.
    """

    # display order / priority when several mode reads are high
    _MODE_JOINS = (
        (HVACMode.HEAT_COOL, "mode_auto"),
        (HVACMode.HEAT, "mode_heat"),
        (HVACMode.COOL, "mode_cool"),
        (HVACMode.FAN_ONLY, "mode_fan_only"),
        (HVACMode.DRY, "mode_dry"),
        (HVACMode.OFF, "mode_off"),
    )

    def __init__(self, hub, entry_id, item: dict, unit: str, device_info=None):
        unique_id = f"{entry_id}_climate_{item[CONF_ID]}"
        super().__init__(hub, entry_id, unique_id, item[CONF_NAME], device_info, item)
        self._attr_temperature_unit = unit
        self._processor_temp_unit = self._normalize_temp_unit(
            item.get(CONF_TEMP_UNIT, unit), unit
        )

        self._heat_sp_join = item.get(CONF_HEAT_SP_JOIN)
        self._cool_sp_join = item.get(CONF_COOL_SP_JOIN)
        self._reg_temp_join = item[CONF_REG_TEMP_JOIN]
        # scaling: raw join value = physical value * divisor
        self._temp_divisor = _safe_divisor(
            item.get(CONF_TEMP_DIVISOR), 10, CONF_TEMP_DIVISOR, item
        )
        self._humidity_divisor = _safe_divisor(
            item.get(CONF_HUMIDITY_DIVISOR), 1, CONF_HUMIDITY_DIVISOR, item
        )

        self._mode_joins = {
            mode: item.get(f"{key}_join")
            for mode, key in self._MODE_JOINS
            if item.get(f"{key}_join")
        }
        self._attr_hvac_modes = list(self._mode_joins)

        self._fan_on_join = item.get(CONF_FAN_ON_JOIN)
        self._fan_auto_join = item.get(CONF_FAN_AUTO_JOIN)
        self._attr_fan_modes = (
            [FAN_ON, FAN_AUTO] if (self._fan_on_join or self._fan_auto_join) else None
        )

        self._h1_join = item.get(CONF_H1_JOIN)
        self._h2_join = item.get(CONF_H2_JOIN)
        self._c1_join = item.get(CONF_C1_JOIN)
        self._c2_join = item.get(CONF_C2_JOIN)
        self._fa_join = item.get(CONF_FA_JOIN)

        self._humidity_join = item.get(CONF_HUMIDITY_JOIN)
        self._target_humidity_join = item.get(CONF_TARGET_HUMIDITY_JOIN)

        # presets: {name: digital join}, set one high at a time
        self._preset_joins = {
            str(name): int(join)
            for name, join in (item.get(CONF_PRESETS) or {}).items()
        }
        self._attr_preset_modes = list(self._preset_joins) or None

        if item.get(CONF_MIN_TEMP) is not None:
            self._attr_min_temp = float(item[CONF_MIN_TEMP])
        if item.get(CONF_MAX_TEMP) is not None:
            self._attr_max_temp = float(item[CONF_MAX_TEMP])
        if item.get(CONF_TEMP_STEP) is not None:
            self._attr_target_temperature_step = float(item[CONF_TEMP_STEP])

        features = ClimateEntityFeature(0)
        if self._heat_sp_join and self._cool_sp_join:
            features |= ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        elif self._heat_sp_join or self._cool_sp_join:
            features |= ClimateEntityFeature.TARGET_TEMPERATURE
        if self._attr_fan_modes:
            features |= ClimateEntityFeature.FAN_MODE
        if self._preset_joins:
            features |= ClimateEntityFeature.PRESET_MODE
        if self._target_humidity_join:
            features |= ClimateEntityFeature.TARGET_HUMIDITY
        if any(mode != HVACMode.OFF for mode in self._mode_joins):
            features |= ClimateEntityFeature.TURN_ON
        if HVACMode.OFF in self._mode_joins:
            features |= ClimateEntityFeature.TURN_OFF
        self._attr_supported_features = features

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_temp_unit(unit, fallback):
        """Normalize configured C/F values and fall back on invalid options."""
        text = str(unit).strip().upper().replace("°", "")
        if text in ("C", "CELSIUS"):
            return "C"
        if text in ("F", "FAHRENHEIT"):
            return "F"
        fallback_text = str(fallback).strip().upper().replace("°", "")
        return "F" if fallback_text.startswith("F") else "C"

    @staticmethod
    def _convert_temperature(value, source_unit, target_unit):
        if source_unit == target_unit:
            return value
        if source_unit == "C":
            return value * 9 / 5 + 32
        return (value - 32) * 5 / 9

    def _temperature_from_hub(self, join):
        raw_temperature = self._hub.get_analog(join) / self._temp_divisor
        ha_unit = self._normalize_temp_unit(self._attr_temperature_unit, "C")
        return self._convert_temperature(
            raw_temperature, self._processor_temp_unit, ha_unit
        )

    @property
    def current_temperature(self):
        return self._temperature_from_hub(self._reg_temp_join)

    @property
    def current_humidity(self):
        if self._humidity_join is None:
            return None
        return self._hub.get_analog(self._humidity_join) / self._humidity_divisor

    @property
    def target_humidity(self):
        if self._target_humidity_join is None:
            return None
        return self._hub.get_analog(self._target_humidity_join) / self._humidity_divisor

    @property
    def target_temperature(self):
        join = self._heat_sp_join or self._cool_sp_join
        if join is None or (self._heat_sp_join and self._cool_sp_join):
            return None
        return self._temperature_from_hub(join)

    @property
    def target_temperature_high(self):
        if self._cool_sp_join is None:
            return None
        return self._temperature_from_hub(self._cool_sp_join)

    @property
    def target_temperature_low(self):
        if self._heat_sp_join is None:
            return None
        return self._temperature_from_hub(self._heat_sp_join)

    @property
    def hvac_mode(self):
        for mode, join in self._mode_joins.items():
            if self._hub.get_digital(join):
                return mode
        return None

    @property
    def fan_mode(self):
        if self._fan_auto_join and self._hub.get_digital(self._fan_auto_join):
            return FAN_AUTO
        if self._fan_on_join and self._hub.get_digital(self._fan_on_join):
            return FAN_ON
        # Fallback: no mode join active but the fan is really running (FA)
        if self._fa_join and self._hub.get_digital(self._fa_join):
            return FAN_ON
        return None

    @property
    def preset_mode(self):
        for name, join in self._preset_joins.items():
            if self._hub.get_digital(join):
                return name
        return None

    @property
    def hvac_action(self):
        heating = (self._h1_join and self._hub.get_digital(self._h1_join)) or (
            self._h2_join and self._hub.get_digital(self._h2_join)
        )
        cooling = (self._c1_join and self._hub.get_digital(self._c1_join)) or (
            self._c2_join and self._hub.get_digital(self._c2_join)
        )
        if heating:
            return HVACAction.HEATING
        if cooling:
            return HVACAction.COOLING
        if self._fa_join and self._hub.get_digital(self._fa_join):
            return HVACAction.FAN
        return HVACAction.IDLE

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    async def async_set_hvac_mode(self, hvac_mode):
        target_join = self._mode_joins.get(hvac_mode)
        if target_join is None:
            return
        for join in self._mode_joins.values():
            if join != target_join:
                self._set_digital(join, False)
        self._set_digital(target_join, True)

    async def async_turn_on(self):
        for mode, join in self._mode_joins.items():
            if mode != HVACMode.OFF:
                await self.async_set_hvac_mode(mode)
                return

    async def async_turn_off(self):
        if HVACMode.OFF in self._mode_joins:
            await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_fan_mode(self, fan_mode):
        if fan_mode == FAN_AUTO:
            if self._fan_on_join:
                self._set_digital(self._fan_on_join, False)
            if self._fan_auto_join:
                self._set_digital(self._fan_auto_join, True)
        elif fan_mode == FAN_ON:
            if self._fan_auto_join:
                self._set_digital(self._fan_auto_join, False)
            if self._fan_on_join:
                self._set_digital(self._fan_on_join, True)

    async def async_set_preset_mode(self, preset_mode):
        target_join = self._preset_joins.get(preset_mode)
        if target_join is None:
            return
        for join in self._preset_joins.values():
            if join != target_join:
                self._set_digital(join, False)
        self._set_digital(target_join, True)

    def _set_temperature_join(self, join, temperature) -> bool:
        ha_unit = self._normalize_temp_unit(self._attr_temperature_unit, "C")
        processor_temperature = self._convert_temperature(
            temperature, ha_unit, self._processor_temp_unit
        )
        raw_value = round(processor_temperature * self._temp_divisor)
        if not self._hub.set_analog(join, raw_value):
            return False
        self._hub.update_analog(join, raw_value)
        return True

    async def async_set_temperature(self, **kwargs):
        updated = False
        if "target_temp_low" in kwargs and self._heat_sp_join:
            updated |= self._set_temperature_join(
                self._heat_sp_join, kwargs["target_temp_low"]
            )
        if "target_temp_high" in kwargs and self._cool_sp_join:
            updated |= self._set_temperature_join(
                self._cool_sp_join, kwargs["target_temp_high"]
            )
        if "temperature" in kwargs:
            join = self._heat_sp_join or self._cool_sp_join
            if join is not None:
                updated |= self._set_temperature_join(join, kwargs["temperature"])
        if updated:
            self.async_write_ha_state()

    async def async_set_humidity(self, humidity: int):
        if self._target_humidity_join is not None:
            raw_value = int(humidity * self._humidity_divisor)
            if self._hub.set_analog(self._target_humidity_join, raw_value):
                self._hub.update_analog(self._target_humidity_join, raw_value)
                self.async_write_ha_state()
