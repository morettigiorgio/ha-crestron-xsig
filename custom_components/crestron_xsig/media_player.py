"""Media player platform for Crestron XSIG."""

from __future__ import annotations

from homeassistant.components.media_player import MediaPlayerEntity, MediaPlayerEntityFeature
from homeassistant.const import STATE_OFF, STATE_ON

from .const import (
    CONF_ID,
    CONF_MUTE_JOIN,
    CONF_MUTE_MODE,
    CONF_NAME,
    CONF_SOURCE_NUM_JOIN,
    CONF_SOURCES,
    CONF_VOLUME_DOWN_JOIN,
    CONF_VOLUME_JOIN,
    CONF_VOLUME_UP_JOIN,
    DATA_HUB,
    DOMAIN,
    OPT_MEDIA_PLAYERS,
    MUTE_MODE_SET_STATE,
    MUTE_MODE_TOGGLE_PULSE,
)
from .entity import CrestronEntity, build_device_info


async def async_setup_entry(hass, entry, async_add_entities):
    hub = hass.data[DOMAIN][entry.entry_id][DATA_HUB]
    entities = [
        CrestronMediaPlayer(hub, entry.entry_id, item, build_device_info(hass, entry, item))
        for item in entry.options.get(OPT_MEDIA_PLAYERS, [])
    ]
    async_add_entities(entities)


class CrestronMediaPlayer(CrestronEntity, MediaPlayerEntity):
    _attr_device_class = "speaker"
    _attr_supported_features = (
        MediaPlayerEntityFeature.SELECT_SOURCE
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
    )

    def __init__(self, hub, entry_id, item: dict, device_info=None):
        unique_id = f"{entry_id}_media_player_{item[CONF_ID]}"
        super().__init__(hub, entry_id, unique_id, item[CONF_NAME], device_info, item)
        self._mute_join = item[CONF_MUTE_JOIN]
        self._mute_mode = item.get(CONF_MUTE_MODE, MUTE_MODE_TOGGLE_PULSE)
        if self._mute_mode not in (MUTE_MODE_TOGGLE_PULSE, MUTE_MODE_SET_STATE):
            self._mute_mode = MUTE_MODE_TOGGLE_PULSE
        self._volume_up_join = item[CONF_VOLUME_UP_JOIN]
        self._volume_down_join = item[CONF_VOLUME_DOWN_JOIN]
        self._volume_join = item[CONF_VOLUME_JOIN]
        self._source_number_join = item[CONF_SOURCE_NUM_JOIN]
        # Stored with int keys in options, but JSON round-trips them as str.
        self._sources = {int(k): v for k, v in item.get(CONF_SOURCES, {}).items()}

    @property
    def source_list(self):
        return list(self._sources.values())

    @property
    def source(self):
        source_num = self._hub.get_analog(self._source_number_join)
        return self._sources.get(source_num)

    @property
    def state(self):
        return STATE_OFF if self._hub.get_analog(self._source_number_join) == 0 else STATE_ON

    @property
    def is_volume_muted(self) -> bool:
        return self._hub.get_digital(self._mute_join)

    @property
    def volume_level(self) -> float:
        return self._hub.get_analog(self._volume_join) / 65535

    async def async_mute_volume(self, mute):
        if self._mute_mode == MUTE_MODE_SET_STATE:
            target = bool(mute)
            if self._hub.get_digital(self._mute_join) != target:
                if self._set_digital(self._mute_join, target):
                    self._hub.update_digital(self._mute_join, target)
                    self.async_write_ha_state()
            return
        self._pulse(self._mute_join)

    async def async_volume_up(self, **kwargs):
        self._pulse(self._volume_up_join)

    async def async_volume_down(self, **kwargs):
        self._pulse(self._volume_down_join)

    async def async_set_volume_level(self, volume):
        self._hub.set_analog(self._volume_join, int(volume * 65535))

    async def async_select_source(self, source):
        for input_num, name in self._sources.items():
            if name == source:
                self._hub.set_analog(self._source_number_join, input_num)
                return

    async def async_turn_off(self, **kwargs):
        self._hub.set_analog(self._source_number_join, 0)

    async def async_turn_on(self, **kwargs):
        self._hub.set_analog(self._source_number_join, 1)
