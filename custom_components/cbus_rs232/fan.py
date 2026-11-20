"""C-Bus fan controls."""

from homeassistant.components.fan import FanEntity, FanEntityFeature

from .load import LoadEntity, discover_loads


async def async_setup_entry(hass, entry, async_add_entities):
    discover_loads(entry, async_add_entities, (0x70,), VentilationFan)


class VentilationFan(LoadEntity, FanEntity):
    _attr_supported_features = (
        FanEntityFeature.SET_SPEED
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )
    _attr_speed_count = 255

    @property
    def percentage(self) -> int | None:
        level = self._group.brightness
        return round(level * 100 / 255) if level is not None else None

    async def async_set_percentage(self, percentage: int) -> None:
        await self._set_level(round(percentage * 255 / 100), 0)

    async def async_turn_on(
        self, percentage: int | None = None, preset_mode: str | None = None, **kwargs
    ) -> None:
        await self.async_set_percentage(100 if percentage is None else percentage)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set_level(0, 0)
