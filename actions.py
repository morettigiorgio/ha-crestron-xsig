"""Action rules: run Home Assistant scripts when a Crestron join arrives.

Equivalent of the legacy YAML integration's ``from_joins``: when a join value
is received from the processor, a script sequence runs with ``{{ value }}``
in its variables (digital joins pass true/false, analog an int, serial the
string). Digital joins only trigger on the high (press) edge by default, so
momentary presses do not run the action twice; that can be changed per rule
with ``trigger_on: release | both``.
"""

from __future__ import annotations

import asyncio
import logging

from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers.script import Script

from .const import (
    CONF_JOIN,
    CONF_NAME,
    CONF_SCRIPT,
    CONF_TRIGGER_ON,
    TRIGGER_ON_BOTH,
    TRIGGER_ON_PRESS,
    TRIGGER_ON_RELEASE,
    format_join,
    native_join_value,
    parse_join,
)
from .xsig_hub import CrestronXsigHub

_LOGGER = logging.getLogger(__name__)


class ActionManager:
    """Runs configured script sequences on received join values."""

    def __init__(
        self,
        hass: HomeAssistant,
        hub: CrestronXsigHub,
        items: list[dict],
    ) -> None:
        self.hass = hass
        self.hub = hub
        self._rules: list[dict] = []
        self._context = Context()
        self._tasks: set[asyncio.Task] = set()

        for item in items:
            parsed = parse_join(item.get(CONF_JOIN, ""))
            if parsed is None:
                _LOGGER.warning(
                    "Action %r has an invalid join %r (expected e.g. 'd123', "
                    "'a45', 's7') — skipped",
                    item.get(CONF_NAME),
                    item.get(CONF_JOIN),
                )
                continue
            sequence = item.get(CONF_SCRIPT)
            if isinstance(sequence, dict):
                sequence = [sequence]
            if not isinstance(sequence, list) or not sequence:
                _LOGGER.warning(
                    "Action %r (%s) has no runnable script — skipped",
                    item.get(CONF_NAME),
                    item.get(CONF_JOIN),
                )
                continue
            try:
                script = Script(
                    self.hass,
                    sequence,
                    f"Crestron join {item.get(CONF_JOIN)} ({item.get(CONF_NAME, '')})",
                    "crestron_xsig",
                )
            except Exception as err:  # noqa: BLE001 - invalid action config
                _LOGGER.warning(
                    "Action %r (%s): invalid script: %s — skipped",
                    item.get(CONF_NAME),
                    item.get(CONF_JOIN),
                    err,
                )
                continue
            self._rules.append(
                {
                    "item": item,
                    "type": parsed[0],
                    "number": parsed[1],
                    "script": script,
                    "lock": asyncio.Lock(),
                }
            )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def async_setup(self) -> None:
        if not self._rules:
            return
        self.hub.register_callback(self._process_callback)

    async def async_unload(self) -> None:
        self.hub.remove_callback(self._process_callback)
        self._cancel_pending()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        for rule in self._rules:
            # HA's Script has no synchronous stop(); async_stop() stops any
            # in-flight runs (stable API since at least 2023.1).
            await rule["script"].async_stop()

    def _cancel_pending(self) -> None:
        """Cancel actions still running when the processor disconnects/unloads."""
        for task in tuple(self._tasks):
            task.cancel()

    # ------------------------------------------------------------------
    # Triggering
    # ------------------------------------------------------------------
    async def _process_callback(self, cbtype: str, value: str) -> None:
        if cbtype == "available":
            if str(value).strip().lower() in ("false", "0", "off"):
                self._cancel_pending()
            return
        for rule in self._rules:
            join = format_join(rule["type"], rule["number"])
            if cbtype != join:
                continue
            trigger_on = rule["item"].get(CONF_TRIGGER_ON, TRIGGER_ON_PRESS)
            if not _should_trigger(rule["type"], value, trigger_on):
                continue
            variables = {"value": native_join_value(rule["type"], value)}
            task = self.hass.async_create_task(
                self._run_rule(rule, variables, join),
                name=f"crestron_xsig_action_{rule['item'].get(CONF_NAME, join)}",
            )
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _run_rule(self, rule: dict, variables: dict, join: str) -> None:
        """Run independently of join dispatch, preserving per-rule order."""
        try:
            async with rule["lock"]:
                await rule["script"].async_run(variables, self._context)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - a broken action must not break the hub
            _LOGGER.exception(
                "Error running action %r for join %s",
                rule["item"].get(CONF_NAME),
                join,
            )


def _should_trigger(join_type: str, value: str, trigger_on: str) -> bool:
    """Digital joins trigger on the configured edge; analog/serial always."""
    if join_type != "d":
        return True
    pressed = str(value) in ("True", "true", "1")
    if trigger_on == TRIGGER_ON_RELEASE:
        return not pressed
    if trigger_on == TRIGGER_ON_BOTH:
        return True
    return pressed
