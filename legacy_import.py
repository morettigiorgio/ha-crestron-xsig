"""Map a legacy YAML ``crestron:`` configuration to this integration's options.

The legacy YAML integration (npope / georgesak, ``custom_components/crestron``)
was configured with::

    port: 16384
    to_joins:            # HA -> Crestron (XSIG outputs): value_template or
      - join: a2         # entity_id (+ attribute) pushed to the join
        value_template: "{{states('input_number.x')|int(0)}}"
    from_joins:          # Crestron -> HA (XSIG inputs): run a script/service
      - join: d451       # when the join is received
        script:
          action: switch.toggle
          target:
            entity_id: switch.x

This module converts that structure into the ``exposes`` / ``actions`` option
lists used by the config-entry (UI) version of this integration:

* ``to_joins``   -> ``exposes`` (HA -> Crestron bridge rules)
* ``from_joins`` -> ``actions`` (Crestron -> HA rules, run with {{ value }})

Intentionally pure Python + PyYAML with no Home Assistant imports (a small
``const`` import fallback keeps it runnable standalone for tests).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field

import yaml

try:
    from .const import (
        CONF_ATTRIBUTE,
        CONF_ENTITY_ID,
        CONF_ID,
        CONF_JOIN,
        CONF_NAME,
        CONF_SCRIPT,
        CONF_TRIGGER_ON,
        CONF_VALUE_TEMPLATE,
        TRIGGER_ON_PRESS,
        parse_join,
    )
except ImportError:  # standalone (tests / CLI tools)
    from const import (  # type: ignore
        CONF_ATTRIBUTE,
        CONF_ENTITY_ID,
        CONF_ID,
        CONF_JOIN,
        CONF_NAME,
        CONF_SCRIPT,
        CONF_TRIGGER_ON,
        CONF_VALUE_TEMPLATE,
        TRIGGER_ON_PRESS,
        parse_join,
    )

# Accepted YAML spellings for the two rule lists.
_TO_KEYS = ("to_joins", "to_hub")
_FROM_KEYS = ("from_joins", "from_hub")


@dataclass
class LegacyImportResult:
    """Outcome of parsing a legacy crestron.yaml."""

    exposes: list[dict] = field(default_factory=list)
    actions: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    port: int | None = None
    error: str | None = None


def map_legacy_yaml(text: str) -> LegacyImportResult:
    """Parse legacy YAML text and return the mapped rules + warnings."""
    result = LegacyImportResult()
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as err:
        result.error = f"YAML parse error: {err}"
        return result

    if data is None:
        result.error = "The YAML document is empty."
        return result
    if not isinstance(data, dict):
        result.error = (
            "The YAML document is not a mapping "
            "(expected 'port:', 'to_joins:', ...)."
        )
        return result

    port = data.get("port")
    if isinstance(port, int):
        result.port = port

    unknown = [key for key in data if key not in ("port", *_TO_KEYS, *_FROM_KEYS)]
    if unknown:
        result.warnings.append(
            f"Unknown top-level keys ignored: {', '.join(sorted(map(str, unknown)))}"
        )

    comment_names = _comment_names(text)

    to_items = _first_list(data, _TO_KEYS)
    from_items = _first_list(data, _FROM_KEYS)

    # -- to_joins -> exposes -------------------------------------------------
    seen_joins: dict[str, int] = {}
    for index, raw in enumerate(to_items):
        if not isinstance(raw, dict):
            result.warnings.append(
                f"to_joins entry #{index + 1} is not a mapping — skipped"
            )
            continue
        item = _map_to_join(
            raw,
            _name_at(comment_names["to_joins"], index),
            result.warnings,
            index,
        )
        if item is None:
            continue
        join = item[CONF_JOIN]
        if join in seen_joins:
            # The legacy hub stored to_joins in a dict keyed by join: the
            # later definition silently replaced the earlier one. Keep that
            # behavior, but say so.
            result.warnings.append(
                f"to_joins: join {join} is defined more than once — the later "
                "definition replaces the earlier one (same as the legacy "
                "component)."
            )
            result.exposes[seen_joins[join]] = item
        else:
            seen_joins[join] = len(result.exposes)
            result.exposes.append(item)

    # -- from_joins -> actions ----------------------------------------------
    for index, raw in enumerate(from_items):
        if not isinstance(raw, dict):
            result.warnings.append(
                f"from_joins entry #{index + 1} is not a mapping — skipped"
            )
            continue
        item = _map_from_join(
            raw,
            _name_at(comment_names["from_joins"], index),
            result.warnings,
            index,
        )
        if item is not None:
            result.actions.append(item)

    return result


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------


def _first_list(data: dict, keys: tuple[str, ...]) -> list:
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):  # tolerate a single mapping entry
            return [value]
    return []


def _map_to_join(raw: dict, name: str, warnings: list[str], index: int) -> dict | None:
    join = str(raw.get(CONF_JOIN, "")).strip().lower()
    if parse_join(join) is None:
        warnings.append(
            f"to_joins entry #{index + 1}: invalid join {raw.get(CONF_JOIN)!r} "
            "(expected e.g. 'd451', 'a101', 's7') — skipped"
        )
        return None

    hint = name or _content_hint(raw)
    item = {
        CONF_NAME: f"{hint} ({join})" if hint else f"Expose {join}",
        CONF_JOIN: join,
    }

    value_template = raw.get(CONF_VALUE_TEMPLATE)
    entity_id = raw.get(CONF_ENTITY_ID)
    attribute = raw.get(CONF_ATTRIBUTE)

    if value_template:
        item[CONF_VALUE_TEMPLATE] = str(value_template)
    elif entity_id:
        item[CONF_ENTITY_ID] = str(entity_id)
        if attribute:
            item[CONF_ATTRIBUTE] = str(attribute)
    else:
        warnings.append(
            f"to_joins entry #{index + 1} ({join}): no value_template and no "
            "entity_id — skipped"
        )
        return None
    item[CONF_ID] = _legacy_rule_id("expose", index, item)
    return item


def _map_from_join(raw: dict, name: str, warnings: list[str], index: int) -> dict | None:
    join = str(raw.get(CONF_JOIN, "")).strip().lower()
    if parse_join(join) is None:
        warnings.append(
            f"from_joins entry #{index + 1}: invalid join {raw.get(CONF_JOIN)!r} — skipped"
        )
        return None

    script = raw.get(CONF_SCRIPT)
    if script is None:
        # Tolerate the service/service_data (or action/data) flat form.
        service = raw.get("action", raw.get("service"))
        if service:
            action = {"action": str(service)}
            data = raw.get("data", raw.get("service_data"))
            if data:
                action["data"] = data
            if raw.get("target"):
                action["target"] = raw["target"]
            script = [action]

    if isinstance(script, dict):
        script = [script]
    if not isinstance(script, list) or not script:
        warnings.append(
            f"from_joins entry #{index + 1} ({join}): no runnable 'script' — skipped"
        )
        return None

    hint = name or _content_hint(raw)
    item = {
        CONF_NAME: f"{hint} ({join})" if hint else f"Action {join}",
        CONF_JOIN: join,
        # Legacy behavior: digital joins trigger on the high (press) edge only,
        # so momentary presses don't call the service twice.
        CONF_TRIGGER_ON: TRIGGER_ON_PRESS,
        CONF_SCRIPT: script,
    }
    item[CONF_ID] = _legacy_rule_id("action", index, item)
    return item


def _legacy_rule_id(rule_type: str, index: int, item: dict) -> str:
    """Stable ID for a legacy rule at the same position/content in a YAML file."""
    payload = json.dumps(
        [rule_type, index, item], sort_keys=True, separators=(",", ":"), default=str
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
    return f"legacy_{digest}"


def _name_at(names: list[str], index: int) -> str:
    if index < len(names):
        return names[index]
    return ""


_ENTITY_HINT_RE = re.compile(
    r"(?:states|state_attr)\(\s*['\"]([A-Za-z0-9_]+\.[A-Za-z0-9_]+)"
)


def _content_hint(raw: dict) -> str:
    """Best-effort name from the entry content: the object_id of the first
    Home Assistant entity referenced by entity_id or by a template, or the
    name of the called service/script."""
    entity_id = _find_entity_id(raw)
    if entity_id:
        return entity_id.split(".", 1)[1]
    for text in _iter_strings(raw):
        match = _ENTITY_HINT_RE.search(text)
        if match:
            return match.group(1).split(".", 1)[1]
    action = _find_action(raw)
    if action:
        return action.split(".")[-1]
    return ""


def _find_action(value) -> str | None:
    if isinstance(value, dict):
        for key, sub in value.items():
            if key in ("action", "service") and isinstance(sub, str):
                return sub
            found = _find_action(sub)
            if found:
                return found
    elif isinstance(value, list):
        for sub in value:
            found = _find_action(sub)
            if found:
                return found
    return None


def _find_entity_id(value) -> str | None:
    if isinstance(value, dict):
        for key, sub in value.items():
            if key == CONF_ENTITY_ID and isinstance(sub, str):
                return sub
            found = _find_entity_id(sub)
            if found:
                return found
    elif isinstance(value, list):
        for sub in value:
            found = _find_entity_id(sub)
            if found:
                return found
    return None


def _iter_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for sub in value.values():
            yield from _iter_strings(sub)
    elif isinstance(value, list):
        for sub in value:
            yield from _iter_strings(sub)


# ---------------------------------------------------------------------------
# Comment-based naming heuristic
# ---------------------------------------------------------------------------

_SECTION_RE = re.compile(r"^(to_joins|from_joins|to_hub|from_hub)\s*:")
_ITEM_RE = re.compile(r"^-\s*join\s*:")
_KEYLIKE_RE = re.compile(r"^[A-Za-z_][A-Za-z_0-9]*\s*:")
_INLINE_COMMENT_RE = re.compile(r"\s#+\s*(\S.*)$")


def _trailing_comment(line: str) -> str | None:
    """Return the inline trailing comment of a code line, if any."""
    match = _INLINE_COMMENT_RE.search(line)
    return match.group(1).strip() if match else None


def _comment_names(text: str) -> dict[str, list[str]]:
    """Collect a descriptive name for each ``- join:`` item.

    The legacy file has very good comments, either inline (``- join: d451``
    ... ``# POE1_Kitchen_Press_(2s)``) or as a standalone line above the item
    (``# Cameras``). Name priority: comment on the join line itself, then the
    last inline comment inside the item block, then the comment above the
    item, then the last section comment. Purely best-effort.
    """
    names: dict[str, list[str]] = {"to_joins": [], "from_joins": []}
    section: str | None = None
    pending: str | None = None        # standalone comment above the item
    join_comment: str | None = None   # inline comment on the - join: line
    trailing: list[str] = []          # inline comments inside the item block
    item_open = False

    def flush() -> None:
        nonlocal item_open, pending, join_comment, trailing
        if not item_open:
            return
        if section is not None:
            if join_comment:
                name = join_comment
            elif trailing:
                name = trailing[-1]
            else:
                name = pending or ""
            names[section].append(name[:60])
        item_open = False
        pending = None
        join_comment = None
        trailing = []

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        section_match = _SECTION_RE.match(stripped)
        if section_match:
            flush()
            key = section_match.group(1)
            section = "to_joins" if key in _TO_KEYS else "from_joins"
            pending = None
            continue

        if stripped.startswith("#"):
            comment = stripped.lstrip("#").strip()
            if (
                not comment
                or comment.startswith("!")
                or comment.startswith("-")
                or "- join:" in comment
                or _KEYLIKE_RE.match(comment)
                or not any(ch.isalnum() for ch in comment)
            ):
                continue
            if item_open:
                flush()
            pending = comment
            continue

        if _ITEM_RE.match(stripped):
            flush()
            item_open = True
            inline = _trailing_comment(line)
            if inline:
                join_comment = inline
            continue

        if item_open:
            inline = _trailing_comment(line)
            if inline:
                trailing.append(inline)

    flush()
    return names
