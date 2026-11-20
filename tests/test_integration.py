"""Exercise the integration through Home Assistant's config and service APIs."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.cbus_rs232 import async_remove_entry, async_setup_entry
from custom_components.cbus_rs232.cbus.client import CBus, Group
from custom_components.cbus_rs232.cbus.protocol import (
    GroupStatus,
    LightingCommand,
    LightingEvent,
    Status,
    StatusReport,
)
from custom_components.cbus_rs232.const import DOMAIN
from custom_components.cbus_rs232.light import CBusLight

from .conftest import PCI


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, data={"port": "esphome://proxy/uart0", "application": 56}
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture(autouse=True)
def dependencies():
    with (
        patch("homeassistant.setup.async_process_deps_reqs", return_value=None),
        patch(
            "homeassistant.config_entries.async_process_deps_reqs", return_value=None
        ),
    ):
        yield


async def test_config_flow(hass: HomeAssistant, pci: PCI) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["data_schema"].schema["port"].selector_type == "serial_port"
    with patch("custom_components.cbus_rs232.async_setup_entry", return_value=None):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"port": "esphome://proxy/uart0", "application": 56}
        )
        await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert pci.closed


@pytest.mark.parametrize("error", [OSError, TimeoutError, ValueError])
async def test_config_failure(hass: HomeAssistant, error: type[Exception]) -> None:
    with (
        patch(
            "custom_components.cbus_rs232.config_flow.CBus.connect", side_effect=error
        ),
        patch(
            "custom_components.cbus_rs232.config_flow.CBus.disconnect", new=AsyncMock()
        ) as close,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}, data={"port": "bad", "application": 56}
        )
    assert result["errors"] == {"base": "cannot_connect"}
    close.assert_awaited_once()


async def test_duplicate_port(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}, data=entry.data
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_setup_failure(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    with patch("serialx.open_serial_connection", side_effect=OSError):
        assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_discovery_and_control(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    pci: PCI,
    entity_registry: er.EntityRegistry,
) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    client = entry.runtime_data
    client._apply(
        StatusReport(56, (GroupStatus(8, Status.ON, 87), GroupStatus(9, Status.OFF, 0)))
    )
    await hass.async_block_till_done()
    entity_id = entity_registry.async_get_entity_id(
        "light", DOMAIN, f"{entry.entry_id}_56_8"
    )
    assert hass.states.get(entity_id).state == "on"
    assert hass.states.get(entity_id).attributes["brightness"] == 87
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": entity_id, "brightness": 128}, blocking=True
    )
    assert client.groups[8].level == 128
    await hass.services.async_call(
        "light", "turn_off", {"entity_id": entity_id}, blocking=True
    )
    assert hass.states.get(entity_id).state == "off"
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": entity_id}, blocking=True
    )
    assert client.groups[8].level == 255
    client._apply(StatusReport(56, (GroupStatus(8, Status.ERROR),)))
    assert hass.states.get(entity_id).state == "unavailable"
    client._apply(LightingEvent(56, (LightingCommand(8, 0xAA, b"\x00\x01Kitchen"),)))
    await hass.async_block_till_done()
    assert len(er.async_entries_for_config_entry(entity_registry, entry.entry_id)) == 2
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert pci.closed
    assert client._listeners == []


async def test_restore_groups(
    hass: HomeAssistant, entry: MockConfigEntry, pci: PCI, hass_storage: dict
) -> None:
    hass_storage[f"{DOMAIN}.{entry.entry_id}"] = {
        "version": 1,
        "data": [{"address": 8, "label": "Kitchen"}],
    }
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    client = entry.runtime_data
    assert client.groups[8].label == "Kitchen"
    assert client.groups[8].status == Status.ABSENT
    await hass.config_entries.async_unload(entry.entry_id)
    await async_remove_entry(hass, entry)


async def test_disconnect_reloads(
    hass: HomeAssistant, entry: MockConfigEntry, pci: PCI
) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    with patch.object(hass.config_entries, "async_schedule_reload") as reload:
        entry.runtime_data._lost("unplugged")
        reload.assert_called_once_with(entry.entry_id)
    await hass.config_entries.async_unload(entry.entry_id)


async def test_platform_setup_error_closes(
    hass: HomeAssistant, entry: MockConfigEntry, pci: PCI
) -> None:
    with (
        patch.object(
            hass.config_entries, "async_forward_entry_setups", side_effect=RuntimeError
        ),
        pytest.raises(RuntimeError),
    ):
        await async_setup_entry(hass, entry)
    assert pci.closed


async def test_light_transitions_and_errors(entry: MockConfigEntry) -> None:
    client = CBus("test")
    entry.runtime_data = client
    group = Group(8, Status.ON, 128)
    light = CBusLight(entry, group)
    assert light.name == "Group 8"
    group.label = "Kitchen"
    assert light.name == "Kitchen"
    with patch.object(client, "set_level", new=AsyncMock()) as set_level:
        await light.async_turn_on(brightness=255, transition=2)
        set_level.assert_awaited_once_with(8, 255, 1)
        group.level = None
        await light.async_turn_off(transition=4)
        set_level.assert_awaited_with(8, 0, 1)
        group.level = 0
        await light.async_turn_off()
        set_level.assert_awaited_with(8, 0, 0)
    group.status = Status.ERROR
    assert light.is_on is None
    with pytest.raises(HomeAssistantError):
        await light.async_turn_on()
