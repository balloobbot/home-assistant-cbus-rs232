"""Security status and arming commands."""

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
)
from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntityFeature as Feature,
)
from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelState as State,
)
from homeassistant.exceptions import HomeAssistantError

from .entity import ApplicationEntity, discover_devices


async def async_setup_entry(hass, entry, async_add_entities):
    discover_devices(
        entry,
        async_add_entities,
        lambda device: (
            [CBusAlarm(entry, device, "alarm")] if device.application == 0xD0 else []
        ),
    )


class CBusAlarm(ApplicationEntity, AlarmControlPanelEntity):
    _attr_code_arm_required = False
    _attr_supported_features = (
        Feature.ARM_AWAY
        | Feature.ARM_HOME
        | Feature.ARM_NIGHT
        | Feature.ARM_VACATION
        | Feature.TRIGGER
    )

    @property
    def alarm_state(self):
        state = self.device.values
        if state.get("alarm"):
            return State.TRIGGERED
        if state.get("delay") == "entry_delay":
            return State.PENDING
        if state.get("delay") == "exit_delay":
            return State.ARMING
        return {0: State.DISARMED, 1: State.ARMED_AWAY, 2: State.ARMED_HOME}.get(
            state.get("mode")
        )

    async def async_alarm_arm_away(self, code=None):
        await self.send("arm", mode=1)

    async def async_alarm_arm_night(self, code=None):
        await self.send("arm", mode=2)

    async def async_alarm_arm_home(self, code=None):
        await self.send("arm", mode=3)

    async def async_alarm_arm_vacation(self, code=None):
        await self.send("arm", mode=4)

    async def async_alarm_trigger(self, code=None):
        await self.send("raise_alarm")

    async def async_alarm_disarm(self, code=None):
        raise HomeAssistantError(
            "C-Bus has no disarm command. Use the keypad action "
            "with your panel's documented key sequence."
        )
