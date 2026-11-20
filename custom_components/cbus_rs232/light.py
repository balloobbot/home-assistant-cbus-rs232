"""Discovered C-Bus lighting groups."""

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_TRANSITION,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CBusConfigEntry
from .cbus.client import CBus, Group
from .cbus.protocol import RAMP_SECONDS, Status
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: CBusConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    client = entry.runtime_data
    known: set[int] = set()

    @callback
    def discover() -> None:
        new = client.groups.keys() - known
        if new:
            known.update(new)
            async_add_entities(CBusLight(entry, client.groups[g]) for g in sorted(new))

    entry.async_on_unload(client.subscribe(discover))
    discover()


class CBusLight(LightEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_supported_features = LightEntityFeature.TRANSITION

    def __init__(self, entry: CBusConfigEntry, group: Group) -> None:
        self._client: CBus = entry.runtime_data
        self._group = group
        self._attr_unique_id = (
            f"{entry.entry_id}_{self._client.application}_{group.address}"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="C-Bus",
            manufacturer="Clipsal",
            model="Serial PCI",
        )

    @property
    def name(self) -> str:
        return self._group.label or f"Group {self._group.address}"

    @property
    def available(self) -> bool:
        return self._client.connected and self._group.status in (Status.ON, Status.OFF)

    @property
    def is_on(self) -> bool | None:
        if self._group.status not in (Status.ON, Status.OFF):
            return None
        return self._group.status == Status.ON

    @property
    def brightness(self) -> int | None:
        return self._group.brightness

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._client.subscribe(self.async_write_ha_state))

    async def _set_level(self, level: int, transition: float) -> None:
        current = self._group.brightness
        # C-Bus encodes full-scale ramp time, HA specifies time to the target.
        full_scale = transition
        if current is not None and current != level:
            full_scale = transition * 255 / abs(current - level)
        index = min(
            range(len(RAMP_SECONDS)), key=lambda i: abs(RAMP_SECONDS[i] - full_scale)
        )
        try:
            await self._client.set_level(self._group.address, level, index)
        except (OSError, TimeoutError) as err:
            raise HomeAssistantError(
                "C-Bus did not confirm the lighting command"
            ) from err

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set_level(
            kwargs.get(ATTR_BRIGHTNESS, 255), kwargs.get(ATTR_TRANSITION, 0)
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set_level(0, kwargs.get(ATTR_TRANSITION, 0))
