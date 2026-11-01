# Testing status

Local software checks and live Home Assistant/Crestron verification are
separate evidence. Passing a local check does not prove end-to-end behavior.

## Current evidence

- **Focused local checks:** `python tools/test_xsig_hub_protocol.py` runs six
  asyncio protocol tests without Home Assistant. `python tools/check_flows.py`
  checks form-schema serialization and selected entity-category, RGB, climate
  unit-selector, and media-player mute-mode behavior using Home Assistant
  stubs. Both commands pass locally; the flow check includes Add/Edit
  persistence and validation for these selectors. They are targeted checks, not
  a comprehensive integration suite.
- **Automation/HACS:** `.github/workflows/ci.yaml` now runs Ruff, the local
  protocol/config-flow checks, hassfest and HACS validation on push and pull
  request. Ruff and the two local checks pass here; hassfest/HACS action results
  await the workflow's first run on GitHub. HACS installation/update itself has
  not yet been smoke-tested. The local checks do not validate behavior in a
  running Home Assistant.
- **Hardware/UI checks reported by the maintainer:** earlier logs record
  reconnect/full-sync, pulse lifecycle, serial receive, direct join-service
  validation and several entity checks. The latest report marks PASS for both
  mute modes, Celsius/Fahrenheit conversion, UI validation messages, delayed
  actions, `reload_connection`, duplicate exposes, service cleanup on unload,
  serial-boundary and soak checks, entity deletion, shared-device assignment,
  and additional edge cases. The reported environment is Home Assistant
  Container (Core 2026.10.4, Frontend 20260930.5) with a Crestron DIN-AP3
  running firmware 1.8001.5761.28479. The test date and per-case matrix were
  not supplied.
- **Legacy YAML import:** the `crestron.yaml` import flow is implemented, but
  its import test has not yet been run. The flow-schema check only confirms
  that its forms serialize; it does not test YAML parsing, import results or
  the full Home Assistant UI flow. Treat import as in development and
  unverified.

## Before a release

Record the Home Assistant version, processor/model/firmware, and results.
Run software checks and hardware checks separately, and report which were
actually completed rather than marking an entire category as tested.

### Home Assistant checks

- **Reported PASS:** Add/Edit and UI validation, removal of entities, shared
  device assignment, translated validation errors, duplicate expose sources,
  service cleanup on integration removal, `reload_connection`, both media
  mute modes, °C/°F conversion, and the additional edge-case coverage.
- The environment is recorded above; the test date and detailed per-case
  results were not recorded, so these remain maintainer-reported outcomes.
- **Still unverified:** legacy YAML import with representative valid and
  invalid input, including the review/confirmation flow and resulting rules.

### Crestron hardware checks

- **Reported PASS:** reconnect/full-sync and reboot handling from earlier test
  records; entity commands/feedback and scaling checks; delayed actions,
  `reload_connection`, service cleanup, both mute modes, °C/°F conversion,
  serial-boundary test, soak/stability, and the recent edge-case coverage.
- The environment is recorded above, but detailed run parameters and the test
  date are unavailable. The only explicitly deferred functional test is legacy
  YAML import.
- HACS install/update has not been tested; it requires the repository to be
  published first. This is a distribution check, not an XSIG functional test.

## Development workflow

Reloading a config entry reloads integration data but does not re-import
Python modules. Restart Home Assistant Core after code changes. Debug logging
can be enabled with:

```yaml
action: logger.set_level
data:
  custom_components.crestron_xsig: debug
```

Reset the level to `info` when finished. Logs can help diagnose protocol
traffic, but are not a substitute for an observed Home Assistant result or a
hardware check.
