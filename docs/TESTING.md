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
- **Automation/Marketplace catalog:** `.github/workflows/ci.yaml` runs Ruff,
  the local protocol/config-flow checks, hassfest and the HACS catalog
  validation action on push and pull request. Home Assistant 2026.11 replaced
  the HACS custom integration with the built-in Marketplace; the Marketplace
  continues to use the HACS catalog, `hacs.json`, and validator. Ruff and the
  two local checks pass here; hassfest/catalog-action results await the
  workflow's first run on GitHub. Marketplace installation/update itself has
  not yet been smoke-tested. The local checks do not validate behavior in a
  running Home Assistant.
- **Hardware:** The reported environment is Home Assistant
  Container (Core 2026.10.4, Frontend 20260930.5) with a Crestron DIN-AP3
  running firmware 1.8001.5761.28479. The test date and per-case matrix were
  not supplied.
- **Legacy YAML import:** the maintainer manually tested the import through
  the Home Assistant UI and confirmed that it completed successfully. The
  import form uses a multiline text field; paste the complete `crestron.yaml`
  contents with their original line breaks and indentation (open the file in a
  text editor and copy it; direct file upload is not supported). The automated
  flow check verifies form serialization, but does not independently test YAML
  parsing or imported-rule correctness. Live synchronization of the imported
  rules with a Crestron processor has not yet been reported.

## Before a release

Record the Home Assistant version, processor/model/firmware, and results.
Run software checks and hardware checks separately, and report which were
actually completed rather than marking an entire category as tested.

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
