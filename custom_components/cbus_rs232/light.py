"""Lighting applications 0x30 through 0x5F."""

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_TRANSITION,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)

from .load import LoadEntity, discover_loads


async def async_setup_entry(hass, entry, async_add_entities):
    discover_loads(entry, async_add_entities, range(0x30, 0x60), CBusLight)


class CBusLight(LoadEntity, LightEntity):
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_supported_features = LightEntityFeature.TRANSITION

    @property
    def brightness(self) -> int | None:
        return self._group.brightness

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set_level(
            kwargs.get(ATTR_BRIGHTNESS, 255), kwargs.get(ATTR_TRANSITION, 0)
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set_level(0, kwargs.get(ATTR_TRANSITION, 0))
