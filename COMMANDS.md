# Application command reference

Call `cbus_rs232.send_command` with `entry_id`, a decimal `application`, a `command` name, and a `fields` mapping. Supply every listed field. Use integers for numeric fields and hexadecimal strings for byte fields. An empty field list means `{}`.

`legacy_error` is receive-only. Send `error_report` for new reports. The `trigger_min` and `trigger_max` names accept legacy incoming packets but transmit canonical `trigger` commands with action 0 or 255. `indicator_kill` deactivates scene indicators for its trigger group.

The tables describe protocol values. They do not invent device capabilities. A command can be a control request or a state broadcast; its meaning follows the relevant Schneider application chapter.

## Field conventions

- `u8`, `u16`, `u32`: unsigned integers of the stated bit width. `i8` and `i16`: signed integers. Multi-byte values use network byte order.
- `group`: application group address. Lighting-compatible groups use 0–254. Enable group 255 broadcasts to all variables. Trigger and media group 255 is unused and ignored on receive. Temperature group 255 is an ordinary group. Other applications use their chapter's group conventions.
- `zones`: bit mask for HVAC zones 0–6. For example, 1 selects zone 0; 4 selects zone 2; 5 selects both. Select at least one zone.
- HVAC temperature `value` and `level`: degrees Celsius multiplied by 256 when the mode's raw-level bit is clear. Humidity `value` and `level`: relative humidity multiplied by 65535/100 when the raw-level bit is clear. Plant command levels use their signed or unsigned one-byte demand scale.
- HVAC `mode`: low three bits select off/heat/cool/auto/fan (0–4), or off/humidify/dehumidify/auto (0–3). Bit 3 selects raw level, bit 4 setback, bit 5 guard, and bit 6 auxiliary use. Bit 7 is reserved. `type` selects the plant type defined by Chapter 25. `auxiliary` uses bits 0–5 for fan speed and bit 6 for continuous operation.
- Schedules retain the protocol's entry, format, start-time and level fields. `start` is minutes from Sunday 00:00. Formats 1–7 are defined by Chapter 25. Start times are 0–10079; 65535 marks a null entry.
- Measurement `value * 10**multiplier` gives the value in the selected unit. Unit 4 is Boolean. Unit 254 is unitless; 255 is custom.
- Temperature Broadcast `value / 4` gives degrees Celsius. Meter totals use kWh, MJ, m³, m³, and L for electricity, gas, water, other-water, and oil respectively.
- Error `category_flags`: `(category << 6) | (recent << 5) | (acknowledged << 4) | (most_severe << 3) | severity`. Severity is 0 all OK, 1 OK, 2 minor, 3 general, or 4 extreme. `data1` and `data2` follow the category-specific definitions in Chapter 34. All OK clears the device's current faults in that category. Latched reports do not replace current fault state.
- Security `arm.mode`: 1 away, 2 night, 3 day/home, 4 vacation, 255 highest. Reported `armed.mode` uses a different scale: 0 disarmed, 1 fully armed, 2 partially armed, 3–127 vendor-defined. Keypad `key` is one byte: ASCII for ordinary keys, 13 for Enter, and the panel's defined special-key codes.
- Security packed zone fields contain four two-bit statuses per byte, highest pair first: 0 sealed, 1 unsealed, 2 open, 3 short. Status reports cover zones 1–32 and 33–80 separately. Fixed zone names require exactly eleven ASCII bytes, including space padding.
- Access `direction`: 0 unused, 1 in, 2 out. `credential` is 0–10 bytes. Contact reports do not imply lock state.
- Media `pause.operation`: 0 pause, nonzero resume. Step operations use 0 previous and nonzero next. Shuffle uses 0 off and 255 on. Repeat uses 0 off, 1–254 one, 255 all. Fast-forward/rewind use 0 normal and 2, 4, 6, 8, 10, 12 for 2× through 64×.
- Media text `header`: bits 0–1 are fragment number, bits 2–3 are total fragments minus one, and bits 4–6 select current/next/previous/enumeration metadata. Current names use zero in bits 4–6. Use at most four fragments, in order, with at most 40 UTF-8 bytes across the complete name. Text is UTF-8 encoded to hexadecimal. Only complete current names update player metadata. Chapter 21 recommends at most eleven text bytes per fragment for routing through six bridges.
- Clock `weekday`: Monday 0 through Sunday 6. `daylight_saving`: 0 standard, 1 one-hour advance, 255 unknown. Telephony `ringing.count` must be 1. Numbers are 0–16 ASCII bytes.

The PCI accepts at most 45 characters between `\` and carriage return. This includes the checksum and confirmation tag. Application commands therefore have at most 18 bytes, including their opcode. For example, each transmitted media text fragment can contain at most 15 text bytes. The receive decoder accepts the chapter's longer text fields. It does not truncate an outgoing command to make it fit.

Trigger labels use `options: 1` for text. Bit 0 must be set. Icon and preferred-language modes use bits 1–2, as in Chapter 7. A trigger label must be the last command in its packet. `arm_ready.zone` is zero when all zones sealed correctly during arming; otherwise it identifies an unsealed zone.

## Load-compatible applications

Use addresses 48–95 for lighting, 112 for ventilation, 113 for irrigation, 114 for pools, and 115–116 for HVAC actuators.

| Command | Fields |
| --- | --- |
| `set_level` | `group` u8 (0–254), `level` u8, `ramp` u8 (0–15) |
| `terminate_ramp` | `group` u8 (0–254) |
| `label` | `group` u8 (0–254), `options` u8, `language` u8, `data` hex |

Ramp indices map to full-scale seconds: 0, 4, 8, 12, 20, 30, 40, 60, 90, 120, 180, 300, 420, 600, 900, 1020. The duration for a smaller level change scales with the distance between levels. Label options follow Chapter 2; `options: 0`, `language: 1` selects English text. Label text, predefined icons, preferred language, and dynamic icon sequences use the same validated wire command.

## Temperature — 25 (`0x19`)

| Command | Fields |
| --- | --- |
| `temperature` | `group` u8, `value` u8 |

## Enable — 203 (`0xCB`)

| Command | Fields |
| --- | --- |
| `set_enable` | `group` u8, `value` u8 |

## Trigger — 202 (`0xCA`)

| Command | Fields |
| --- | --- |
| `trigger` | `group` u8, `action` u8 |
| `trigger_min` | `group` u8 |
| `trigger_max` | `group` u8 |
| `indicator_kill` | `group` u8 |
| `trigger_label` | `group` u8, `options` u8, `action` u8, `language` u8, `text` hex, 0–16 bytes |

## Metering — 209 (`0xD1`)

| Command | Fields |
| --- | --- |
| `request_electricity` | None |
| `electricity` | `value` u32 |
| `request_gas` | None |
| `gas` | `value` u32 |
| `request_water` | None |
| `water` | `value` u32 |
| `request_other_water` | None |
| `other_water` | `value` u32 |
| `request_oil` | None |
| `oil` | `value` u32 |

## Measurement — 228 (`0xE4`)

| Command | Fields |
| --- | --- |
| `measurement` | `device` u8, `channel` u8, `units` u8, `multiplier` i8, `value` i16 |

## Clock — 223 (`0xDF`)

| Command | Fields |
| --- | --- |
| `time` | `hour` u8, `minute` u8, `second` u8, `daylight_saving` u8 |
| `date` | `year` u16, `month` u8, `day` u8, `weekday` u8 |
| `request_clock` | None |

## Access control — 213 (`0xD5`)

| Command | Fields |
| --- | --- |
| `valid_access` | `network` u8, `point` u8, `direction` u8, `credential` hex, 0–10 bytes |
| `invalid_access` | `network` u8, `point` u8, `direction` u8, `credential` hex, 0–10 bytes |
| `close_access` | `network` u8, `point` u8 |
| `lock_access` | `network` u8, `point` u8 |
| `left_open` | `network` u8, `point` u8 |
| `forced_open` | `network` u8, `point` u8 |
| `closed` | `network` u8, `point` u8 |
| `request_exit` | `network` u8, `point` u8 |

## Error reporting — 206 (`0xCE`)

| Command | Fields |
| --- | --- |
| `legacy_error` | `category_flags` u16, `device` u8, `data1` u8, `data2` u8 |
| `error_report` | `category_flags` u16, `device` u8, `data1` u8, `data2` u8 |
| `acknowledge_error` | `category_flags` u16, `device` u8, `data1` u8, `data2` u8 |
| `clear_error` | `category_flags` u16, `device` u8, `data1` u8, `data2` u8 |

## Security — 208 (`0xD0`)

| Command | Fields |
| --- | --- |
| `armed` | `mode` u8 |
| `disarmed` | None |
| `exit_delay` | None |
| `entry_delay` | None |
| `alarm_on` | None |
| `alarm_off` | None |
| `tamper_on` | None |
| `tamper_off` | None |
| `panic_on` | None |
| `panic_off` | None |
| `battery_low_on` | None |
| `battery_low_off` | None |
| `mains_failure_on` | None |
| `mains_failure_off` | None |
| `line_cut_on` | None |
| `line_cut_off` | None |
| `arm_failed_on` | None |
| `arm_failed_off` | None |
| `fire_on` | None |
| `fire_off` | None |
| `gas_alarm_on` | None |
| `gas_alarm_off` | None |
| `other_alarm_on` | None |
| `other_alarm_off` | None |
| `zone_unsealed` | `zone` u8 |
| `zone_sealed` | `zone` u8 |
| `zone_open` | `zone` u8 |
| `zone_short` | `zone` u8 |
| `zone_isolated` | `zone` u8 |
| `arm_ready` | `zone` u8 |
| `battery_charging` | `state` u8 |
| `zone_name` | `zone` u8, `text` hex, exactly 11 bytes |
| `security_status` | `mode` u8, `tamper` u8, `panic` u8, `zones` hex, exactly 8 bytes |
| `security_zones` | `zones` hex, exactly 12 bytes |
| `password_status` | `status` u8 |
| `request_security` | None |
| `request_security_zones` | None |
| `arm` | `mode` u8 |
| `raise_tamper` | None |
| `drop_tamper` | None |
| `raise_alarm` | None |
| `keypad` | `key` u8 |
| `display_message` | `text` hex, 0–18 bytes |
| `request_zone_name` | `zone` u8 |

## Telephony — 224 (`0xE0`)

| Command | Fields |
| --- | --- |
| `on_hook` | None |
| `off_hook` | `reason` u8, `number` hex, 0–16 bytes |
| `dial_out_failure` | `reason` u8 |
| `dial_in_failure` | `reason` u8 |
| `ringing` | `count` u8, `number` hex, 0–16 bytes |
| `last_number` | `type` u8, `number` hex, 0–16 bytes |
| `internet_request` | None |
| `isolate_outlet` | `state` u8 |
| `request_last_number` | `type` u8 |
| `reject_call` | None |
| `divert` | `number` hex, 0–16 bytes |
| `clear_diversion` | None |

## Media — 192 (`0xC0`)

| Command | Fields |
| --- | --- |
| `stop` | `group` u8 |
| `play` | `group` u8 |
| `pause` | `group` u8, `operation` u8 |
| `category` | `group` u8, `category` u8 |
| `selection` | `group` u8, `selection` u16 |
| `track` | `group` u8, `track` u32 |
| `shuffle` | `group` u8, `state` u8 |
| `repeat` | `group` u8, `type` u8 |
| `step_category` | `group` u8, `operation` u8 |
| `step_selection` | `group` u8, `operation` u8 |
| `step_track` | `group` u8, `operation` u8 |
| `fast_forward` | `group` u8, `operation` u8 |
| `rewind` | `group` u8, `operation` u8 |
| `power` | `group` u8, `state` u8 |
| `total_tracks` | `group` u8, `total` u32 |
| `request_media` | `group` u8 |
| `enumerate` | `group` u8, `type` u8, `start` u8 |
| `enumeration_size` | `group` u8, `type` u8, `start` u8, `size` u8 |
| `track_name` | `group` u8, `header` u8, `text` hex, 0–29 bytes |
| `selection_name` | `group` u8, `header` u8, `text` hex, 0–29 bytes |
| `category_name` | `group` u8, `header` u8, `text` hex, 0–29 bytes |

## Air conditioning — 172 (`0xAC`)

| Command | Fields |
| --- | --- |
| `hvac_schedule` | `group` u8, `zones` u8, `entry` u8, `format` u8, `mode` u8, `start` u16, `level` i16 |
| `humidity_schedule` | `group` u8, `zones` u8, `entry` u8, `format` u8, `mode` u8, `start` u16, `level` u16 |
| `refresh_hvac` | `group` u8 |
| `hvac_status` | `group` u8, `zones` u8, `type` u8, `status` u8, `error` u8 |
| `humidity_status` | `group` u8, `zones` u8, `type` u8, `status` u8, `error` u8 |
| `zone_temperature` | `group` u8, `zones` u8, `value` i16, `status` u8 |
| `zone_humidity` | `group` u8, `zones` u8, `value` u16, `status` u8 |
| `hvac_off` | `group` u8 |
| `hvac_on` | `group` u8 |
| `set_hvac` | `group` u8, `zones` u8, `mode` u8, `type` u8, `level` i16, `auxiliary` u8 |
| `hvac_plant` | `group` u8, `zones` u8, `mode` u8, `type` u8, `level` i8, `auxiliary` u8 |
| `set_humidity` | `group` u8, `zones` u8, `mode` u8, `type` u8, `level` u16, `auxiliary` u8 |
| `humidity_plant` | `group` u8, `zones` u8, `mode` u8, `type` u8, `level` u8, `auxiliary` u8 |
| `hvac_upper_guard` | `group` u8, `zones` u8, `level` i16, `mode` u8 |
| `hvac_lower_guard` | `group` u8, `zones` u8, `level` i16, `mode` u8 |
| `hvac_setback` | `group` u8, `zones` u8, `level` i16, `mode` u8 |
| `humidity_upper_guard` | `group` u8, `zones` u8, `level` u16, `mode` u8 |
| `humidity_lower_guard` | `group` u8, `zones` u8, `level` u16, `mode` u8 |
| `humidity_setback` | `group` u8, `zones` u8, `level` u16, `mode` u8 |

## Request examples

Request electricity totals from local metering devices:

```yaml
action: cbus_rs232.send_command
data:
  entry_id: YOUR_CONFIG_ENTRY_ID
  application: 209
  command: request_electricity
```

Request air-conditioning settings and status for zone group 7:

```yaml
action: cbus_rs232.send_command
data:
  entry_id: YOUR_CONFIG_ENTRY_ID
  application: 172
  command: refresh_hvac
  fields:
    group: 7
```

Do not issue HVAC refresh requests more often than once per five seconds. Leave at least ten seconds between HVAC setpoint changes. Error-report refresh uses `trigger` on application 202 with the group and action configured by the installer.

The [official application bundle](https://www.se.com/au/en/download/document/Serial_Interface_Applications/) defines device-specific modes, schedule formats, icon formats, and error-category data. Use those definitions when constructing advanced commands.
