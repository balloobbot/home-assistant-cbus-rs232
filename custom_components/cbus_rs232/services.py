"""Named application commands for automations."""

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_register_admin_service

from .cbus.applications import LOAD_APPLICATIONS
from .cbus.protocol import LightingCommand, byte, level_command
from .const import DOMAIN

SCHEMA = vol.Schema(
    {
        vol.Required("entry_id"): cv.string,
        vol.Required("application"): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=255)
        ),
        vol.Required("command"): cv.string,
        vol.Optional("fields", default=dict): dict,
    }
)


def register(hass):
    async def send_command(call):
        entry = hass.config_entries.async_get_entry(call.data["entry_id"])
        if (
            entry is None
            or entry.domain != DOMAIN
            or entry.state is not ConfigEntryState.LOADED
        ):
            raise HomeAssistantError("Select a loaded C-Bus config entry")
        client = entry.runtime_data
        app, name, fields = (
            call.data[key] for key in ("application", "command", "fields")
        )
        try:
            if app in LOAD_APPLICATIONS:
                await client.command(load_command(name, fields), application=app)
            else:
                await client.send_application(app, name, fields)
        except (OSError, TimeoutError, ValueError) as err:
            raise HomeAssistantError(str(err)) from err

    # The same action can arm security panels and change access-control settings.
    async_register_admin_service(
        hass, DOMAIN, "send_command", send_command, schema=SCHEMA
    )


def load_command(name, fields):
    required = {
        "set_level": {"group", "level", "ramp"},
        "terminate_ramp": {"group"},
        "label": {"group", "options", "language", "data"},
    }
    if name not in required or fields.keys() != required[name]:
        raise ValueError(
            "Use set_level(group, level, ramp), terminate_ramp(group), "
            "or label(group, options, language, data)"
        )
    group = byte(fields["group"], 254)
    if name == "set_level":
        return level_command(group, fields["level"], fields["ramp"])
    if name == "terminate_ramp":
        return LightingCommand(group, 9)
    if not isinstance(fields["data"], str):
        raise ValueError("Label data must be hexadecimal text")
    data = bytes([byte(fields["options"]), byte(fields["language"])]) + bytes.fromhex(
        fields["data"]
    )
    if len(data) > 18:
        raise ValueError("Label is too long")
    return LightingCommand(group, 0xA0 | (len(data) + 1), data)
