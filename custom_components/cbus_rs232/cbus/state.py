"""State derived from received application messages."""

from collections import deque
from dataclasses import dataclass, field
from datetime import date, time

from .applications import ApplicationCommand, ApplicationEvent

MEASUREMENT_UNITS = (
    "°C",
    "A",
    "°",
    "C",
    None,
    "F",
    "H",
    "Hz",
    "J",
    "kat",
    "kg/m³",
    "kg",
    "L",
    "L/h",
    "L/min",
    "L/s",
    "lx",
    "m",
    "m/min",
    "m/s",
    "m/s²",
    "mol",
    "N·m",
    "N",
    "Ω",
    "Pa",
    "%",
    "dB",
    "ppm",
    "rpm",
    "s",
    "min",
    "h",
    "Sv",
    "sr",
    "T",
    "V",
    "Wh",
    "W",
    "Wb",
)
METER_UNITS = {
    "electricity": "kWh",
    "gas": "MJ",
    "water": "m³",
    "other_water": "m³",
    "oil": "L",
}


@dataclass
class Reading:
    value: object
    unit: str | None = None
    binary: bool = False
    total: bool = False


@dataclass
class ApplicationDevice:
    application: int
    key: str
    address: dict[str, int]
    values: dict = field(default_factory=dict)
    readings: dict[str, Reading] = field(default_factory=dict)
    event: ApplicationCommand | None = None
    sequence: int = 0
    events: deque = field(default_factory=lambda: deque(maxlen=64))
    text_parts: dict[str, tuple[int, int, bytes]] = field(default_factory=dict)


class ApplicationState:
    def __init__(self) -> None:
        self.devices: dict[tuple[int, str], ApplicationDevice] = {}

    def apply(self, event: ApplicationEvent) -> None:
        for command in event.commands:
            for address in self._addresses(event, command):
                key = "_".join(f"{name}_{value}" for name, value in address.items())
                device = self.devices.setdefault(
                    (event.application, key),
                    ApplicationDevice(event.application, key, address),
                )
                device.event = command
                device.sequence += 1
                device.events.append((device.sequence, command))
                self._update(device, command)

    def _addresses(
        self, event: ApplicationEvent, command: ApplicationCommand
    ) -> list[dict]:
        values = command.values
        if values.get("group") == 255:
            if event.application == 0xCB:
                return [
                    device.address
                    for device in self.devices.values()
                    if device.application == 0xCB
                ]
            if event.application in (0xCA, 0xC0):
                return []
        if event.application == 0xAC:
            if "zones" not in values:
                return [
                    device.address
                    for device in self.devices.values()
                    if device.application == 0xAC
                    and device.address["group"] == values["group"]
                ] or [{"group": values["group"], "zone": 0}]
            zones = values["zones"]
            return [
                {"group": values["group"], "zone": zone}
                for zone in range(7)
                if zones & (1 << zone)
            ]
        if event.application == 0xE4:
            return [{"device": values["device"], "channel": values["channel"]}]
        if event.application == 0xD5:
            return [{"network": values["network"], "point": values["point"]}]
        if event.application == 0xCE:
            return [
                {
                    "device": values["device"],
                    "category": values["category_flags"] >> 6,
                    "event": values["data1"],
                }
            ]
        if "group" in values:
            return [{"group": values["group"]}]
        return [{"source": event.source}]

    def _update(self, device: ApplicationDevice, command: ApplicationCommand) -> None:
        app, name, v = device.application, command.name, command.values
        state, readings = device.values, device.readings
        if app in (0x19, 0xCB):
            state["value"] = v["value"]
            if app == 0x19:
                readings["temperature"] = Reading(v["value"] / 4, "°C")
        elif app == 0xE4:
            units = v["units"]
            value = v["value"] * 10.0 ** v["multiplier"]
            unit = MEASUREMENT_UNITS[units] if units < len(MEASUREMENT_UNITS) else None
            readings["measurement"] = Reading(
                bool(value) if units == 4 else value, unit, units == 4
            )
            state.update(v)
        elif app == 0xD1 and name in METER_UNITS:
            readings[name] = Reading(v["value"], METER_UNITS[name], total=True)
        elif app == 0xCA:
            if name in ("trigger", "trigger_min", "trigger_max"):
                state["action"] = v.get("action", 255 if name == "trigger_max" else 0)
                readings["action"] = Reading(state["action"])
        elif app == 0xDF:
            if name == "time":
                readings["time"] = Reading(
                    time(v["hour"], v["minute"], v["second"]).isoformat()
                )
            elif name == "date":
                readings["date"] = Reading(
                    date(v["year"], v["month"], v["day"]).isoformat()
                )
        elif app == 0xD5:
            if name in ("left_open", "forced_open", "closed"):
                readings["open"] = Reading(name != "closed", binary=True)
        elif app == 0xE0:
            if name in ("on_hook", "off_hook", "ringing"):
                readings["line"] = Reading(name)
            if "number" in v:
                readings["number"] = Reading(
                    bytes.fromhex(v["number"]).decode("ascii", errors="replace")
                )
        elif app == 0xCE:
            if name in ("error_report", "legacy_error"):
                flags = v["category_flags"]
                # Latched reports do not replace the current fault condition.
                if name == "legacy_error" or flags & 0x20:
                    severity = flags & 7
                    readings["fault"] = Reading(severity > 1, binary=True)
                    readings["severity"] = Reading(severity)
                    state.update(v)
                    if severity == 0:
                        for other in self.devices.values():
                            if (
                                other.application == 0xCE
                                and other.address["device"] == device.address["device"]
                                and other.address["category"]
                                == device.address["category"]
                            ):
                                other.readings["fault"] = Reading(False, binary=True)
                                other.readings["severity"] = Reading(0)
        elif app == 0xD0:
            self._security(device, command)
        elif app == 0xC0:
            self._media(device, command)
        elif app == 0xAC:
            self._hvac(device, command)

    def _security(self, device: ApplicationDevice, command: ApplicationCommand) -> None:
        name, v = command.name, command.values
        state, readings = device.values, device.readings
        if name in ("armed", "security_status"):
            state["mode"] = v["mode"]
            state["delay"] = None
        elif name == "disarmed":
            state.update(mode=0, delay=None)
        elif name in ("entry_delay", "exit_delay"):
            state["delay"] = name
        elif name.endswith(("_on", "_off")):
            key = name.rsplit("_", 1)[0]
            value = name.endswith("_on")
            readings[key] = Reading(value, binary=True)
            state[key] = value
        elif name in ("zone_unsealed", "zone_sealed", "zone_open", "zone_short"):
            readings[f"zone_{v['zone']}"] = Reading(name != "zone_sealed", binary=True)
        elif name == "arm_ready":
            readings["arm_ready"] = Reading(v["zone"] == 0, binary=True)
        elif name == "battery_charging":
            readings["battery_charging"] = Reading(bool(v["state"]), binary=True)
        elif name == "zone_name":
            state[f"zone_{v['zone']}_name"] = (
                bytes.fromhex(v["text"]).decode("ascii", errors="replace").rstrip()
            )
        if name in ("security_status", "security_zones"):
            start = 1 if name == "security_status" else 33
            for index, packed in enumerate(bytes.fromhex(v["zones"])):
                for offset in range(4):
                    readings[f"zone_{start + index * 4 + offset}"] = Reading(
                        bool(packed >> (6 - offset * 2) & 3), binary=True
                    )
            if name == "security_status":
                readings["tamper"] = Reading(bool(v["tamper"]), binary=True)
                readings["panic"] = Reading(bool(v["panic"]), binary=True)

    def _media(self, device: ApplicationDevice, command: ApplicationCommand) -> None:
        name, v, state = command.name, command.values, device.values
        if name in ("play", "stop", "pause"):
            state["playback"] = {
                "play": "playing",
                "stop": "idle",
                "pause": "paused" if not v.get("operation") else "playing",
            }[name]
        elif name in ("power", "shuffle"):
            state[name] = bool(v["state"])
        elif name == "repeat":
            state["repeat"] = (
                "off" if v["type"] == 0 else "all" if v["type"] == 255 else "one"
            )
        elif name in ("track", "category", "selection", "total_tracks"):
            state.update(v)
        elif name.endswith("_name"):
            header = v["header"]
            if header & 0xF0:
                return
            sequence, total = header & 3, (header >> 2) & 3
            previous_sequence, previous_total, data = device.text_parts.get(
                name, (-1, total, b"")
            )
            if sequence == 0:
                data = b""
            elif sequence != previous_sequence + 1 or total != previous_total:
                device.text_parts.pop(name, None)
                return
            data += bytes.fromhex(v["text"])
            if len(data) > 40:
                device.text_parts.pop(name, None)
                return
            device.text_parts[name] = sequence, total, data
            if sequence == total:
                state[name] = data.decode("utf-8", errors="replace")
                device.text_parts.pop(name)

    def _hvac(self, device: ApplicationDevice, command: ApplicationCommand) -> None:
        name, v, state = command.name, command.values, device.values
        if name in ("set_hvac", "set_humidity"):
            prefix = "hvac" if name == "set_hvac" else "humidity"
            state[prefix] = dict(v)
        elif name in ("zone_temperature", "zone_humidity"):
            humidity = name == "zone_humidity"
            key = "humidity" if humidity else "temperature"
            value = v["value"] * 100 / 65535 if humidity else v["value"] / 256
            device.readings[key] = Reading(
                value if v["status"] < 3 else None, "%" if humidity else "°C"
            )
        elif name in ("hvac_status", "humidity_status", "hvac_plant", "humidity_plant"):
            state[name] = dict(v)
            if name.endswith("_status"):
                device.readings[name + "_fault"] = Reading(
                    bool(v["status"] & 64), binary=True
                )
                device.readings[name + "_error"] = Reading(v["error"])
            else:
                device.readings[name + "_level"] = Reading(v["level"])
        elif name in ("hvac_on", "hvac_off"):
            state["power"] = name == "hvac_on"
