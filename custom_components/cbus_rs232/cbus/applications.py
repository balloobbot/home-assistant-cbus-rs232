"""Application command layouts from the Open C-Bus application chapters."""

import struct
from dataclasses import dataclass
from datetime import date, time

APPLICATIONS = {
    0x19: "Temperature",
    0x70: "Ventilation",
    0x71: "Irrigation",
    0x72: "Pools",
    0x73: "HVAC actuator 1",
    0x74: "HVAC actuator 2",
    0xAC: "Air conditioning",
    0xC0: "Media",
    0xCA: "Trigger",
    0xCB: "Enable",
    0xCE: "Error reporting",
    0xD0: "Security",
    0xD1: "Metering",
    0xD5: "Access control",
    0xDF: "Clock",
    0xE0: "Telephony",
    0xE4: "Measurement",
}
LOAD_APPLICATIONS = frozenset((*range(0x30, 0x60), *range(0x70, 0x75)))


@dataclass(frozen=True)
class Definition:
    name: str
    opcode: int
    layout: str
    fields: str
    event: int | None = None
    tail: str | None = None
    maximum: int = 16

    def decode(self, data: bytes) -> dict:
        prefix = int(self.event is not None)
        body = data[prefix:]
        size = struct.calcsize(">" + self.layout)
        if len(body) < size or (self.tail is None and len(body) != size):
            raise ValueError("Invalid command length")
        if self.tail is not None and len(body) - size > self.maximum:
            raise ValueError("Application text exceeds its maximum length")
        values = struct.unpack(">" + self.layout, body[:size])
        result = {
            key: value.hex() if isinstance(value, bytes) else value
            for key, value in zip(self.fields.split(), values, strict=True)
        }
        if self.tail is not None:
            result[self.tail] = body[size:].hex()
        validate(self.name, result)
        return result

    def encode(self, values: dict) -> bytes:
        names = self.fields.split() + ([self.tail] if self.tail else [])
        if set(names) != values.keys():
            raise ValueError(f"{self.name} requires fields: {', '.join(names)}")
        try:
            args = [
                bytes.fromhex(values[key])
                if isinstance(values[key], str)
                else values[key]
                for key in self.fields.split()
            ]
            body = struct.pack(">" + self.layout, *args)
        except (struct.error, TypeError) as err:
            raise ValueError("Invalid application field value") from err
        if self.event is not None:
            body = bytes([self.event]) + body
        if self.tail is not None:
            if not isinstance(values[self.tail], str):
                raise ValueError("Byte fields require hexadecimal text")
            body += bytes.fromhex(values[self.tail])
        decoded = self.decode(body)
        for key, value in decoded.items():
            if isinstance(value, str):
                if not isinstance(values[key], str) or bytes.fromhex(
                    value
                ) != bytes.fromhex(values[key]):
                    raise ValueError("Invalid fixed-width field length")
            elif type(values[key]) is not int:
                raise ValueError("Numeric fields require integers")
        opcode = self.opcode | len(body) if self.tail is not None else self.opcode
        return bytes([opcode]) + body


@dataclass(frozen=True)
class ApplicationCommand:
    name: str
    values: dict


@dataclass(frozen=True)
class ApplicationEvent:
    application: int
    source: int
    commands: tuple[ApplicationCommand, ...]


D = Definition
DEFINITIONS: dict[int, tuple[Definition, ...]] = {
    0x19: (D("temperature", 2, "BB", "group value"),),
    0xCB: (D("set_enable", 2, "BB", "group value"),),
    0xCA: (
        D("trigger", 2, "BB", "group action"),
        D("trigger_min", 1, "B", "group"),
        D("trigger_max", 0x79, "B", "group"),
        D("indicator_kill", 9, "B", "group"),
        D("trigger_label", 0xA0, "BBBB", "group options action language", tail="text"),
    ),
    0xD1: tuple(
        definition
        for index, utility in enumerate(
            ("electricity", "gas", "water", "other_water", "oil"), 1
        )
        for definition in (
            D(f"request_{utility}", 9, "", "", index),
            D(utility, 13, "I", "value", 128 + index),
        )
    ),
    0xE4: (D("measurement", 14, "BBBbh", "device channel units multiplier value"),),
    0xDF: (
        D("time", 13, "BBBB", "hour minute second daylight_saving", 1),
        D("date", 14, "HBBB", "year month day weekday", 2),
        D("request_clock", 17, "", "", 3),
    ),
    0xD5: (
        D(
            "valid_access",
            0xA0,
            "BBB",
            "network point direction",
            tail="credential",
            maximum=10,
        ),
        D(
            "invalid_access",
            0xC0,
            "BBB",
            "network point direction",
            tail="credential",
            maximum=10,
        ),
        *(
            D(name, code, "BB", "network point")
            for name, code in (
                ("close_access", 2),
                ("lock_access", 10),
                ("left_open", 18),
                ("forced_open", 26),
                ("closed", 34),
                ("request_exit", 50),
            )
        ),
    ),
    0xCE: tuple(
        D(name, code, "HBBB", "category_flags device data1 data2")
        for name, code in (
            ("legacy_error", 5),
            ("error_report", 0x15),
            ("acknowledge_error", 0x25),
            ("clear_error", 0x35),
        )
    ),
    0xD0: (
        D("armed", 0x7A, "B", "mode", 0x80),
        D("disarmed", 1, "", "", 0x80),
        D("exit_delay", 9, "", "", 0x81),
        D("entry_delay", 9, "", "", 0x82),
        *(
            D(name + suffix, code, "", "", event)
            for name, event in (
                ("alarm", 0x83),
                ("tamper", 0x84),
                ("panic", 0x85),
                ("battery_low", 0x8B),
                ("mains_failure", 0x91),
                ("line_cut", 0x94),
                ("arm_failed", 0x95),
                ("fire", 0x96),
                ("gas_alarm", 0x97),
                ("other_alarm", 0x98),
            )
            for suffix, code in (("_on", 0x79), ("_off", 1))
        ),
        *(
            D(name, 10, "B", "zone", event)
            for name, event in (
                ("zone_unsealed", 0x86),
                ("zone_sealed", 0x87),
                ("zone_open", 0x88),
                ("zone_short", 0x89),
                ("zone_isolated", 0x8A),
                ("arm_ready", 0x92),
            )
        ),
        D("battery_charging", 10, "B", "state", 0x8C),
        D("zone_name", 0xAD, "B11s", "zone text", 0x8D),
        D("security_status", 0xAC, "BBB8s", "mode tamper panic zones", 0x8E),
        D("security_zones", 0xAD, "12s", "zones", 0x8F),
        D("password_status", 10, "B", "status", 0x90),
        D("request_security", 9, "", "", 0xA0),
        D("request_security_zones", 9, "", "", 0xA1),
        D("arm", 10, "B", "mode", 0xA2),
        D("raise_tamper", 0x79, "", "", 0xA3),
        D("drop_tamper", 1, "", "", 0xA3),
        D("raise_alarm", 0x79, "", "", 0xA4),
        D("keypad", 10, "B", "key", 0xA5),
        D("display_message", 0xE0, "", "", 0xA6, "text", 18),
        D("request_zone_name", 10, "B", "zone", 0xA7),
    ),
    0xE0: (
        D("on_hook", 9, "", "", 1),
        D("off_hook", 0xA0, "B", "reason", 2, "number"),
        D("dial_out_failure", 10, "B", "reason", 3),
        D("dial_in_failure", 10, "B", "reason", 4),
        D("ringing", 0xA0, "B", "count", 5, "number"),
        D("last_number", 0xA0, "B", "type", 6, "number"),
        D("internet_request", 9, "", "", 7),
        D("isolate_outlet", 10, "B", "state", 0x80),
        D("request_last_number", 10, "B", "type", 0x81),
        D("reject_call", 9, "", "", 0x82),
        D("divert", 0xA0, "", "", 0x83, "number"),
        D("clear_diversion", 9, "", "", 0x84),
    ),
    0xC0: (
        D("stop", 1, "B", "group"),
        D("play", 0x79, "B", "group"),
        D("pause", 10, "BB", "group operation"),
        D("category", 0x12, "BB", "group category"),
        D("selection", 0x1B, "BH", "group selection"),
        D("track", 0x25, "BI", "group track"),
        D("shuffle", 0x2A, "BB", "group state"),
        D("repeat", 0x32, "BB", "group type"),
        *(
            D(name, code, "BB", "group operation")
            for name, code in (
                ("step_category", 0x3A),
                ("step_selection", 0x42),
                ("step_track", 0x4A),
                ("fast_forward", 0x52),
                ("rewind", 0x5A),
            )
        ),
        D("power", 0x62, "BB", "group state"),
        D("total_tracks", 0x6D, "BI", "group total"),
        D("request_media", 0x71, "B", "group"),
        D("enumerate", 0x73, "BBB", "group type start"),
        D("enumeration_size", 0x74, "BBBB", "group type start size"),
        *(
            D(name, code, "BB", "group header", tail="text", maximum=29)
            for name, code in (
                ("track_name", 0x80),
                ("selection_name", 0xA0),
                ("category_name", 0xC0),
            )
        ),
    ),
    0xAC: (
        D(
            "hvac_schedule",
            0x89,
            "BBBBBHh",
            "group zones entry format mode start level",
        ),
        D(
            "humidity_schedule",
            0xA9,
            "BBBBBHH",
            "group zones entry format mode start level",
        ),
        D("refresh_hvac", 0x21, "B", "group"),
        D("hvac_status", 5, "BBBBB", "group zones type status error"),
        D("humidity_status", 13, "BBBBB", "group zones type status error"),
        D("zone_temperature", 21, "BBhB", "group zones value status"),
        D("zone_humidity", 29, "BBHB", "group zones value status"),
        D("hvac_off", 1, "B", "group"),
        D("hvac_on", 0x79, "B", "group"),
        D("set_hvac", 0x2F, "BBBBhB", "group zones mode type level auxiliary"),
        D("hvac_plant", 0x36, "BBBBbB", "group zones mode type level auxiliary"),
        D("set_humidity", 0x47, "BBBBHB", "group zones mode type level auxiliary"),
        D("humidity_plant", 0x4E, "BBBBBB", "group zones mode type level auxiliary"),
        *(
            D(name, code, "BBhB", "group zones level mode")
            for name, code in (
                ("hvac_upper_guard", 0x55),
                ("hvac_lower_guard", 0x5D),
                ("hvac_setback", 0x65),
            )
        ),
        *(
            D(name, code, "BBHB", "group zones level mode")
            for name, code in (
                ("humidity_upper_guard", 0x6D),
                ("humidity_lower_guard", 0x75),
                ("humidity_setback", 0x7D),
            )
        ),
    ),
}


def validate(name: str, values: dict) -> None:
    if (
        "zones" in values
        and isinstance(values["zones"], int)
        and not 1 <= values["zones"] <= 127
    ):
        raise ValueError("Zone list must select zones 0 through 6")
    if name in (
        "set_hvac",
        "set_humidity",
        "hvac_plant",
        "humidity_plant",
        "hvac_schedule",
        "humidity_schedule",
    ):
        if values["mode"] & 128 or values["mode"] & 7 > (
            3 if "humidity" in name else 4
        ):
            raise ValueError("Reserved HVAC mode")
        if "auxiliary" in values and values["auxiliary"] & 128:
            raise ValueError("Reserved auxiliary bit")
    if name in ("zone_temperature", "zone_humidity") and values["status"] > 3:
        raise ValueError("Reserved sensor status")
    if "type" in values and name.startswith(
        (
            "set_hvac",
            "hvac_plant",
            "hvac_status",
            "set_humidity",
            "humidity_plant",
            "humidity_status",
        )
    ):
        allowed = (*range(11), 255) if "hvac" in name else range(4)
        if values["type"] not in allowed:
            raise ValueError("Reserved plant type")
    if name in ("hvac_schedule", "humidity_schedule"):
        if values["format"] not in range(1, 8) or not (
            0 <= values["start"] < 10080 or values["start"] == 65535
        ):
            raise ValueError("Invalid schedule format or start time")
    if (
        name in ("category", "selection", "track")
        and values[name]
        >= {"category": 128, "selection": 32768, "track": 2147483648}[name]
    ):
        raise ValueError("Reserved media index")
    if name in ("fast_forward", "rewind") and values["operation"] not in range(
        0, 13, 2
    ):
        raise ValueError("Reserved media speed")
    if name == "ringing" and values["count"] != 1:
        raise ValueError("Ringing count must be one")
    if name == "trigger_label":
        options, text = values["options"], bytes.fromhex(values["text"])
        kind = options & 6
        if not options & 1 or options & 0x18 or options & 0x80 and kind != 4:
            raise ValueError("Reserved trigger label options")
        if kind == 2 and (len(text) != 3 or text[0] != 1):
            raise ValueError("Invalid trigger icon")
        if kind == 6 and text:
            raise ValueError("Preferred language cannot contain text")
    if name in ("track_name", "selection_name", "category_name"):
        header = values["header"]
        if (
            header & 128
            or (header >> 4) & 7 in (3, 4)
            or header & 3 > (header >> 2) & 3
        ):
            raise ValueError("Invalid media text header")
    if name == "time":
        time(values["hour"], values["minute"], values["second"])
        if values["daylight_saving"] not in (0, 1, 255):
            raise ValueError("Reserved daylight saving value")
    if name == "date":
        date(values["year"], values["month"], values["day"])
        if values["weekday"] > 6:
            raise ValueError("Invalid weekday")
    if name == "arm" and values["mode"] not in (1, 2, 3, 4, 255):
        raise ValueError("Reserved arm mode")
    if name in ("valid_access", "invalid_access") and values["direction"] > 2:
        raise ValueError("Invalid access direction")
    if name == "shuffle" and values["state"] not in (0, 255):
        raise ValueError("Reserved shuffle value")


def decode_application(
    application: int, payload: bytes
) -> tuple[ApplicationCommand, ...]:
    if not payload:
        raise ValueError("Empty application payload")
    commands = []
    while payload:
        code = payload[0]
        length = code & (31 if code & 128 else 7)
        if len(payload) < length + 1:
            raise ValueError("Truncated application command")
        data, payload = payload[1 : length + 1], payload[length + 1 :]
        for definition in DEFINITIONS[application]:
            match = (
                (code & 0xE0 == definition.opcode)
                if definition.tail
                else code == definition.opcode
            )
            if application in (0x19, 0xCB) or (
                application == 0xCA and definition.name == "trigger"
            ):
                match = code < 128 and code & 7 == 2
            if match and (
                definition.event is None or data and data[0] == definition.event
            ):
                if definition.name == "trigger_label" and payload:
                    raise ValueError("Trigger label must be last")
                commands.append(
                    ApplicationCommand(definition.name, definition.decode(data))
                )
                break
    return tuple(commands)


def encode_application(application: int, name: str, values: dict) -> bytes:
    if application in (0xCA, 0xC0) and values.get("group") == 255:
        raise ValueError("Group 255 is unused in this application")
    if application == 0xCE and name == "legacy_error":
        raise ValueError("legacy_error is receive-only; use error_report")
    for definition in DEFINITIONS.get(application, ()):
        if definition.name == name:
            command = definition.encode(values)
            if application == 0xCA and name in ("trigger_min", "trigger_max"):
                command = bytes(
                    [2, values["group"], 0 if name == "trigger_min" else 255]
                )
            return bytes([5, application, 0]) + command
    raise ValueError("Unknown application command")
