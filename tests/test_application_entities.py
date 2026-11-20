"""Exercise each application through Home Assistant entities and actions."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.auth.const import GROUP_ID_USER
from homeassistant.core import Context
from homeassistant.exceptions import HomeAssistantError, Unauthorized
from homeassistant.helpers import entity_registry as er

from custom_components.cbus_rs232.cbus.applications import (
    ApplicationCommand,
    ApplicationEvent,
)
from custom_components.cbus_rs232.cbus.client import Group
from custom_components.cbus_rs232.cbus.protocol import (
    GroupStatus,
    Status,
    StatusReport,
    checksum,
)
from custom_components.cbus_rs232.climate import ZoneClimate
from custom_components.cbus_rs232.const import DOMAIN
from custom_components.cbus_rs232.fan import VentilationFan
from custom_components.cbus_rs232.humidifier import ZoneHumidifier
from custom_components.cbus_rs232.number import EnableNumber
from custom_components.cbus_rs232.services import load_command


@pytest.fixture
async def loaded(hass, entry, pci):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    yield entry
    await hass.config_entries.async_unload(entry.entry_id)


def emit(entry, app, name, **fields):
    entry.runtime_data._apply(
        ApplicationEvent(app, 23, (ApplicationCommand(name, fields),))
    )


def entity_id(hass, entry, platform, key):
    result = er.async_get(hass).async_get_entity_id(
        platform, DOMAIN, f"{entry.entry_id}_{key}"
    )
    assert result is not None
    return result


async def call(hass, platform, service, entity, **fields):
    await hass.services.async_call(
        platform, service, {"entity_id": entity, **fields}, blocking=True
    )


async def test_all_load_platforms(hass, loaded, pci):
    client = loaded.runtime_data
    for app in (0x30, 0x5F, 0x70, 0x71, 0x72, 0x73, 0x74):
        client._apply(StatusReport(app, (GroupStatus(1, Status.ON, 128),)))
    await hass.async_block_till_done()
    for app, platform in (
        (0x30, "light"),
        (0x5F, "light"),
        (0x70, "fan"),
        (0x71, "switch"),
        (0x72, "switch"),
        (0x73, "switch"),
        (0x74, "switch"),
    ):
        eid = entity_id(hass, loaded, platform, f"{app}_1")
        assert hass.states.get(eid).state == "on"
        await call(hass, platform, "turn_off", eid)
        assert client.loads[app][1].level == 0
        await call(hass, platform, "turn_on", eid)
        assert client.loads[app][1].level == 255
        assert pci.writes[-1].startswith(f"\\05{app:02X}000201FF".encode())
    fan = entity_id(hass, loaded, "fan", "112_1")
    await call(hass, "fan", "set_percentage", fan, percentage=50)
    assert client.loads[0x70][1].level == 128
    assert hass.states.get(fan).attributes["percentage"] == 50
    await call(hass, "fan", "turn_on", fan, percentage=25)
    assert client.loads[0x70][1].level == 64
    assert VentilationFan(loaded, Group(2)).percentage is None


async def test_sensor_discovery(hass, loaded):
    emit(loaded, 0x19, "temperature", group=1, value=86)
    emit(loaded, 0xD1, "electricity", value=1234)
    emit(
        loaded, 0xE4, "measurement", device=2, channel=3, units=4, multiplier=0, value=1
    )
    emit(loaded, 0xD5, "left_open", network=0, point=4)
    emit(loaded, 0xCB, "set_enable", group=2, value=5)
    await hass.async_block_till_done()
    temp = hass.states.get(entity_id(hass, loaded, "sensor", "25_group_1_temperature"))
    assert temp.state == "21.5"
    assert temp.attributes["unit_of_measurement"] == "°C"
    meter = hass.states.get(
        entity_id(hass, loaded, "sensor", "209_source_23_electricity")
    )
    assert meter.state == "1234"
    assert meter.attributes["state_class"] == "total_increasing"
    measurement = entity_id(
        hass, loaded, "binary_sensor", "228_device_2_channel_3_measurement"
    )
    assert hass.states.get(measurement).state == "on"
    contact = entity_id(hass, loaded, "binary_sensor", "213_network_0_point_4_open")
    assert hass.states.get(contact).state == "on"
    emit(loaded, 0xD5, "closed", network=0, point=4)
    assert hass.states.get(contact).state == "off"
    number = entity_id(hass, loaded, "number", "203_group_2_value")
    await call(hass, "number", "set_value", number, value=99)
    assert hass.states.get(number).state == "99"
    device = loaded.runtime_data.applications.devices[0xCB, "group_2"]
    with patch.object(
        loaded.runtime_data, "send_application", new=AsyncMock(side_effect=OSError)
    ):
        with pytest.raises(HomeAssistantError):
            await EnableNumber(loaded, device, "value").async_set_native_value(5)


async def test_every_trigger_is_emitted(hass, loaded):
    emit(loaded, 0xCA, "trigger", group=7, action=1)
    await hass.async_block_till_done()
    eid = entity_id(hass, loaded, "event", "202_group_7_events")
    assert hass.states.get(eid).attributes["event_type"] == "trigger"
    assert hass.states.get(eid).attributes["action"] == 1
    with patch(
        "custom_components.cbus_rs232.event.ApplicationEvents._trigger_event"
    ) as trigger:
        loaded.runtime_data._apply(
            ApplicationEvent(
                0xCA,
                23,
                (
                    ApplicationCommand("trigger", {"group": 7, "action": 2}),
                    ApplicationCommand("trigger", {"group": 7, "action": 3}),
                ),
            )
        )
        assert [args.args[1]["action"] for args in trigger.call_args_list] == [2, 3]
        loaded.runtime_data._notify()
        assert trigger.call_count == 2


async def test_climate_and_humidity_controls(hass, loaded):
    emit(
        loaded,
        0xAC,
        "set_hvac",
        group=1,
        zones=3,
        mode=0x41,
        type=3,
        level=5504,
        auxiliary=0x42,
    )
    emit(
        loaded,
        0xAC,
        "set_humidity",
        group=1,
        zones=3,
        mode=3,
        type=3,
        level=32768,
        auxiliary=0,
    )
    await hass.async_block_till_done()
    climate = entity_id(hass, loaded, "climate", "172_group_1_zone_1_climate")
    humidifier = entity_id(
        hass, loaded, "humidifier", "172_group_1_zone_1_humidity_control"
    )
    assert hass.states.get(climate).state == "heat"
    assert hass.states.get(climate).attributes["temperature"] == 21.5
    emit(loaded, 0xAC, "zone_temperature", group=1, zones=2, value=5120, status=0)
    emit(loaded, 0xAC, "zone_humidity", group=1, zones=2, value=32768, status=0)
    assert hass.states.get(climate).attributes["current_temperature"] == 20
    assert hass.states.get(climate).attributes["current_humidity"] == pytest.approx(
        50, abs=0.01
    )
    assert hass.states.get(humidifier).attributes["current_humidity"] == pytest.approx(
        50, abs=0.01
    )
    await call(hass, "climate", "set_temperature", climate, temperature=22)
    await call(hass, "climate", "set_hvac_mode", climate, hvac_mode="cool")
    devices = loaded.runtime_data.applications.devices
    config = devices[0xAC, "group_1_zone_1"].values["hvac"]
    assert config == dict(
        group=1, zones=2, mode=0x42, type=3, level=5632, auxiliary=0x42
    )
    assert devices[0xAC, "group_1_zone_0"].values["hvac"]["level"] == 5504
    await call(hass, "humidifier", "set_humidity", humidifier, humidity=60)
    assert devices[0xAC, "group_1_zone_1"].values["humidity"]["level"] == 39321
    await call(hass, "humidifier", "set_mode", humidifier, mode="dehumidify")
    assert hass.states.get(humidifier).attributes["mode"] == "dehumidify"
    await call(hass, "humidifier", "turn_off", humidifier)
    assert hass.states.get(humidifier).state == "off"
    await call(hass, "humidifier", "turn_on", humidifier)
    assert hass.states.get(humidifier).attributes["mode"] == "auto"
    emit(loaded, 0xAC, "hvac_off", group=1)
    assert hass.states.get(climate).state == "off"
    assert hass.states.get(humidifier).state == "off"


async def test_raw_plant_levels_are_not_temperature_or_humidity(hass, loaded):
    for name in ("set_hvac", "set_humidity"):
        emit(
            loaded, 0xAC, name, group=1, zones=1, mode=9, type=1, level=123, auxiliary=0
        )
    await hass.async_block_till_done()
    device = loaded.runtime_data.applications.devices[0xAC, "group_1_zone_0"]
    climate = ZoneClimate(loaded, device, "climate")
    humidifier = ZoneHumidifier(loaded, device, "humidity_control")
    assert climate.target_temperature is None
    assert not climate.supported_features
    assert humidifier.target_humidity is None
    with pytest.raises(HomeAssistantError):
        await climate.async_set_temperature(temperature=20)
    with pytest.raises(HomeAssistantError):
        await humidifier.async_set_humidity(50)


async def test_media_controls(hass, loaded):
    emit(loaded, 0xC0, "request_media", group=1)
    await hass.async_block_till_done()
    eid = entity_id(hass, loaded, "media_player", "192_group_1_player")
    assert hass.states.get(eid).state == "unknown"
    for name, state in (
        ("turn_on", "unknown"),
        ("media_play", "playing"),
        ("media_pause", "paused"),
        ("media_stop", "idle"),
        ("turn_off", "off"),
    ):
        await call(hass, "media_player", name, eid)
        assert hass.states.get(eid).state == state
    await call(hass, "media_player", "media_next_track", eid)
    await call(hass, "media_player", "media_previous_track", eid)
    await call(hass, "media_player", "shuffle_set", eid, shuffle=True)
    await call(hass, "media_player", "repeat_set", eid, repeat="all")
    await call(hass, "media_player", "turn_on", eid)
    emit(loaded, 0xC0, "track_name", group=1, header=0, text="536f6e67")
    emit(loaded, 0xC0, "selection_name", group=1, header=0, text="416c62756d")
    emit(loaded, 0xC0, "track", group=1, track=2)
    attrs = hass.states.get(eid).attributes
    assert attrs["media_title"] == "Song"
    assert attrs["media_album_name"] == "Album"
    assert attrs["media_track"] == 2
    assert attrs["shuffle"] is True
    assert attrs["repeat"] == "all"


async def test_security_commands_wait_for_panel_status(hass, loaded):
    emit(loaded, 0xD0, "request_security")
    await hass.async_block_till_done()
    eid = entity_id(hass, loaded, "alarm_control_panel", "208_source_23_alarm")
    assert hass.states.get(eid).state == "unknown"
    for name, state, fields in (
        ("disarmed", "disarmed", {}),
        ("armed", "armed_away", {"mode": 1}),
        ("armed", "armed_home", {"mode": 2}),
        ("entry_delay", "pending", {}),
        ("exit_delay", "arming", {}),
        ("alarm_on", "triggered", {}),
    ):
        emit(loaded, 0xD0, name, **fields)
        assert hass.states.get(eid).state == state
    for command in (
        "alarm_arm_away",
        "alarm_arm_home",
        "alarm_arm_night",
        "alarm_arm_vacation",
        "alarm_trigger",
    ):
        await call(hass, "alarm_control_panel", command, eid)
        assert hass.states.get(eid).state == "triggered"
    with pytest.raises(HomeAssistantError, match="no disarm command"):
        await call(hass, "alarm_control_panel", "alarm_disarm", eid)


async def test_named_actions(hass, loaded, pci, hass_owner_user):
    base = {"entry_id": loaded.entry_id}
    for app, command, fields, wire in (
        (0xCA, "trigger", {"group": 1, "action": 5}, "05CA00020105"),
        (0xD5, "lock_access", {"network": 0, "point": 2}, "05D5000A0002"),
        (0x71, "set_level", {"group": 3, "level": 128, "ramp": 0}, "057100020380"),
        (0x71, "terminate_ramp", {"group": 3}, "0571000903"),
        (
            0x71,
            "label",
            {"group": 3, "options": 0, "language": 1, "data": "4869"},
            "057100A50300014869",
        ),
    ):
        await hass.services.async_call(
            DOMAIN,
            "send_command",
            base | {"application": app, "command": command, "fields": fields},
            blocking=True,
        )
        assert pci.writes[-1].startswith(b"\\" + wire.encode())
    assert (
        loaded.runtime_data.applications.devices[0xCA, "group_1"].values["action"] == 5
    )
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            "send_command",
            base | {"application": 0, "command": "unknown"},
            blocking=True,
        )
    for entry_id_value in ("missing",):
        with pytest.raises(HomeAssistantError, match="loaded"):
            await hass.services.async_call(
                DOMAIN,
                "send_command",
                {"entry_id": entry_id_value, "application": 0xCA, "command": "trigger"},
                blocking=True,
            )
    user = await hass.auth.async_create_user("Non-admin", group_ids=[GROUP_ID_USER])
    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN,
            "send_command",
            base | {"application": 0xCA, "command": "trigger"},
            blocking=True,
            context=Context(user_id=user.id),
        )


@pytest.mark.parametrize(
    "name,fields",
    [
        ("unknown", {}),
        ("set_level", {"group": 1}),
        ("label", {"group": 1, "options": 0, "language": 1, "data": None}),
        ("label", {"group": 1, "options": 0, "language": 1, "data": "00" * 17}),
    ],
)
def test_bad_load_action(name, fields):
    with pytest.raises(ValueError):
        load_command(name, fields)


async def test_application_packets_and_disconnected_commands(client):
    payload = bytes.fromhex("0517CB00020163")
    client._line(checksum(payload).hex().encode())
    assert client.applications.devices[0xCB, "group_1"].values["value"] == 99
    client._apply(StatusReport(0xCB, (GroupStatus(1, Status.ON),)))
    assert 0xCB not in client.loads
    await client.disconnect()
    with pytest.raises(ConnectionError):
        await client.send_application(0xCA, "trigger", {"group": 1, "action": 5})
