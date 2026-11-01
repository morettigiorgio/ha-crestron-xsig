# Known issues and verification gaps

This list covers limitations that affect users or still need verification;
it is not a history of completed development tasks. See
[TESTING.md](TESTING.md) for the evidence currently available.

## Current limitations

- **Media-player mute mode:** Add/Edit lets the user choose a momentary toggle
  pulse or explicit ON/OFF state. The maintainer reports testing both modes on
  the Crestron system successfully, per the maintainer's latest test report.
- **Climate processor units:** Add/Edit lets the user choose Celsius,
  Fahrenheit, or follow Home Assistant's configured unit. The maintainer reports
  testing Celsius/Fahrenheit conversion successfully on the system.
  Home Assistant's configured-unit option remains available as a third choice.
- **Multiple clients per listener:** unsupported. Use one Crestron TCP client
  per listener. Multiple Home Assistant config entries/listeners are a
  separate use case.
- **TCP bind failures:** a failed listener bind is logged, but no dedicated
  Home Assistant repair notification is provided.

## Not yet verified

- **Legacy YAML import:** the `crestron.yaml` import flow is implemented but
  its real-world test is deferred by the maintainer until synchronization with
  the Crestron system is tested. It remains in development and should be
  treated as unverified, including its parser and Home Assistant UI flow.
- **Release regression:** the maintainer now reports PASS for the pending
  entity/configuration checks, both mute modes, temperature conversion, duplicate
  expose sources, service cleanup, UI validation messages, delayed actions,
  `reload_connection`, serial-boundary/soak checks and shared-device assignment.
  Reported environment: Home Assistant Container Core 2026.10.4 and Crestron
  DIN-AP3 firmware 1.8001.5761.28479; test date and per-case matrix were not
  supplied. Legacy YAML import remains deferred; HACS installation/update has
  not been smoke-tested. The integration's remaining functional test is the deferred
  legacy YAML import; general publication preparation is still required.

Report reproducible problems through the project's GitHub issue tracker.
Avoid including credentials or private configuration data.
