"""Media Transport Control groups."""

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerState,
)
from homeassistant.components.media_player import (
    MediaPlayerEntityFeature as Feature,
)

from .entity import ApplicationEntity, discover_devices


async def async_setup_entry(hass, entry, async_add_entities):
    discover_devices(
        entry,
        async_add_entities,
        lambda device: (
            [CBusMediaPlayer(entry, device, "player")]
            if device.application == 0xC0
            else []
        ),
    )


class CBusMediaPlayer(ApplicationEntity, MediaPlayerEntity):
    _attr_supported_features = (
        Feature.PLAY
        | Feature.PAUSE
        | Feature.STOP
        | Feature.NEXT_TRACK
        | Feature.PREVIOUS_TRACK
        | Feature.TURN_ON
        | Feature.TURN_OFF
        | Feature.SHUFFLE_SET
        | Feature.REPEAT_SET
    )

    @property
    def state(self):
        if self.device.values.get("power") is False:
            return MediaPlayerState.OFF
        return self.device.values.get("playback")

    @property
    def media_title(self):
        return self.device.values.get("track_name")

    @property
    def media_album_name(self):
        return self.device.values.get("selection_name")

    @property
    def media_track(self):
        return self.device.values.get("track")

    @property
    def shuffle(self):
        return self.device.values.get("shuffle")

    @property
    def repeat(self):
        return self.device.values.get("repeat")

    async def _command(self, name, **values):
        await self.send(name, group=self.device.address["group"], **values)

    async def async_media_play(self):
        await self._command("play")

    async def async_media_pause(self):
        await self._command("pause", operation=0)

    async def async_media_stop(self):
        await self._command("stop")

    async def async_media_next_track(self):
        await self._command("step_track", operation=1)

    async def async_media_previous_track(self):
        await self._command("step_track", operation=0)

    async def async_turn_on(self):
        await self._command("power", state=255)

    async def async_turn_off(self):
        await self._command("power", state=0)

    async def async_set_shuffle(self, shuffle):
        await self._command("shuffle", state=255 if shuffle else 0)

    async def async_set_repeat(self, repeat):
        await self._command("repeat", type={"off": 0, "one": 1, "all": 255}[repeat])
