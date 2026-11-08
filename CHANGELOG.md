# Changelog

Notable changes to Crestron XSIG for Home Assistant are recorded here.
This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and semantic versioning. Versions below `1.0.0` may include breaking changes;
these will be called out explicitly.

## [0.5.0] — Unreleased

### Added

- Home Assistant Marketplace support, including the integration category,
  Marketplace installation link and updated distribution guidance. The existing
  `hacs.json` metadata and HACS catalog validator remain required by the
  Marketplace.
- Downloadable JSON diagnostics for a sorted inventory of configured
  entities, joins, exposes and actions.

### Fixed

- Render the legacy YAML import input as a multiline field so pasted YAML
  retains its line breaks and indentation. The import flow has been manually
  tested successfully in Home Assistant.

### Known limitations

- Marketplace installation/update has not yet been smoke-tested. The
  Marketplace is built into Home Assistant 2026.11 and newer, replacing the
  HACS custom integration. Use the README repository link until this project is
  in the public catalog; older Home Assistant releases can use HACS.

## [0.4.0] — First public release

> Initial public release. Add the publication date when the GitHub release is
> created.

### Added

- Config-entry setup with a Home Assistant TCP listener for the Crestron XSIG
  processor.
- UI configuration for switches, RGB/brightness lights, covers, sensors,
  binary sensors, climate, media players, text, number and button entities.
- Expose rules (Home Assistant → Crestron) and action rules (Crestron → Home
  Assistant), including typed digital, analog and serial joins.
- Per-entity device grouping, join services, connection reconfiguration and
  detailed wiring/configuration guides with Home Assistant and SIMPL examples.
- Selectable media-player mute behavior (toggle pulse or explicit state) and
  selectable climate processor temperature units (Home Assistant, Celsius or
  Fahrenheit).
- Selectable cover position range: 16-bit (0–65535, default) or direct
  percentage (0–100).

### Fixed and improved

- Correct sensor entity behavior and improved XSIG protocol handling,
  validation, scaling, reconnect synchronization and pulse lifecycle.
- Improved Add/Edit forms, validation feedback and preservation of entity
  identity when editing configuration.

### Known limitations

- Import of legacy `crestron.yaml` configuration is available in the options
  flow but remains unverified and is marked as in development.
- One Crestron TCP client is supported per configured listener.
