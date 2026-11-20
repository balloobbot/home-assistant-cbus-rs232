"""Security zones, access contacts, measurements, and fault reports."""

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CBusConfigEntry
from .cbus.state import ApplicationDevice
from .entity import ApplicationEntity, discover_devices


async def async_setup_entry(
    hass: HomeAssistant, entry: CBusConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    discover_devices(
        entry,
        async_add_entities,
        lambda device: [
            ApplicationBinarySensor(entry, device, name)
            for name, reading in device.readings.items()
            if reading.binary
        ],
    )


class ApplicationBinarySensor(ApplicationEntity, BinarySensorEntity):
    def __init__(
        self, entry: CBusConfigEntry, device: ApplicationDevice, name: str
    ) -> None:
        super().__init__(entry, device, name)
        self.reading = name

    @property
    def is_on(self) -> bool | None:
        return self.device.readings[self.reading].value
