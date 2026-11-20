"""Zone thermostats from the Air Conditioning application."""

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.exceptions import HomeAssistantError

from .entity import ApplicationEntity, discover_devices

MODES = (
    HVACMode.OFF,
    HVACMode.HEAT,
    HVACMode.COOL,
    HVACMode.HEAT_COOL,
    HVACMode.FAN_ONLY,
)


async def async_setup_entry(hass, entry, async_add_entities):
    discover_devices(
        entry,
        async_add_entities,
        lambda device: (
            [ZoneClimate(entry, device, "climate")]
            if device.application == 0xAC and "hvac" in device.values
            else []
        ),
    )


class ZoneClimate(ApplicationEntity, ClimateEntity):
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = list(MODES)
    _attr_min_temp = -40
    _attr_max_temp = 100
    _attr_target_temperature_step = 0.5

    @property
    def supported_features(self):
        return (
            ClimateEntityFeature.TARGET_TEMPERATURE
            if not self.device.values["hvac"]["mode"] & 8
            else ClimateEntityFeature(0)
        )

    @property
    def hvac_mode(self):
        if self.device.values.get("power") is False:
            return HVACMode.OFF
        return MODES[self.device.values["hvac"]["mode"] & 7]

    @property
    def target_temperature(self):
        config = self.device.values["hvac"]
        return None if config["mode"] & 8 else config["level"] / 256

    @property
    def current_temperature(self):
        reading = self.device.readings.get("temperature")
        return reading.value if reading else None

    @property
    def current_humidity(self):
        reading = self.device.readings.get("humidity")
        return reading.value if reading else None

    async def _set(self, **changes):
        values = (
            self.device.values["hvac"]
            | {"zones": 1 << self.device.address["zone"]}
            | changes
        )
        await self.send("set_hvac", **values)

    async def async_set_hvac_mode(self, hvac_mode):
        mode = (self.device.values["hvac"]["mode"] & ~7) | MODES.index(hvac_mode)
        await self._set(mode=mode)

    async def async_set_temperature(self, **kwargs):
        if self.device.values["hvac"]["mode"] & 8:
            raise HomeAssistantError(
                "This zone uses a raw plant level, not a temperature setpoint"
            )
        await self._set(level=round(kwargs[ATTR_TEMPERATURE] * 256))
