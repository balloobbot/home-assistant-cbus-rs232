"""Application events, including triggers and protocol-specific notifications."""

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CBusConfigEntry
from .cbus.applications import DEFINITIONS
from .cbus.state import ApplicationDevice
from .entity import ApplicationEntity, discover_devices


async def async_setup_entry(
    hass: HomeAssistant, entry: CBusConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    discover_devices(
        entry, async_add_entities, lambda device: [ApplicationEvents(entry, device)]
    )


class ApplicationEvents(ApplicationEntity, EventEntity):
    def __init__(self, entry: CBusConfigEntry, device: ApplicationDevice) -> None:
        super().__init__(entry, device, "events")
        self._attr_event_types = [d.name for d in DEFINITIONS[device.application]]
        self._sequence = 0

    @callback
    def _updated(self) -> None:
        for sequence, command in self.device.events:
            if sequence > self._sequence:
                self._sequence = sequence
                self._trigger_event(command.name, command.values)
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.client.subscribe(self._updated))
        self._updated()
