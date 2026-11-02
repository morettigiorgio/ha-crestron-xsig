# Crestron XSIG for Home Assistant

A custom Home Assistant integration that connects to a Crestron control
system over XSIG. Home Assistant listens as a TCP server; the Crestron
processor connects as a client. The integration supports digital,
analog and serial joins, entity configuration from the Home Assistant
UI, and bridges between existing Home Assistant entities and Crestron.

## Installation and setup

1. Install the repository contents directly into
   `<config>/custom_components/crestron_xsig/`. For example, clone this
   repository into that exact directory, or copy the repository-root files
   there from the downloaded archive. `manifest.json` must be directly inside
   `custom_components/crestron_xsig/`.
2. Restart Home Assistant.
3. Open **Settings → Devices & Services → Add Integration**, search for
   **Crestron XSIG**, and choose the TCP port Home Assistant will listen
   on.
4. Configure the Crestron TCP/IP client to connect to Home Assistant's
   IP address and that port. Ensure the network and firewall allow the
   connection. Connect the client to an XSIG (Intersystem Communication)
   symbol and wire the signals to the appropriate joins.

## Configuration and features

Use **Settings → Devices & Services → Crestron XSIG → Configure** to
add, edit or remove entities and rules. Supported entities include
switches, brightness/RGB lights, covers, sensors, binary sensors, climate,
media players, text (serial output), numbers (analog output) and buttons
(digital pulse output). Entities can be organized on the integration's
processor device, custom child devices, or other Home Assistant devices.

The Configure menu also supports:

- **Expose (Home Assistant → Crestron):** send an existing entity's
  state or a template result to a typed XSIG join (`dN`, `aN` or `sN`).
- **Action (Crestron → Home Assistant):** run a Home Assistant action
  sequence when a configured join is received; the action can use
  `{{ value }}`.
- **Import legacy YAML (in development):** maps `to_joins` and
  `from_joins` from an older `crestron.yaml` to exposes and actions. The
  import test has not yet been run; treat this path as unverified.

Changes made in the Configure menu reload the integration automatically.
The listener port can be changed through the integration's reconfigure
flow.

Each Add/Edit form links to a type-specific guide with every available option,
join direction, wiring advice, and Home Assistant/SIMPL examples. Start at
[docs/help/README.md](docs/help/README.md) for the complete guide index.

## Services

| Service | Description |
|---|---|
| `crestron_xsig.set_digital` | Write a digital join (1–4096); select `entry_id` when multiple processors are configured. |
| `crestron_xsig.set_analog` | Write an analog join (1–1024), value 0–65535; select `entry_id` when multiple processors are configured. |
| `crestron_xsig.set_serial` | Write a serial join (1–1024), up to 252 encoded bytes; select `entry_id` when multiple processors are configured. |
| `crestron_xsig.reload_connection` | Reload the selected config entry, or all entries if no entry is selected. |

Digital, analog and serial joins have separate number ranges. Refer to
the wiring guide for signal direction and entity-specific scaling.

## Behavior and limitations to know

- Media-player Add/Edit lets you select a momentary **toggle pulse** (the
  default, for Crestron programs that toggle mute) or **set requested state**
  (explicit muted/unmuted ON/OFF).
- Climate Add/Edit lets you set the processor temperature unit to **Home
  Assistant**, **Celsius**, or **Fahrenheit**. Choose the unit actually used by
  the Crestron program; Home Assistant values are converted accordingly.
- Multiple configured entries (each with its own listener) are supported;
  multiple Crestron clients on one listener are not. Use one client per
  listener.
- **Recommended after a Crestron/XSIG reboot:** have the Crestron program
  send `0xFC` followed by `0xFD` after reconnecting. `0xFC` clears HA's cached
  digital, analog and serial join values; `0xFD` then refreshes non-zero values
  and re-pushes configured HA exposes. This handles joins that reset to zero
  but are omitted from the processor's status dump, preventing stale HA states.
  Do not send `0xFC` for a normal network interruption if the processor did not
  reset: it intentionally clears HA's cached join state. Details are in the
  [wiring guide](docs/WIRING.md#reconnect-and-full-state-sync).
- Serial values are limited to 252 bytes and use Latin-1 encoding;
  characters outside that encoding are replaced.
- A failed TCP port bind is reported in the Home Assistant log; no
  dedicated repair notification is currently provided.

For the current testing status and known limitations, see
[docs/TESTING.md](docs/TESTING.md) and
[docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md).

## Feedback and contributions

Suggestions, bug reports and contributions are welcome. Please open an
[issue](https://github.com/morettigiorgio/ha-crestron-xsig/issues) for general
feedback and see [CONTRIBUTING.md](CONTRIBUTING.md) before submitting a pull
request. For security concerns, follow [SECURITY.md](SECURITY.md) and report
privately; do not post processor credentials or personal configuration data.

## License and attribution

This project is licensed under the Apache License 2.0; see [LICENSE](LICENSE).
It builds on work by Nick Pope and Georges Khalil. See
[docs/TRANSPARENCY.md](docs/TRANSPARENCY.md) for upstream attribution.

## Support
If you like my work and want to support me, you can buy me a coffee!

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/K3K21T8I02)
