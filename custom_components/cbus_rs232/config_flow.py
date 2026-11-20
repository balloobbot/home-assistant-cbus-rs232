"""Select a PCI serial port and lighting application."""

from typing import Any

import probatio as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PORT
from homeassistant.helpers.selector import SerialPortSelector

from .cbus.client import CBus
from .const import CONF_APPLICATION, DOMAIN


class CBusConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            self._async_abort_entries_match({CONF_PORT: user_input[CONF_PORT]})
            client = CBus(user_input[CONF_PORT], user_input[CONF_APPLICATION])
            try:
                await client.connect()
            except OSError, TimeoutError, ValueError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(title="C-Bus", data=user_input)
            finally:
                await client.disconnect()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PORT): SerialPortSelector(),
                    vol.Required(CONF_APPLICATION, default=56): vol.All(
                        vol.Coerce(int), vol.Range(min=48, max=95)
                    ),
                }
            ),
            errors=errors,
        )
