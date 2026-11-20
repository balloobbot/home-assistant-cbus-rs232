"""Discovery and state shared by load-compatible applications."""

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo, Entity

from . import CBusConfigEntry
from .cbus.client import CBus, Group
from .cbus.protocol import RAMP_SECONDS, Status
from .const import DOMAIN


def discover_loads(entry, add, applications, entity_class):
    known = set()

    @callback
    def discover():
        entities = []
        for application, groups in entry.runtime_data.loads.items():
            if application in applications:
                for address, group in groups.items():
                    if (application, address) not in known:
                        known.add((application, address))
                        entities.append(entity_class(entry, group))
        if entities:
            add(entities)

    entry.async_on_unload(entry.runtime_data.subscribe(discover))
    discover()


class LoadEntity(Entity):
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, entry: CBusConfigEntry, group: Group) -> None:
        self._client: CBus = entry.runtime_data
        self._group = group
        self._attr_unique_id = f"{entry.entry_id}_{group.application}_{group.address}"
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
            await self._client.set_level(
                self._group.address, level, index, application=self._group.application
            )
        except (OSError, TimeoutError) as err:
            raise HomeAssistantError("C-Bus did not confirm the load command") from err
