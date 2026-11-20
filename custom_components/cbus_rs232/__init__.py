"""C-Bus lighting through an RS-232 PCI."""

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_PORT, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.storage import Store

from .cbus.client import CBus, Group
from .const import CONF_APPLICATION, DOMAIN

type CBusConfigEntry = ConfigEntry[CBus]
PLATFORMS = [Platform.LIGHT]


async def async_setup_entry(hass: HomeAssistant, entry: CBusConfigEntry) -> None:
    client = CBus(entry.data[CONF_PORT], entry.data[CONF_APPLICATION])
    store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
    if saved := await store.async_load():
        for item in saved:
            client.groups[item["address"]] = Group(item["address"], label=item["label"])
    try:
        await client.connect()
    except (OSError, TimeoutError, ValueError) as err:
        raise ConfigEntryNotReady("Cannot connect to the C-Bus PCI") from err
    entry.runtime_data = client
    previous = None

    @callback
    def updated() -> None:
        nonlocal previous
        saved = [
            {"address": g.address, "label": g.label} for g in client.groups.values()
        ]
        if saved != previous:
            previous = saved
            store.async_delay_save(lambda: saved, 5)
        if not client.connected and entry.state is ConfigEntryState.LOADED:
            hass.config_entries.async_schedule_reload(entry.entry_id)

    entry.async_on_unload(client.subscribe(updated))
    updated()
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        await client.disconnect()
        raise


async def async_unload_entry(hass: HomeAssistant, entry: CBusConfigEntry) -> None:
    await hass.config_entries.async_unload_platforms_or_raise(entry, PLATFORMS)
    await entry.runtime_data.disconnect()


async def async_remove_entry(hass: HomeAssistant, entry: CBusConfigEntry) -> None:
    await Store(hass, 1, f"{DOMAIN}.{entry.entry_id}").async_remove()
