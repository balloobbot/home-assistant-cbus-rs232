"""Application state from network traffic, including multi-command frames."""

import pytest

from custom_components.cbus_rs232.cbus.applications import (
    ApplicationCommand,
    ApplicationEvent,
)
from custom_components.cbus_rs232.cbus.state import MEASUREMENT_UNITS, ApplicationState

from .test_applications import VECTORS


def apply(model, app, name, source=23, **fields):
    model.apply(ApplicationEvent(app, source, (ApplicationCommand(name, fields),)))
    return next(reversed(model.devices.values()))


@pytest.mark.parametrize("app,name,wire,fields", VECTORS)
def test_all_commands_have_events(app, name, wire, fields):
    state = ApplicationState()
    apply(state, app, name, **fields)
    assert state.devices
    for device in state.devices.values():
        assert device.event == ApplicationCommand(name, fields)
        assert list(device.events) == [(1, device.event)]


def test_group_values_and_trigger_sequence():
    state = ApplicationState()
    device = apply(state, 0x19, "temperature", group=1, value=86)
    assert device.readings["temperature"].value == 21.5
    assert device.readings["temperature"].unit == "°C"
    device = apply(state, 0xCB, "set_enable", group=2, value=17)
    assert device.values["value"] == 17
    state.apply(
        ApplicationEvent(
            0xCA,
            23,
            tuple(
                ApplicationCommand("trigger", dict(group=3, action=i))
                for i in range(70)
            ),
        )
    )
    device = state.devices[0xCA, "group_3"]
    assert device.sequence == 70
    assert device.readings["action"].value == 69
    assert [sequence for sequence, _ in device.events] == list(range(7, 71))
    apply(state, 0xCA, "trigger_min", group=3)
    assert device.readings["action"].value == 0
    apply(state, 0xCA, "trigger_max", group=3)
    assert device.readings["action"].value == 255


@pytest.mark.parametrize("units", [*range(40), 254, 255])
def test_measurements(units):
    device = apply(
        ApplicationState(),
        0xE4,
        "measurement",
        device=1,
        channel=2,
        units=units,
        multiplier=-2,
        value=-1234,
    )
    reading = device.readings["measurement"]
    assert reading.value == (True if units == 4 else -12.34)
    assert reading.binary == (units == 4)
    assert reading.unit == (MEASUREMENT_UNITS[units] if units < 40 else None)
    assert device.address == {"device": 1, "channel": 2}


def test_meter_sources_do_not_collide():
    state = ApplicationState()
    for source in (1, 2):
        apply(state, 0xD1, "electricity", source, value=source * 100)
    assert state.devices[0xD1, "source_1"].readings["electricity"].value == 100
    assert state.devices[0xD1, "source_2"].readings["electricity"].value == 200
    assert state.devices[0xD1, "source_1"].readings["electricity"].total


def test_contacts_clock_and_phone():
    state = ApplicationState()
    device = apply(state, 0xD5, "left_open", network=1, point=2)
    assert device.readings["open"].value is True
    apply(state, 0xD5, "closed", network=1, point=2)
    assert device.readings["open"].value is False
    apply(state, 0xD5, "lock_access", network=1, point=2)
    assert device.readings["open"].value is False
    device = apply(
        state, 0xDF, "time", hour=13, minute=14, second=15, daylight_saving=0
    )
    assert device.readings["time"].value == "13:14:15"
    apply(state, 0xDF, "date", year=2026, month=11, day=19, weekday=3)
    assert device.readings["date"].value == "2026-11-19"
    device = apply(state, 0xE0, "ringing", count=1, number="31323334")
    assert device.readings["line"].value == "ringing"
    assert device.readings["number"].value == "1234"


def test_security_zones_and_status():
    state = ApplicationState()
    device = apply(
        state,
        0xD0,
        "security_status",
        mode=1,
        tamper=0,
        panic=255,
        zones="1b" + "00" * 7,
    )
    assert device.values["mode"] == 1
    assert device.readings["tamper"].value is False
    assert device.readings["panic"].value is True
    assert [device.readings[f"zone_{i}"].value for i in range(1, 5)] == [
        False,
        True,
        True,
        True,
    ]
    apply(state, 0xD0, "security_zones", zones="00" * 11 + "03")
    assert device.readings["zone_79"].value is False
    assert device.readings["zone_80"].value is True
    apply(state, 0xD0, "zone_name", zone=1, text="48616c6c20202020202020")
    assert device.values["zone_1_name"] == "Hall"
    for name in ("zone_open", "zone_short", "zone_unsealed"):
        apply(state, 0xD0, name, zone=1)
        assert device.readings["zone_1"].value is True
    apply(state, 0xD0, "zone_sealed", zone=1)
    assert device.readings["zone_1"].value is False
    apply(state, 0xD0, "entry_delay")
    assert device.values["delay"] == "entry_delay"
    apply(state, 0xD0, "disarmed")
    assert device.values["delay"] is None
    assert device.values["mode"] == 0
    for name in ("alarm", "panic", "fire", "tamper"):
        apply(state, 0xD0, name + "_on")
        assert device.values[name] is True
        apply(state, 0xD0, name + "_off")
        assert device.values[name] is False


def test_current_and_latched_errors():
    state = ApplicationState()
    device = apply(
        state, 0xCE, "error_report", category_flags=0x0063, device=1, data1=3, data2=4
    )
    assert device.readings["fault"].value is True
    assert device.readings["severity"].value == 3
    apply(
        state, 0xCE, "error_report", category_flags=0x004C, device=1, data1=3, data2=4
    )
    assert device.readings["severity"].value == 3
    apply(
        state, 0xCE, "error_report", category_flags=0x0061, device=1, data1=3, data2=0
    )
    assert device.readings["fault"].value is False


def test_media_state():
    state = ApplicationState()
    device = apply(state, 0xC0, "play", group=7)
    assert device.values["playback"] == "playing"
    apply(state, 0xC0, "pause", group=7, operation=0)
    assert device.values["playback"] == "paused"
    apply(state, 0xC0, "pause", group=7, operation=1)
    assert device.values["playback"] == "playing"
    apply(state, 0xC0, "stop", group=7)
    assert device.values["playback"] == "idle"
    for value, expected in ((0, "off"), (1, "one"), (255, "all")):
        apply(state, 0xC0, "repeat", group=7, type=value)
        assert device.values["repeat"] == expected
    apply(state, 0xC0, "shuffle", group=7, state=0)
    assert device.values["shuffle"] is False


def test_fragmented_utf8_metadata():
    state = ApplicationState()
    device = apply(state, 0xC0, "track_name", group=7, header=4, text="436166c3")
    assert "track_name" not in device.values
    apply(state, 0xC0, "track_name", group=7, header=5, text="a9")
    assert device.values["track_name"] == "Café"
    assert not device.text_parts
    apply(state, 0xC0, "track_name", group=7, header=0x10, text="78")
    assert device.values["track_name"] == "Café"
    for header in (6, 5, 9):
        apply(state, 0xC0, "track_name", group=7, header=4, text="00")
        if header == 5:
            apply(state, 0xC0, "track_name", group=7, header=6, text="00")
        apply(state, 0xC0, "track_name", group=7, header=header, text="00")
        assert device.values["track_name"] == "Café"
        assert not device.text_parts


def test_hvac_zone_masks_and_group_commands():
    state = ApplicationState()
    apply(state, 0xAC, "refresh_hvac", group=1)
    assert len(state.devices) == 1
    apply(
        state,
        0xAC,
        "set_hvac",
        group=1,
        zones=0x45,
        mode=1,
        type=1,
        level=5504,
        auxiliary=0,
    )
    assert {d.address["zone"] for d in state.devices.values()} == {0, 2, 6}
    apply(state, 0xAC, "hvac_off", group=1)
    assert all(not d.values["power"] for d in state.devices.values())
    apply(state, 0xAC, "zone_temperature", group=1, zones=0x45, value=-2560, status=0)
    assert all(d.readings["temperature"].value == -10 for d in state.devices.values())
    apply(state, 0xAC, "zone_temperature", group=1, zones=1, value=-2560, status=3)
    assert state.devices[0xAC, "group_1_zone_0"].readings["temperature"].value is None
    assert state.devices[0xAC, "group_1_zone_2"].readings["temperature"].value == -10
    apply(state, 0xAC, "zone_humidity", group=1, zones=1, value=65535, status=0)
    assert state.devices[0xAC, "group_1_zone_0"].readings["humidity"].value == 100


def test_published_error_reports_and_all_ok():
    from custom_components.cbus_rs232.cbus.applications import decode_application

    model = ApplicationState()
    apply(model, 0xD0, "disarmed")
    apply(
        model, 0xCE, "error_report", category_flags=0x9023, device=99, data1=1, data2=0
    )
    apply(
        model,
        0xCE,
        "error_report",
        category_flags=0x8822,
        device=0x42,
        data1=1,
        data2=0,
    )
    for payload in ("159023426633", "159023426700", "15882A6721B4", "15FF20DE0000"):
        model.apply(
            ApplicationEvent(0xCE, 23, decode_application(0xCE, bytes.fromhex(payload)))
        )
    current = model.devices[0xCE, "device_66_category_576_event_102"]
    assert current.readings["severity"].value == 3
    assert (
        model.devices[0xCE, "device_103_category_544_event_33"]
        .readings["severity"]
        .value
        == 2
    )
    model.apply(
        ApplicationEvent(
            0xCE, 23, decode_application(0xCE, bytes.fromhex("159020420000"))
        )
    )
    assert current.readings["fault"].value is False
    assert (
        model.devices[0xCE, "device_66_category_576_event_103"].readings["fault"].value
        is False
    )
    assert (
        model.devices[0xCE, "device_99_category_576_event_1"].readings["fault"].value
        is True
    )
    assert (
        model.devices[0xCE, "device_66_category_544_event_1"].readings["fault"].value
        is True
    )


def test_enable_wildcard_and_unused_groups():
    state = ApplicationState()
    apply(state, 0xCB, "set_enable", group=1, value=10)
    apply(state, 0xCB, "set_enable", group=2, value=20)
    apply(state, 0xCA, "trigger", group=7, action=1)
    apply(state, 0xCB, "set_enable", group=255, value=0)
    assert state.devices[0xCB, "group_1"].values["value"] == 0
    assert state.devices[0xCB, "group_2"].values["value"] == 0
    apply(state, 0xCA, "trigger", group=255, action=5)
    apply(state, 0xC0, "play", group=255)
    assert len(state.devices) == 3
    device = apply(state, 0x19, "temperature", group=255, value=86)
    assert device.address == {"group": 255}


def test_security_arm_readiness():
    state = ApplicationState()
    device = apply(state, 0xD0, "arm_ready", zone=3)
    assert device.readings["arm_ready"].value is False
    apply(state, 0xD0, "arm_ready", zone=0)
    assert device.readings["arm_ready"].value is True


def test_media_text_total_length_limit():
    model = ApplicationState()
    device = apply(model, 0xC0, "track_name", group=1, header=4, text="41" * 20)
    apply(model, 0xC0, "track_name", group=1, header=5, text="42" * 20)
    assert device.values["track_name"] == "A" * 20 + "B" * 20
    apply(model, 0xC0, "track_name", group=1, header=4, text="41" * 20)
    apply(model, 0xC0, "track_name", group=1, header=5, text="43" * 21)
    assert device.values["track_name"] == "A" * 20 + "B" * 20
    assert not device.text_parts
