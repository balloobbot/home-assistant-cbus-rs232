"""Shared discovery for application entities."""

from collections.abc import Callable

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo, Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CBusConfigEntry
from .cbus.applications import APPLICATIONS
from .cbus.state import ApplicationDevice
from .const import DOMAIN


def discover_devices(
    entry: CBusConfigEntry,
    add: AddEntitiesCallback,
    factory: Callable[[ApplicationDevice], list[Entity]],
) -> None:
    known: set[str] = set()

    @callback
    def updated() -> None:
        entities = []
        for device in entry.runtime_data.applications.devices.values():
            for entity in factory(device):
                if entity.unique_id not in known:
                    known.add(entity.unique_id)
                    entities.append(entity)
        if entities:
            add(entities)

    entry.async_on_unload(entry.runtime_data.subscribe(updated))
    updated()


class ApplicationEntity(Entity):
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(
        self, entry: CBusConfigEntry, device: ApplicationDevice, suffix: str
    ) -> None:
        self.client = entry.runtime_data
        self.device = device
        self._attr_unique_id = (
            f"{entry.entry_id}_{device.application}_{device.key}_{suffix}"
        )
        self._attr_name = (
            f"{APPLICATIONS[device.application]} "
            f"{device.key.replace('_', ' ')} {suffix.replace('_', ' ')}"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="C-Bus",
            manufacturer="Clipsal",
            model="Serial PCI",
        )

    @property
    def available(self) -> bool:
        return self.client.connected

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.client.subscribe(self.async_write_ha_state))

    async def send(self, name: str, **values: int) -> None:
        try:
            await self.client.send_application(self.device.application, name, values)
        except (OSError, TimeoutError, ValueError) as err:
            raise HomeAssistantError("C-Bus command failed") from err
