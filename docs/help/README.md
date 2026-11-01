# Configure Crestron XSIG from Home Assistant

These guides explain every **Add** and **Edit** form in the integration options. They are linked from the question-mark help on the corresponding Home Assistant form. The examples use Home Assistant and Crestron SIMPL screenshots; join assignments are illustrative—use the join numbers in your own program.

## Choose a guide

- [Switch](switch.md)
- [Light](light.md)
- [Cover](cover.md)
- [Sensor](sensor.md)
- [Binary sensor](binary-sensor.md)
- [Climate / thermostat](climate.md)
- [Media player](media-player.md)
- [Text](text.md)
- [Number](number.md)
- [Button](button.md)
- [Expose: Home Assistant → Crestron](expose.md)
- [Action: Crestron → Home Assistant](action.md)

## Before assigning joins

The Crestron processor connects to the TCP listener configured by the integration. Add an XSIG symbol in SIMPL and connect its **in** and/or **out** signals to the logic that owns each join. In these guides, directions are named from Home Assistant's point of view:

- **XSIG in → HA**: Crestron sends a value to Home Assistant; use for feedback/read-only values.
- **XSIG out ← HA**: Home Assistant sends a value to Crestron; use for commands and text/number output.
- **XSIG in+out**: both sides can send values; use for a command with feedback or a shared state.

Joins are one-based. Entity forms ask for the join number only; **Expose** and **Action** forms ask for a typed join such as `d451`, `a101`, or `s7`.

| XSIG join | Meaning | Valid join numbers | Value |
|---|---|---:|---|
| Digital (`d`) | Boolean / pulse | 1–4096 | Low/high (0/1) |
| Analog (`a`) | Numeric | 1–1024 | 0–65535 |
| Serial (`s`) | Text | 1–1024 | Up to 252 encoded bytes per value |

Digital, analog and serial join numbers are separate namespaces. For the protocol and connection wiring, see the [wiring guide](../WIRING.md).

## Shared form options

Entity forms also include options that are not join signals:

- **Name**: friendly name in Home Assistant.
- **Device**: place the entity on this integration's Crestron processor device, a device created under **Manage devices**, or another existing Home Assistant device. This only changes Home Assistant's device grouping; it does not affect XSIG wiring.
- **Entity category**: optional Home Assistant classification (`None`, `Configuration`, or `Diagnostic`).
- **Optimistic** (where offered): immediately reflect a command locally instead of waiting for Crestron to echo the new state. Use it when the program does not send feedback. Without it, state is driven by the received XSIG value.

On **Edit**, the existing entity keeps its identity and history. Empty optional fields can be cleared. A join should not be assigned to multiple unrelated entities unless the shared behavior is intentional.

## Screenshots

Screenshots are examples rather than a required recipe. Each topic page shows the available form fields and its matching UI/SIMPL examples. The pictures use the then-current Home Assistant layout; labels or page layout can change between HA releases.
