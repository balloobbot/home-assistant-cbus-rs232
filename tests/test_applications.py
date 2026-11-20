"""Wire vectors for the published C-Bus application chapters."""

import pytest

from custom_components.cbus_rs232.cbus.applications import (
    DEFINITIONS,
    LOAD_APPLICATIONS,
    ApplicationCommand,
    ApplicationEvent,
    decode_application,
    encode_application,
)
from custom_components.cbus_rs232.cbus.protocol import (
    checksum,
    decode_line,
    encode_commands,
    level_command,
    status_request,
)

# Literal command bytes and fields are separate from the production layout table.
VECTORS = [
    (0x19, "temperature", "020756", {"group": 7, "value": 86}),
    (0xCB, "set_enable", "0207FF", {"group": 7, "value": 255}),
    (0xCA, "trigger", "020703", {"group": 7, "action": 3}),
    (0xCA, "trigger_min", "0107", {"group": 7}),
    (0xCA, "trigger_max", "7907", {"group": 7}),
    (0xCA, "indicator_kill", "0907", {"group": 7}),
    (
        0xCA,
        "trigger_label",
        "A707010301486F6D",
        {"group": 7, "options": 1, "action": 3, "language": 1, "text": "486f6d"},
    ),
    (
        0xE4,
        "measurement",
        "0E010200FFFEED",
        {"device": 1, "channel": 2, "units": 0, "multiplier": -1, "value": -275},
    ),
    (
        0xDF,
        "time",
        "0D01172A3BFF",
        {"hour": 23, "minute": 42, "second": 59, "daylight_saving": 255},
    ),
    (
        0xDF,
        "date",
        "0E0207E80C1F01",
        {"year": 2024, "month": 12, "day": 31, "weekday": 1},
    ),
    (0xDF, "request_clock", "1103", {}),
    (
        0xD5,
        "valid_access",
        "A50003010123",
        {"network": 0, "point": 3, "direction": 1, "credential": "0123"},
    ),
    (
        0xD5,
        "invalid_access",
        "C3000302",
        {"network": 0, "point": 3, "direction": 2, "credential": ""},
    ),
    (0xD0, "armed", "7A8001", {"mode": 1}),
    (0xD0, "disarmed", "0180", {}),
    (0xD0, "exit_delay", "0981", {}),
    (0xD0, "entry_delay", "0982", {}),
    (0xD0, "battery_charging", "0A8CFF", {"state": 255}),
    (
        0xD0,
        "zone_name",
        "AD8D034B49544348454E20202020",
        {"zone": 3, "text": "4b49544348454e20202020"},
    ),
    (
        0xD0,
        "security_status",
        "AC8E0100FF0001020304050607",
        {"mode": 1, "tamper": 0, "panic": 255, "zones": "0001020304050607"},
    ),
    (
        0xD0,
        "security_zones",
        "AD8F000102030405060708090A0B",
        {"zones": "000102030405060708090a0b"},
    ),
    (0xD0, "password_status", "0A9000", {"status": 0}),
    (0xD0, "request_security", "09A0", {}),
    (0xD0, "request_security_zones", "09A1", {}),
    (0xD0, "arm", "0AA202", {"mode": 2}),
    (0xD0, "raise_tamper", "79A3", {}),
    (0xD0, "drop_tamper", "01A3", {}),
    (0xD0, "raise_alarm", "79A4", {}),
    (0xD0, "keypad", "0AA50D", {"key": 13}),
    (0xD0, "display_message", "E3A64869", {"text": "4869"}),
    (0xD0, "request_zone_name", "0AA703", {"zone": 3}),
    (0xE0, "on_hook", "0901", {}),
    (0xE0, "off_hook", "A402013132", {"reason": 1, "number": "3132"}),
    (0xE0, "dial_out_failure", "0A0301", {"reason": 1}),
    (0xE0, "dial_in_failure", "0A0401", {"reason": 1}),
    (0xE0, "ringing", "A405013132", {"count": 1, "number": "3132"}),
    (0xE0, "last_number", "A406013132", {"type": 1, "number": "3132"}),
    (0xE0, "internet_request", "0907", {}),
    (0xE0, "isolate_outlet", "0A8000", {"state": 0}),
    (0xE0, "request_last_number", "0A8101", {"type": 1}),
    (0xE0, "reject_call", "0982", {}),
    (0xE0, "divert", "A3833132", {"number": "3132"}),
    (0xE0, "clear_diversion", "0984", {}),
    (0xC0, "stop", "0107", {"group": 7}),
    (0xC0, "play", "7907", {"group": 7}),
    (0xC0, "pause", "0A0700", {"group": 7, "operation": 0}),
    (0xC0, "category", "120703", {"group": 7, "category": 3}),
    (0xC0, "selection", "1B071234", {"group": 7, "selection": 0x1234}),
    (0xC0, "track", "250712345678", {"group": 7, "track": 0x12345678}),
    (0xC0, "shuffle", "2A07FF", {"group": 7, "state": 255}),
    (0xC0, "repeat", "320701", {"group": 7, "type": 1}),
    (0xC0, "step_category", "3A0701", {"group": 7, "operation": 1}),
    (0xC0, "step_selection", "420701", {"group": 7, "operation": 1}),
    (0xC0, "step_track", "4A0700", {"group": 7, "operation": 0}),
    (0xC0, "fast_forward", "520702", {"group": 7, "operation": 2}),
    (0xC0, "rewind", "5A0702", {"group": 7, "operation": 2}),
    (0xC0, "power", "6207FF", {"group": 7, "state": 255}),
    (0xC0, "total_tracks", "6D0712345678", {"group": 7, "total": 0x12345678}),
    (0xC0, "request_media", "7107", {"group": 7}),
    (0xC0, "enumerate", "73070102", {"group": 7, "type": 1, "start": 2}),
    (
        0xC0,
        "enumeration_size",
        "7407010203",
        {"group": 7, "type": 1, "start": 2, "size": 3},
    ),
    (0xC0, "track_name", "8407004869", {"group": 7, "header": 0, "text": "4869"}),
    (0xC0, "selection_name", "A407004869", {"group": 7, "header": 0, "text": "4869"}),
    (0xC0, "category_name", "C407004869", {"group": 7, "header": 0, "text": "4869"}),
    (
        0xAC,
        "hvac_schedule",
        "8907030101011234F600",
        {
            "group": 7,
            "zones": 3,
            "entry": 1,
            "format": 1,
            "mode": 1,
            "start": 0x1234,
            "level": -2560,
        },
    ),
    (
        0xAC,
        "humidity_schedule",
        "A9070301010312348000",
        {
            "group": 7,
            "zones": 3,
            "entry": 1,
            "format": 1,
            "mode": 3,
            "start": 0x1234,
            "level": 32768,
        },
    ),
    (0xAC, "refresh_hvac", "2107", {"group": 7}),
    (
        0xAC,
        "hvac_status",
        "050703010200",
        {"group": 7, "zones": 3, "type": 1, "status": 2, "error": 0},
    ),
    (
        0xAC,
        "humidity_status",
        "0D0703010200",
        {"group": 7, "zones": 3, "type": 1, "status": 2, "error": 0},
    ),
    (
        0xAC,
        "zone_temperature",
        "150703F60000",
        {"group": 7, "zones": 3, "value": -2560, "status": 0},
    ),
    (
        0xAC,
        "zone_humidity",
        "1D0703800000",
        {"group": 7, "zones": 3, "value": 32768, "status": 0},
    ),
    (0xAC, "hvac_off", "0107", {"group": 7}),
    (0xAC, "hvac_on", "7907", {"group": 7}),
    (
        0xAC,
        "set_hvac",
        "2F07030101158000",
        {"group": 7, "zones": 3, "mode": 1, "type": 1, "level": 5504, "auxiliary": 0},
    ),
    (
        0xAC,
        "hvac_plant",
        "3607030205C000",
        {"group": 7, "zones": 3, "mode": 2, "type": 5, "level": -64, "auxiliary": 0},
    ),
    (
        0xAC,
        "set_humidity",
        "4707030303800000",
        {"group": 7, "zones": 3, "mode": 3, "type": 3, "level": 32768, "auxiliary": 0},
    ),
    (
        0xAC,
        "humidity_plant",
        "4E070301018000",
        {"group": 7, "zones": 3, "mode": 1, "type": 1, "level": 128, "auxiliary": 0},
    ),
]
for name, code in (
    ("close_access", "02"),
    ("lock_access", "0A"),
    ("left_open", "12"),
    ("forced_open", "1A"),
    ("closed", "22"),
    ("request_exit", "32"),
):
    VECTORS.append((0xD5, name, code + "0003", {"network": 0, "point": 3}))
for name, code in (
    ("legacy_error", "05"),
    ("error_report", "15"),
    ("acknowledge_error", "25"),
    ("clear_error", "35"),
):
    VECTORS.append(
        (
            0xCE,
            name,
            code + "6401020304",
            {"category_flags": 0x6401, "device": 2, "data1": 3, "data2": 4},
        )
    )
for index, utility in enumerate(
    ("electricity", "gas", "water", "other_water", "oil"), 1
):
    VECTORS += [
        (0xD1, f"request_{utility}", f"09{index:02x}", {}),
        (0xD1, utility, f"0D{128 + index:02x}12345678", {"value": 0x12345678}),
    ]
for name, event in (
    ("alarm", "83"),
    ("tamper", "84"),
    ("panic", "85"),
    ("battery_low", "8B"),
    ("mains_failure", "91"),
    ("line_cut", "94"),
    ("arm_failed", "95"),
    ("fire", "96"),
    ("gas_alarm", "97"),
    ("other_alarm", "98"),
):
    VECTORS += [
        (0xD0, name + "_on", "79" + event, {}),
        (0xD0, name + "_off", "01" + event, {}),
    ]
for name, event in (
    ("zone_unsealed", "86"),
    ("zone_sealed", "87"),
    ("zone_open", "88"),
    ("zone_short", "89"),
    ("zone_isolated", "8A"),
    ("arm_ready", "92"),
):
    VECTORS.append((0xD0, name, "0A" + event + "03", {"zone": 3}))
for name, code in (
    ("hvac_upper_guard", "55"),
    ("hvac_lower_guard", "5D"),
    ("hvac_setback", "65"),
    ("humidity_upper_guard", "6D"),
    ("humidity_lower_guard", "75"),
    ("humidity_setback", "7D"),
):
    VECTORS.append(
        (
            0xAC,
            name,
            code + "0703158001",
            {"group": 7, "zones": 3, "level": 5504, "mode": 1},
        )
    )


@pytest.mark.parametrize("application,name,wire,fields", VECTORS)
def test_wire_vectors(application, name, wire, fields):
    payload = bytes.fromhex(wire)
    command = ApplicationCommand(name, fields)
    assert decode_application(application, payload) == (command,)
    if name == "legacy_error":
        with pytest.raises(ValueError, match="receive-only"):
            encode_application(application, name, fields)
    else:
        expected = {
            "trigger_min": bytes.fromhex("020700"),
            "trigger_max": bytes.fromhex("0207FF"),
        }.get(name, payload)
        assert (
            encode_application(application, name, fields)
            == bytes([5, application, 0]) + expected
        )
    received = checksum(bytes([5, 23, application, 0]) + payload).hex().encode()
    assert decode_line(received) == ApplicationEvent(application, 23, (command,))
    with pytest.raises(ValueError):
        decode_application(application, payload[:-1])


def test_every_defined_command_has_a_vector():
    assert {(app, d.name) for app, defs in DEFINITIONS.items() for d in defs} == {
        (app, name) for app, name, _, _ in VECTORS
    }


@pytest.mark.parametrize("application", [0x19, 0xCB, 0xCA])
@pytest.mark.parametrize("code", range(2, 128, 8))
def test_variable_opcode_aliases(application, code):
    assert decode_application(application, bytes([code, 7, 4]))[0].values == {
        "group": 7,
        "action" if application == 0xCA else "value": 4,
    }


@pytest.mark.parametrize("application", LOAD_APPLICATIONS)
def test_load_applications(application):
    assert encode_commands(application, (level_command(3, 128),)) == bytes(
        [5, application, 0, 2, 3, 128]
    )
    assert status_request(application) == bytes([5, 255, 0, 0x7A, application, 0])


def test_concatenation_and_reserved_commands():
    assert [
        c.name
        for c in decode_application(0xD0, bytes.fromhex("098109821F000000000000007983"))
    ] == ["exit_delay", "entry_delay", "alarm_on"]
    assert decode_application(0xD0, bytes.fromhex("09FF")) == ()
    assert decode_application(0xD0, bytes.fromhex("E0")) == ()
    assert decode_application(0xC0, bytes.fromhex("00400107")) == (
        ApplicationCommand("stop", {"group": 7}),
    )
    for payload in (b"", b"\xa1\x00", b"\xb3" + bytes(19)):
        with pytest.raises(ValueError):
            decode_application(0xD5, payload)


@pytest.mark.parametrize(
    "application,name,fields",
    [
        (0xCB, "set_enable", {}),
        (0xCB, "set_enable", {"group": 1, "value": 256}),
        (0xCB, "set_enable", {"group": 1, "value": True}),
        (0xCB, "set_enable", {"group": 1, "value": 1.5}),
        (0xCB, "set_enable", {"group": 1, "value": "zz"}),
        (
            0xD5,
            "valid_access",
            {"network": 0, "point": 1, "direction": 3, "credential": ""},
        ),
        (
            0xD5,
            "valid_access",
            {"network": 0, "point": 1, "direction": 0, "credential": "00" * 11},
        ),
        (
            0xD5,
            "valid_access",
            {"network": 0, "point": 1, "direction": 0, "credential": 1},
        ),
        (0xD0, "zone_name", {"zone": 1, "text": "00" * 10}),
        (0xD0, "zone_name", {"zone": 1, "text": b"01234567890"}),
        (0xD0, "zone_name", {"zone": 1, "text": "00" * 12}),
        (0xD0, "zone_name", {"zone": 1, "text": 1}),
        (0xD0, "arm", {"mode": 0}),
        (0xC0, "shuffle", {"group": 1, "state": 1}),
        (0xDF, "time", {"hour": 24, "minute": 0, "second": 0, "daylight_saving": 0}),
        (0xDF, "time", {"hour": 0, "minute": 0, "second": 0, "daylight_saving": 2}),
        (0xDF, "date", {"year": 2024, "month": 2, "day": 30, "weekday": 0}),
        (0xDF, "date", {"year": 2024, "month": 2, "day": 29, "weekday": 7}),
        (0xE0, "ringing", {"count": 2, "number": ""}),
        (0, "unknown", {}),
        (0xD0, "unknown", {}),
    ],
)
def test_bad_fields(application, name, fields):
    with pytest.raises(ValueError):
        encode_application(application, name, fields)


@pytest.mark.parametrize(
    "field,value",
    [
        ("zones", 0),
        ("zones", 128),
        ("mode", 128),
        ("mode", 5),
        ("auxiliary", 128),
        ("type", 11),
    ],
)
def test_reserved_hvac_fields(field, value):
    with pytest.raises(ValueError):
        encode_application(
            0xAC,
            "set_hvac",
            dict(group=1, zones=1, mode=1, type=1, level=5504, auxiliary=0)
            | {field: value},
        )


@pytest.mark.parametrize("name", ["zone_temperature", "zone_humidity"])
def test_reserved_sensor_status(name):
    with pytest.raises(ValueError):
        encode_application(0xAC, name, dict(group=1, zones=1, value=0, status=4))


def test_fixed_width_decode_and_load_rejection():
    with pytest.raises(ValueError):
        DEFINITIONS[0xCB][0].decode(b"\x01\x02\x03")
    with pytest.raises(ValueError):
        status_request(0xCA)


@pytest.mark.parametrize(
    "app,name,fields",
    [
        (0xCA, "trigger", {"group": 255, "action": 1}),
        (0xC0, "play", {"group": 255}),
        (0xC0, "category", {"group": 1, "category": 128}),
        (0xC0, "selection", {"group": 1, "selection": 32768}),
        (0xC0, "track", {"group": 1, "track": 2147483648}),
        (0xC0, "fast_forward", {"group": 1, "operation": 1}),
        (0xC0, "rewind", {"group": 1, "operation": 13}),
    ],
)
def test_reserved_application_values(app, name, fields):
    with pytest.raises(ValueError):
        encode_application(app, name, fields)


@pytest.mark.parametrize(
    "format,start,valid",
    [(0, 0, False), (8, 0, False), (1, 10080, False), (7, 65535, True)],
)
def test_schedule_formats(format, start, valid):
    fields = dict(
        group=1, zones=1, entry=1, format=format, mode=1, start=start, level=5504
    )
    if valid:
        assert encode_application(0xAC, "hvac_schedule", fields)
    else:
        with pytest.raises(ValueError):
            encode_application(0xAC, "hvac_schedule", fields)


@pytest.mark.parametrize(
    "options,text,valid",
    [
        (0, "", False),
        (9, "", False),
        (17, "", False),
        (129, "", False),
        (3, "010203", True),
        (3, "020203", False),
        (3, "01", False),
        (7, "", True),
        (7, "01", False),
        (133, "01", True),
    ],
)
def test_trigger_label_options(options, text, valid):
    fields = dict(group=1, options=options, action=2, language=1, text=text)
    if valid:
        assert encode_application(0xCA, "trigger_label", fields)
    else:
        with pytest.raises(ValueError):
            encode_application(0xCA, "trigger_label", fields)


def test_trigger_label_position():
    with pytest.raises(ValueError, match="last"):
        decode_application(0xCA, bytes.fromhex("A407010201020102"))
    assert [
        c.name for c in decode_application(0xCA, bytes.fromhex("020102A407010201"))
    ] == ["trigger", "trigger_label"]


@pytest.mark.parametrize("header", [0x80, 0x30, 0x40, 0x01])
def test_invalid_media_fragment_headers(header):
    with pytest.raises(ValueError):
        encode_application(0xC0, "track_name", dict(group=1, header=header, text="00"))


def test_security_display_length():
    data = encode_application(0xD0, "display_message", {"text": "41" * 18})
    assert data == bytes.fromhex("05D000F3A6") + b"A" * 18
    with pytest.raises(ValueError):
        encode_application(0xD0, "display_message", {"text": "41" * 19})
