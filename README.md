[![Open in Home Assistant Marketplace](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=balloobbot&repository=home-assistant-cbus-rs232&category=integration)

# C-Bus RS-232 for Home Assistant

Control Clipsal C-Bus through a 5500PC serial interface and an ESPHome RS-232 serial proxy. This custom integration connects directly to the PCI. It needs no C-Gate server, MQTT broker, or installer project file.

Version 0.2 supports every application type in Schneider's published Serial Interface Applications bundle. It includes Home Assistant entities and named actions for application commands.

Requires Home Assistant 2026.11 or later and PCI firmware 4 or later. **Physical 5500PC and serial-proxy hardware validation is still pending.** Tests use documented wire messages, simulated devices, and the real `serialx` TCP transport.

## Supported applications

| Application | Address | Home Assistant support |
| --- | --- | --- |
| Lighting | `0x30`–`0x5F` | Lights, brightness, transitions, labels |
| Ventilation | `0x70` | Fans with speed control |
| Irrigation | `0x71` | Switches; level and ramp actions |
| Pools, spas, ponds, fountains | `0x72` | Switches; level and ramp actions |
| HVAC actuators | `0x73`, `0x74` | Switches; level and ramp actions |
| Temperature broadcast | `0x19` | Temperature sensors |
| Air conditioning | `0xAC` | Climate and humidifier entities per zone; temperature, humidity and fault sensors; schedule and plant commands |
| Media transport | `0xC0` | Media players, playback, track navigation, power, shuffle, repeat, metadata and enumeration commands |
| Trigger control | `0xCA` | Events, last-action sensors, trigger and label commands |
| Enable control | `0xCB` | Number entities for network variables |
| Error reporting | `0xCE` | Current fault and severity sensors; report events, acknowledgement and clear-latch commands |
| Security | `0xD0` | Alarm panels, zone contacts, alarm indicators, arming, keypad and status commands |
| Metering | `0xD1` | Electricity, gas, water, other-water and oil totals; measurement requests |
| Access control | `0xD5` | Door contacts, credential events, close and lock commands |
| Clock and timekeeping | `0xDF` | Date/time sensors; time, date and request commands |
| Telephony | `0xE0` | Line/number sensors; call events, isolation, rejection and diversion commands |
| Measurement | `0xE4` | Numeric and binary sensors with signed values, decimal scaling and all published unit codes |

Non-load applications also expose event entities. Each event includes its command name and fields. Multiple commands in a received packet produce separate events. Media text fragments are assembled before UTF-8 decoding.

## Install

1. Open the Marketplace link above to add this repository to Home Assistant.
2. Download **C-Bus RS-232** and restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration → C-Bus RS-232**.
4. Select the serial proxy port connected to the PCI.
5. Select the primary lighting application for the startup level scan. The default is **56** (`0x38`). All applications are monitored regardless of this setting.

For manual installation, copy `custom_components/cbus_rs232` into your Home Assistant `config/custom_components` directory, then restart Home Assistant.

Upgrades from 0.1 preserve the connection, light entity IDs, discovered load addresses, and labels. Additional application entities appear as their messages arrive.

## Connect the hardware

```text
Home Assistant → ESPHome serial proxy → RS-232 → 5500PC → C-Bus
```

Use an RS-232 transceiver and the cable specified for the PCI. Do not connect TTL UART pins directly to its RS-232 connector. The integration sets **9600 baud, 8 data bits, no parity, and one stop bit**. Only one client can own the PCI connection.

The port selector also accepts a local USB serial port or `socket://HOST:PORT` for a serial device server or CNI. For a raw TCP server, configure 9600 8N1 on the server. Add an ESPHome proxy to Home Assistant through the ESPHome integration first, then select its port.

## Discovery and state

Startup reads all eight level-status blocks for the primary lighting application and scans the other load-compatible applications. This discovers loads that are off as well as loads that are on. Subsequent minute-by-minute refreshes query the primary application and discovered loads. Other applications are discovered from their traffic. They do not use lighting MMI status requests.

Quiet devices may need a status request before their entities appear. Use `request_security`, `request_security_zones`, the five metering requests, `request_media` with its group, or `refresh_hvac` with its zone group. The [command reference](COMMANDS.md) lists these requests. Reload the integration to repeat the scan of all load applications.

A thermostat appears after a `set_hvac` message supplies its mode, plant type, setpoint, and auxiliary settings. A humidifier appears after `set_humidity`. Controls preserve these settings and target only the selected zone. Temperature and humidity reports also create sensors independently. Raw plant levels are not presented as temperature or humidity setpoints.

English DLT text labels supply default load names. Rename entities in Home Assistant for other names. Installer project names and DLT labels are separate data. Load addresses and labels survive restarts; saved states are not treated as live states. Other application entities wait for fresh messages after reconnecting.

Load commands use confirmations. C-Bus has 16 ramp rates from immediate to 17 minutes at full scale. The integration selects the closest rate for a requested light transition. It estimates intermediate brightness until a status report arrives. An on/off report alone cannot reveal a dimming level.

Application state-setting messages update their shared state after PCI confirmation. Security and access commands wait for device reports. A PCI confirmation establishes command delivery, not physical actuation. Serial disconnection, PCI restart, command failure, or an incomplete primary level scan triggers Home Assistant's reload and retry process. Commands with unknown delivery status are not retransmitted.

## Application actions

Use **Developer tools → Actions → C-Bus RS-232: Send application command**, or call `cbus_rs232.send_command` from an automation. Select the integration, enter the decimal application address, and supply the exact fields from the [command reference](COMMANDS.md).

```yaml
action: cbus_rs232.send_command
data:
  entry_id: YOUR_CONFIG_ENTRY_ID
  application: 202
  command: trigger
  fields:
    group: 7
    action: 3
```

This action requires administrator access because it can issue security and access commands. Normal entity controls use Home Assistant's entity permissions.

Security arming commands are application broadcasts. The protocol reports fully armed or partially armed status; it does not identify every vendor's partial mode. C-Bus has no direct disarm command. Use `keypad` with the exact key sequence documented by the panel manufacturer. The integration does not append Enter or infer a PIN format. Access control defines close and lock commands, but provides no unlock command or lock-state report. Door contact state therefore does not become a lock entity.

Media Transport Control has no volume command. Error refresh uses an installer-configured Trigger Control group/action. Clock updates are explicit; Home Assistant does not become a clock master automatically. Space successive HVAC setpoint changes by at least ten seconds and HVAC refresh requests by at least five seconds, as specified by the application chapter.

## Protocol boundaries

The integration implements the published application command layouts on the network directly attached to the PCI. Unit commissioning, installer project import, proprietary applications, and routed network-bridge control are outside its scope. Supporting all published application types does not imply support for those management protocols or every vendor extension.

PCI handling includes volatile wildcard application filters, SMART mode, strict checksums, local SAL, standard and extended MMI, power-up notification, confirmation tags, concatenated messages, fragmented serial input, BASIC echoes, and bounded input buffering. Reserved command opcodes are skipped by their encoded length. Invalid known messages are rejected.

Named commands cover the published application operations, including labels, schedules, enumeration, and fault acknowledgements. Byte-string fields use hexadecimal text. The PCI's 45-character transmit limit still applies. Oversized messages fail before transmission. The command reference explains the limit for text fragments.

## Development

```sh
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

CI requires 100% line and branch coverage for the integration and bundled protocol code. Tests include literal wire vectors for every named application command, published examples, all lighting levels and ramp rates, invalid frames, connection failures, concurrent events, Home Assistant controls, action permissions, and a real `serialx` TCP connection to a local simulator. Coverage measures code execution; hardware compatibility remains a separate check.

## References

- [Schneider Electric's Serial Interface Applications bundle](https://www.se.com/au/en/download/document/Serial_Interface_Applications/): Serial Interface User Guide 1.17, Quick Start Guide 2.0, and all published application chapters.
- [Direct download of the official bundle](https://download.schneider-electric.com/files?p_Doc_Ref=Serial_Interface_Applications).
- [micolous/cbus](https://github.com/micolous/cbus): reference PCI, CNI, MQTT, and simulator implementations. This integration uses its own implementation and does not bundle that library.
- [Home Assistant serial connections](https://www.home-assistant.io/connectivity/serial/).

The long-form status example in SIUG section 9.1 contains `F8` before 25 CAL bytes. Section 7.4 requires `F9`; the checksum then changes from `C4` to `C3`. Tests retain the published frame as an invalid-length case and verify the corrected frame separately.
