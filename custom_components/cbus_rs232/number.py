"""Enable Control network variables."""

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CBusConfigEntry
from .entity import ApplicationEntity, discover_devices


async def async_setup_entry(
    hass: HomeAssistant, entry: CBusConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    discover_devices(
        entry,
        async_add_entities,
        lambda device: (
            [EnableNumber(entry, device, "value")] if device.application == 0xCB else []
        ),
    )


class EnableNumber(ApplicationEntity, NumberEntity):
    _attr_native_min_value = 0
    _attr_native_max_value = 255
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    @property
    def native_value(self) -> float | None:
        return self.device.values.get("value")

    async def async_set_native_value(self, value: float) -> None:
        await self.send(
            "set_enable", group=self.device.address["group"], value=int(value)
        )
