# Crestron XSIG for Home Assistant

A custom Home Assistant integration that connects to a Crestron control
system over XSIG. Home Assistant listens as a TCP server; the Crestron
processor connects as a client. The integration supports digital,
analog and serial joins, entity configuration from the Home Assistant
UI, and bridges between existing Home Assistant entities and Crestron.

## Installation and setup

<!-- ha-marketplace:exclude-start -->
### Home Assistant 2026.11 and newer: Marketplace

[![Open Crestron XSIG in the Home Assistant Marketplace](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=morettigiorgio&repository=ha-crestron-xsig&category=integration)

Use the button above to open this repository in **Settings → Marketplace**.
If it is not yet in the public catalog, Home Assistant will offer to add it as
an integration repository. Install it there, then continue with **Add
Integration** below.

### Older Home Assistant versions

Before Home Assistant 2026.11, install the repository through HACS (the
predecessor to the built-in Marketplace) as a custom integration repository,
or install it manually into `<config>/custom_components/crestron_xsig/`.
For a manual install, clone or copy the repository-root files into that exact
directory; `manifest.json` must be directly inside
`custom_components/crestron_xsig/`. Restart Home Assistant after a manual
install.
<!-- ha-marketplace:exclude-end -->

### Set up the integration

1. Open **Settings → Devices & Services → Add Integration**, search for
   **Crestron XSIG**, and choose the TCP port Home Assistant will listen
   on.
2. Configure the Crestron TCP/IP client to connect to Home Assistant's
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

- **Overview of configured joins:** inspect a sorted inventory of configured entities, joins, exposes and actions. For a downloadable JSON snapshot, use **Download diagnostics** in the integration entry menu; review the file before sharing because it contains configured templates and scripts.
- **Expose (Home Assistant → Crestron):** send an existing entity's
  state or a template result to a typed XSIG join (`dN`, `aN` or `sN`).
- **Action (Crestron → Home Assistant):** run a Home Assistant action
  sequence when a configured join is received; the action can use
  `{{ value }}`.
- **Import legacy YAML:** imports `to_joins` and `from_joins` from an older
  `crestron.yaml` as exposes and actions. The import flow has been tested
  successfully. Paste the complete file contents into the multiline field,
  preserving line breaks and indentation (open the file in a text editor and
  copy it); direct file upload is not supported. Crestron synchronization
  should still be verified separately on your system.

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
It continues the work of Nick Pope and Georges Khalil, whose contributions are
gratefully acknowledged. See [docs/TRANSPARENCY.md](docs/TRANSPARENCY.md) for
upstream attribution and project history.

This repository is maintained by Giorgio Moretti and has been developed with
substantial assistance from an AI coding assistant. Giorgio reviews and is
responsible for the changes published here.

## Support
If you like my work and want to support me, you can buy me a coffee!

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/K3K21T8I02)
