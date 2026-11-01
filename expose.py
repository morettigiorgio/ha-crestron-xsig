"""Expose rules: push Home Assistant state to Crestron joins (HA -> Crestron).

Equivalent of the legacy YAML integration's ``to_joins``: a template (or an
entity_id + optional attribute, which becomes a template) is tracked with
``async_track_template_result`` and its result is written to the XSIG join
whenever it changes. Join type is taken from the join prefix:

* ``d123`` digital: "on"/"true" -> high, "off"/"false" -> low
* ``a123`` analog: rendered value converted with ``int(float(...))``
* ``s123`` serial: rendered value as a string

Values are also (re)pushed when the processor connects and when it requests
a full sync (XSIG 0xFD Send Status), so joins are correct even after a restart of either
side. Unchanged template results are deduplicated during normal tracking; a
forced reconnect/full-sync deliberately resends all values.
"""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import TrackTemplate, async_track_template_result
from homeassistant.helpers.template import Template
from homeassistant.exceptions import TemplateError

from .const import (
    CONF_ATTRIBUTE,
    CONF_ENTITY_ID,
    CONF_JOIN,
    CONF_NAME,
    CONF_VALUE_TEMPLATE,
    format_join,
    parse_join,
)
from .xsig_hub import CrestronXsigHub

_LOGGER = logging.getLogger(__name__)

_TRUE_STRINGS = {"on", "true", "1", "yes", "home"}
_FALSE_STRINGS = {"off", "false", "0", "no", "not_home", "unavailable", "unknown", ""}


def _convert(join_type: str, result) -> bool | int | str | None:
    """Convert a rendered template result to the join's value type."""
    if result is None:
        return None
    text = str(result)
    if join_type == "d":
        lowered = text.strip().lower()
        if lowered in _TRUE_STRINGS:
            return True
        if lowered in _FALSE_STRINGS:
            return False
        return None
    if join_type == "a":
        try:
            return int(float(text))
        except ValueError:
            return None
    return text


class ExposeManager:
    """Tracks HA state and pushes it to Crestron joins."""

    def __init__(
        self,
        hass: HomeAssistant,
        hub: CrestronXsigHub,
        items: list[dict],
    ) -> None:
        self.hass = hass
        self.hub = hub
        self._entries: list[dict] = []
        self._tracker = None
        self._warned_convert: set[str] = set()

        for item in items:
            parsed = parse_join(item.get(CONF_JOIN, ""))
            if parsed is None:
                _LOGGER.warning(
                    "Expose %r has an invalid join %r (expected e.g. 'd123', "
                    "'a45', 's7') — skipped",
                    item.get(CONF_NAME),
                    item.get(CONF_JOIN),
                )
                continue
            try:
                template = self._build_template(item)
            except TemplateError as err:
                _LOGGER.warning(
                    "Expose %r has an invalid template: %s — skipped",
                    item.get(CONF_NAME),
                    err,
                )
                continue
            self._entries.append(
                {
                    "item": item,
                    "template": template,
                    "type": parsed[0],
                    "number": parsed[1],
                    "last": None,
                    "has_sent": False,
                }
            )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def async_setup(self) -> None:
        if not self._entries:
            return
        self._tracker = async_track_template_result(
            self.hass,
            [TrackTemplate(entry["template"], None) for entry in self._entries],
            self._template_changed,
        )
        self.hub.register_callback(self._process_callback)
        self.hub.register_sync_all_joins_callback(self._sync_all)

    async def async_unload(self) -> None:
        if self._tracker is not None:
            self._tracker.async_remove()
            self._tracker = None
        self.hub.remove_callback(self._process_callback)
        self.hub.register_sync_all_joins_callback(None)

    # ------------------------------------------------------------------
    # Template building
    # ------------------------------------------------------------------
    def _build_template(self, item: dict) -> Template:
        if item.get(CONF_VALUE_TEMPLATE):
            return Template(str(item[CONF_VALUE_TEMPLATE]), self.hass)
        entity_id = str(item[CONF_ENTITY_ID])
        if item.get(CONF_ATTRIBUTE):
            source = (
                f"{{{{ state_attr('{entity_id}', '{item[CONF_ATTRIBUTE]}') }}}}"
            )
        else:
            source = f"{{{{ states('{entity_id}') }}}}"
        return Template(source, self.hass)

    # ------------------------------------------------------------------
    # Pushing
    # ------------------------------------------------------------------
    @callback
    def _template_changed(self, event, updates) -> None:
        for update in updates:
            entry = self._entry_for(update.template)
            if entry is None:
                continue
            # TrackTemplateResult has no ``exception`` attribute: when the
            # render fails, ``result`` holds the TemplateError itself (and
            # ``last_result`` the previous successful value).
            if isinstance(update.result, TemplateError):
                _LOGGER.warning(
                    "Expose %r: template error: %s",
                    entry["item"].get(CONF_NAME),
                    update.result,
                )
                continue
            self._push(entry, update.result, force=False)

    async def _process_callback(self, cbtype: str, value: str) -> None:
        """Push everything when the processor (re)connects."""
        if cbtype == "available" and str(value).strip().lower() in (
            "true",
            "1",
            "on",
        ):
            self._push_all()

    async def _sync_all(self) -> None:
        """Push everything when the processor requests a full sync (0xFD)."""
        self._push_all()

    @callback
    def _push_all(self) -> None:
        for entry in self._entries:
            try:
                result = entry["template"].async_render(parse_result=False)
            except TemplateError as err:
                _LOGGER.warning(
                    "Expose %r: template error on sync: %s",
                    entry["item"].get(CONF_NAME),
                    err,
                )
                continue
            self._push(entry, result, force=True)

    @callback
    def _push(self, entry: dict, result, *, force: bool) -> None:
        join_type, number = entry["type"], entry["number"]
        key = format_join(join_type, number)
        value = _convert(join_type, result)
        if value is None:
            if key not in self._warned_convert:
                _LOGGER.warning(
                    "Expose %r: cannot convert %r to a %s value for join %s",
                    entry["item"].get(CONF_NAME),
                    result,
                    {"d": "digital", "a": "analog", "s": "serial"}[join_type],
                    key,
                )
                self._warned_convert.add(key)
            return
        if not force and entry["has_sent"] and entry["last"] == value:
            return
        if join_type == "d":
            self.hub.set_digital(number, value)
        elif join_type == "a":
            self.hub.set_analog(number, value)
        else:
            self.hub.set_serial(number, value)
        entry["last"] = value
        entry["has_sent"] = True

    def _entry_for(self, template) -> dict | None:
        # TrackTemplateResult normally returns the same Template instance,
        # but identity must win when multiple entries have equal templates.
        for entry in self._entries:
            if entry["template"] is template:
                return entry
        for entry in self._entries:
            if entry["template"] == template:
                return entry
        return None
