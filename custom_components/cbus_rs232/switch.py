"""C-Bus switch controls."""

from homeassistant.components.switch import SwitchEntity

from .load import LoadEntity, discover_loads


async def async_setup_entry(hass, entry, async_add_entities):
    discover_loads(entry, async_add_entities, (0x71, 0x72, 0x73, 0x74), LoadSwitch)


class LoadSwitch(LoadEntity, SwitchEntity):
    _attr_supported_features = 0

    async def async_turn_on(self, **kwargs) -> None:
        await self._set_level(255, 0)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set_level(0, 0)
