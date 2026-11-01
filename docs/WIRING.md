# XSIG wiring guide — which side does each join belong to?

This guide explains which side of the Crestron XSIG symbol each join
uses. Direction hints are also shown in the integration's configuration
forms. The entity tables describe the implementation; they are not proof
that every entity has been tested with Crestron hardware. Hardware-specific
observations are identified below.

## The two sides

The XSIG (Intersystem Communication) symbol in your SIMPL program has:

| XSIG symbol side | Data direction | In this project |
|---|---|---|
| **IN** signals (into the symbol, from your logic) | processor → HA | state feedback / sensor values |
| **OUT** signals (out of the symbol, into your logic) | HA → processor | commands |

In the forms we label each field as:
* **(XSIG in → HA)** — wire your program's signal INTO the symbol;
  HA only reads it.
* **(XSIG out ← HA)** — take the signal OUT of the symbol into your
  logic; HA only writes it.
* **(XSIG in+out)** — the same join number exists on BOTH sides: wire
  a feedback signal into `in N` and read the command from `out N`.
  HA writes commands and reads state through the same number.

**Important numbering caveat** (from npope's original docs): the XSIG
numbers signals *sequentially across the whole signal list* — if you
attach e.g. 1 analog and then 1 digital to the same symbol, the digital
labeled "1" travels as join 2. Simplest rule: **use one XSIG symbol for
analog/serial and another one for digitals**, or account for the offset
in the entity configuration.

Tip (from georgesak's docs): set the XSIG symbol option to 2 ("always
propagate values") so repeated identical values still reach HA.

## Reconnect and full-state sync

A full-state sync uses `0xFD`. In the tested Crestron setup, the processor
retransmits joins with non-zero values but omits joins whose current value is
zero. Therefore a reboot can leave HA showing an old non-zero value: the
processor's variables have reset, but the omitted zero is never received.

**Recommended after an XSIG/processor reboot:** once the Crestron client has
reconnected, have the Crestron program send `0xFC` followed by `0xFD`. The
integration handles `0xFC` by clearing its cached digital, analog and serial
join state, so omitted values now read as false/zero/empty instead of stale.
The following `0xFD` full sync refreshes non-zero values and re-pushes configured
Home Assistant exposes. This sequence is the recommended way to ensure HA
entity states reflect the rebooted processor's actual state, including values
that reset to zero.

Do **not** send `0xFC` for an ordinary network interruption where the processor
has not reset its state: it deliberately clears HA's cached join state. In that
case, reconnect without `0xFC` and use the normal sync behavior.

**Hardware observation (one tested setup):** after a `0xFD` request, the
processor sent one `0xFB` marker per XSIG module connected to the serial link.
These markers carry no join values; the integration logs and ignores them.
`0xFC` clears cached join state without synthesizing per-join receive events
or triggering configured actions. Processor behavior may vary by program or
firmware.

## Per entity type

### Sensor — read only
| Field | Direction | Note |
|---|---|---|
| value_join (analog) | XSIG in → HA | value ÷ divisor |

### Binary sensor — read only
| Field | Direction | Note |
|---|---|---|
| is_on_join (digital) | XSIG in → HA | |

### Switch
| Field | Direction | Note |
|---|---|---|
| switch_join (digital) | XSIG in+out | `in N` = load state feedback, `out N` = on/off command |

Switch flags (both opt-in, default off; can be combined):
* **optimistic** — the state updates immediately after a command from
  HA, without waiting for the processor to echo the join back.
* **state sync** — the REAL state is sent to the join whenever it
  changes in HA for any reason (also after external changes), whenever
  it differs from the last value actually sent (echo-loop protection).
  Use only if the program reads the join as a LEVEL, not a pulse.

### Light (brightness)
| Field | Direction | Note |
|---|---|---|
| brightness_join (analog) | XSIG in+out | `in` = actual level feedback (0-65535), `out` = level command |

Brightness maps the full XSIG range 0..65535 to Home Assistant's 0..255
range; every nonzero raw value remains visibly on. `brightness_default`
(on-without-level) is expected to be 0..255; malformed stored values
fall back to 128.

Optional `red_join`, `green_join` and `blue_join` analog joins enable RGB
color. Configure all three or none; each uses the same XSIG 0..65535 to
Home Assistant 0..255 scaling as brightness. Each color join is both read
for feedback and written for commands. Every configured brightness/R/G/B
join must have a distinct analog join number to avoid competing values and
writes. Existing lights with no RGB joins remain brightness-only.

### Cover — all joins optional, freely combinable
| Field | Direction | Note |
|---|---|---|
| open_join / close_join / stop_join | XSIG out ← HA | momentary pulses |
| pos_join (analog) | XSIG in+out | `in` = position feedback (0=closed, 65535=open), `out` = position command |
| is_opening / is_closing | XSIG in → HA | moving feedback |
| is_closed | XSIG in → HA | fully-closed feedback |
| is_opened | XSIG in → HA | fully-open feedback (HA has no "is_opened" state: this confirms "open" and fills in when is_closed is missing) |

Command behavior: **open** pulses `open_join` (if configured) and
writes 65535 to `pos_join` **only** when the *position commands* option
is on — or when there is no pulse join to command with. Same for
**close** (0). **Set position** always writes `pos_join`.

### Media player
| Field | Direction | Note |
|---|---|---|
| mute_join / mute_mode | XSIG in+out | Add/Edit selects `toggle_pulse` (default: momentary toggle command) or `set_state` (write HA's requested ON/OFF state); select the mode matching the Crestron program |
| volume_up / volume_down | XSIG out ← HA | momentary pulses |
| volume_join (analog) | XSIG in+out | 0-65535 |
| source_number_join (analog) | XSIG in+out | 0 = off, 1..n = source |

### Climate (thermostat) — the confusing one, in detail
Only **name** and **current temperature** are required. Everything
else adapts to the thermostat you actually have.

| Field | Direction | Wire what |
|---|---|---|
| reg_temp_join (analog) | XSIG in -> HA | measured temperature (raw = degrees x temp_divisor, default 10) |
| heat_sp_join (analog) | XSIG in+out | heat setpoint (same scaling). Alone = single-setpoint stat |
| cool_sp_join (analog) | XSIG in+out | cool setpoint (same scaling). With heat_sp = heat/cool range |
| temp_divisor / humidity_divisor | (config only) | scaling: raw = physical value x divisor. Temperature defaults to 10 (degrees x10), humidity to 1 |
| temp_unit | config option | Add/Edit selects the processor unit: Home Assistant's configured unit, `C`, or `F`; climate readings and setpoint commands convert between units |
| min_temp / max_temp / temp_step | (config only) | setpoint limits and step shown in HA |
| mode_heat / mode_cool / mode_auto / mode_off | XSIG in+out | one digital per mode: `in` = current mode feedback (your program should make them mutually exclusive), `out` = mode command. The HA mode list adapts to the joins you configure |
| mode_fan_only / mode_dry | XSIG in+out | optional extra modes |
| fan_on / fan_auto | XSIG in+out | fan mode, same pattern as modes |
| h1 / h2 | XSIG in -> HA | **heating actually active** — wire the heating stage/valve command of your program here |
| c1 / c2 | XSIG in -> HA | **cooling actually active** — wire the cooling stage/valve command |
| fa | XSIG in -> HA | fan actually running |
| humidity_join (analog) | XSIG in -> HA | current humidity (raw = percent x humidity_divisor) |
| target_humidity_join (analog) | XSIG in+out | target humidity (same scaling) |
| presets_text | (config) | one digital join per preset, `Name:join` pairs (e.g. `Home:21,Away:22`) — HA sets one high at a time |

The `hvac_action` shown by HA (heating / cooling / fan / idle) is
derived only from h1/h2/c1/c2/fa. If your program drives a valve, wire
that signal to `in` h1 (or c1 for cooling); without stage feedback, HA
reports idle even while heating or cooling. `fan_on` / `fan_auto` report
the fan MODE, not whether it is running. If neither mode join is active
but FA is high, HA falls back to fan mode `on` and `hvac_action: fan`.
For the correct mode display, feed the mode joins back on the XSIG in side.


## One-way control from scripts and automations

To drive a raw XSIG output from an HA script/automation (e.g. send a
notification string to the processor), no entity is needed — use the
services:

```yaml
action: crestron_xsig.set_serial
data:
  join: 3        # serial join number (XSIG out)
  value: "Hello from Home Assistant"
```

Also available: `crestron_xsig.set_digital`, `crestron_xsig.set_analog`
(join limits: digital 1-4096, analog/serial 1-1024; serial payloads
are limited to 252 bytes and encoded as Latin-1; characters not
representable in Latin-1 are replaced).

### Text (serial output)
| Field | Direction | Note |
|---|---|---|
| serial_join | XSIG out <- HA | string output, Latin-1 encoded (max 252 bytes; unsupported characters are replaced) |

### Number (analog output)
| Field | Direction | Note |
|---|---|---|
| value_join (analog) | XSIG out <- HA | slider/box with configurable min/max/step (raw 0-65535 by default) |

### Button (digital pulse output)
| Field | Direction | Note |
|---|---|---|
| button_join (digital) | XSIG out <- HA | pressing the button = momentary pulse, like a script action |
