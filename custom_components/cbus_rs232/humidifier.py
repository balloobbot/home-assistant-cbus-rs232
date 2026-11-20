"""Zone humidity controls from the Air Conditioning application."""

from homeassistant.components.humidifier import (
    HumidifierEntity,
    HumidifierEntityFeature,
)
from homeassistant.exceptions import HomeAssistantError

from .entity import ApplicationEntity, discover_devices

MODES = ("off", "humidify", "dehumidify", "auto")


async def async_setup_entry(hass, entry, async_add_entities):
    discover_devices(
        entry,
        async_add_entities,
        lambda device: (
            [ZoneHumidifier(entry, device, "humidity_control")]
            if device.application == 0xAC and "humidity" in device.values
            else []
        ),
    )


class ZoneHumidifier(ApplicationEntity, HumidifierEntity):
    _attr_supported_features = HumidifierEntityFeature.MODES
    _attr_available_modes = list(MODES)
    _attr_min_humidity = 0
    _attr_max_humidity = 100

    @property
    def mode(self):
        return MODES[self.device.values["humidity"]["mode"] & 7]

    @property
    def is_on(self):
        return self.device.values.get("power") is not False and self.mode != "off"

    @property
    def target_humidity(self):
        config = self.device.values["humidity"]
        return None if config["mode"] & 8 else round(config["level"] * 100 / 65535)

    @property
    def current_humidity(self):
        reading = self.device.readings.get("humidity")
        return reading.value if reading else None

    async def _set(self, **changes):
        values = (
            self.device.values["humidity"]
            | {"zones": 1 << self.device.address["zone"]}
            | changes
        )
        await self.send("set_humidity", **values)

    async def async_set_mode(self, mode):
        await self._set(
            mode=(self.device.values["humidity"]["mode"] & ~7) | MODES.index(mode)
        )

    async def async_set_humidity(self, humidity):
        if self.device.values["humidity"]["mode"] & 8:
            raise HomeAssistantError("This zone uses a raw plant level")
        await self._set(level=round(humidity * 65535 / 100))

    async def async_turn_off(self, **kwargs):
        await self.async_set_mode("off")

    async def async_turn_on(self, **kwargs):
        await self.async_set_mode("auto")
