"""Metering, measurement, temperature, and application status sensors."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CBusConfigEntry
from .cbus.state import ApplicationDevice
from .entity import ApplicationEntity, discover_devices

UNIT_CLASSES = {
    "°C": SensorDeviceClass.TEMPERATURE,
    "A": SensorDeviceClass.CURRENT,
    "Hz": SensorDeviceClass.FREQUENCY,
    "kg": SensorDeviceClass.WEIGHT,
    "L": SensorDeviceClass.VOLUME,
    "m³": SensorDeviceClass.VOLUME,
    "lx": SensorDeviceClass.ILLUMINANCE,
    "m": SensorDeviceClass.DISTANCE,
    "m/s": SensorDeviceClass.SPEED,
    "Pa": SensorDeviceClass.PRESSURE,
    "V": SensorDeviceClass.VOLTAGE,
    "Wh": SensorDeviceClass.ENERGY,
    "kWh": SensorDeviceClass.ENERGY,
    "MJ": SensorDeviceClass.ENERGY,
    "W": SensorDeviceClass.POWER,
}


async def async_setup_entry(
    hass: HomeAssistant, entry: CBusConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    discover_devices(
        entry,
        async_add_entities,
        lambda device: [
            ApplicationSensor(entry, device, name)
            for name, reading in device.readings.items()
            if not reading.binary
        ],
    )


class ApplicationSensor(ApplicationEntity, SensorEntity):
    def __init__(
        self, entry: CBusConfigEntry, device: ApplicationDevice, name: str
    ) -> None:
        super().__init__(entry, device, name)
        self.reading = name

    @property
    def native_value(self):
        return self.device.readings[self.reading].value

    @property
    def native_unit_of_measurement(self) -> str | None:
        return self.device.readings[self.reading].unit

    @property
    def device_class(self):
        return UNIT_CLASSES.get(self.native_unit_of_measurement)

    @property
    def state_class(self) -> SensorStateClass | None:
        return (
            SensorStateClass.TOTAL_INCREASING
            if self.device.readings[self.reading].total
            else None
        )
