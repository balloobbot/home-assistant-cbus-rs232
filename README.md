# C-Bus RS-232 for Home Assistant

Control Clipsal C-Bus lighting through a 5500PC serial interface and an ESPHome RS-232 serial proxy. This custom integration talks directly to the PCI. It needs no C-Gate server, MQTT broker, or installer project file.

Requires Home Assistant 2026.11 or later and a PCI with firmware 4 or later. The code has automated protocol and Home Assistant tests. **It has not been verified on a physical 5500PC or serial proxy.**

## Install

1. In HACS, add `https://github.com/balloobbot/cbus-rs232-hass` as a custom repository with category **Integration**.
2. Download **C-Bus RS-232** and restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration → C-Bus RS-232**.
4. Select the serial proxy port connected to the PCI.
5. Enter the lighting application in decimal. The default is **56** (`0x38`). Valid lighting applications are 48 through 95.

For manual installation, copy `custom_components/cbus_rs232` into your Home Assistant `config/custom_components` directory, then restart Home Assistant.

## Connect the hardware

```text
Home Assistant → ESPHome serial proxy → RS-232 → 5500PC → C-Bus
```

Use an RS-232 transceiver and the cable specified for the PCI. Do not connect TTL UART pins directly to its RS-232 connector. The integration sets **9600 baud, 8 data bits, no parity, and one stop bit**. Only one client can own the PCI connection.

The port selector also accepts a local USB serial port or `socket://HOST:PORT` for a serial device server or CNI. For a raw TCP server, configure 9600 8N1 on the server. ESPHome proxy URLs come from Home Assistant's port selector. Add the proxy to Home Assistant through the ESPHome integration first.

## Discovery and control

The integration reads all eight level-status blocks at startup. It discovers groups that are off as well as groups that are on. It then processes wall-switch events and status reports as they arrive. A full status refresh runs every minute. Setup fails if the PCI acknowledges requests but does not return complete level reports.

Each group becomes a dimmable light. Group addresses are 0 through 254; address 255 is reserved. Rename entities in Home Assistant to identify their loads. English text labels received from DLT label messages supply default names. Installer project import is not implemented. DLT labels and installer project names are different data.

On, off, brightness, and transitions use confirmed commands. C-Bus offers 16 ramp rates from immediate to 17 minutes at full scale. The integration chooses the nearest rate for the requested transition. Intermediate brightness is estimated until a status report arrives. An on/off report alone cannot reveal brightness; an unknown brightness stays unknown.

Discovery addresses and labels survive restarts. Saved state is not treated as live state. Missing groups and groups reporting an error become unavailable. Serial disconnection, PCI restart, command failure, or a failed status refresh triggers Home Assistant's reload and retry process. Commands with unknown delivery status are not retransmitted.

## Protocol scope

This release supports the **lighting application on the network directly attached to the PCI**, with one selected lighting application per connection. It does not implement all C-Bus applications. HVAC, security, metering, trigger control, unit commissioning, network bridges, and C-Gate project databases are outside this release.

| Protocol function | Support |
| --- | --- |
| PCI setup | Volatile application filter, SMART mode, strict checksums, local SAL, MMI monitoring, power-up notification |
| Command delivery | Serialized writes, rotating confirmation tags, all four confirmation results, timeout and cancellation cleanup |
| Lighting commands | On, off, all 16 ramp rates, terminate ramp, concatenated commands |
| Labels | Text, predefined icons, preferred language, dynamic icon command sequence; English flavour-0 text supplies entity names |
| Status | Standard binary MMI, short and local long-form extended MMI, all 256 level encodings, absent and error states |
| Framing | Fragmented/coalesced serial input, BASIC-mode echoes, inline confirmations, checksums, bounded input buffering |
| Recovery | Unplug, EOF, lost acknowledgements, PCI power-up, and incomplete status replies |

The protocol package is bundled under `custom_components/cbus_rs232/cbus`. Its command API also exposes terminate-ramp and label commands. These are not separate Home Assistant services. It accepts the documented label formats but enforces the PCI's 45-character transmit limit; an oversized command is rejected before transmission.

## Development

```sh
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

CI requires 100% line and branch coverage for the integration and bundled protocol code. Tests include published command/status examples, all brightness values and ramp rates, invalid frames, connection failures, concurrent events, Home Assistant flows and services, and a real `serialx` TCP connection to a local simulator. Coverage measures the implemented code. It does not establish hardware compatibility or C-Bus certification.

## Protocol references

- [Schneider Electric's Serial Interface Applications bundle](https://www.se.com/au/en/download/document/Serial_Interface_Applications/): Serial Interface User Guide 1.17, Lighting Application 1.5, and Quick Start Guide 2.0.
- [Direct download of the official bundle](https://download.schneider-electric.com/files?p_Doc_Ref=Serial_Interface_Applications).
- [micolous/cbus](https://github.com/micolous/cbus): a reference implementation with PCI, CNI, MQTT, and simulator examples. This integration uses its own implementation and does not bundle that library.
- [Home Assistant serial connections](https://www.home-assistant.io/connectivity/serial/).

The long-form status example in SIUG section 9.1 contains `F8` before 25 CAL bytes. Section 7.4's length rule requires `F9`; the checksum then changes from `C4` to `C3`. Tests retain the published frame as an invalid-length case and verify the corrected frame separately.
