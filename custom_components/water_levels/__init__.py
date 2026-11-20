"""Water Levels: real-time river gauge data for Ireland, England and Scotland."""

from __future__ import annotations

from typing import Any

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_AVAILABLE_SENSORS, CONF_SOURCE, DOMAIN
from .coordinator import WaterlevelConfigEntry
from .providers import provider_for

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.NUMBER]


async def async_setup_entry(hass: HomeAssistant, entry: WaterlevelConfigEntry) -> bool:
    coordinator = provider_for(entry.data.get(CONF_SOURCE))(hass, entry)
    await coordinator.async_prepare()
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady:
        # Retry setup when the station can't be read at all. A station that has only
        # stopped reporting still sets up, so Data Stale and Last Reading can show it.
        if coordinator.last_reading_time is None:
            raise
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Reload for option or sensor changes, not when the threshold suggestions are stored
    reload_key = _reload_key(entry)

    async def _async_entry_updated(hass: HomeAssistant, entry: WaterlevelConfigEntry) -> None:
        if _reload_key(entry) != reload_key:
            await hass.config_entries.async_reload(entry.entry_id)

    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))
    entry.async_create_background_task(
        hass, coordinator.async_load_background(), f"{DOMAIN} history"
    )
    return True


def _reload_key(entry: WaterlevelConfigEntry) -> tuple[dict[str, Any], tuple[str, ...]]:
    return (dict(entry.options), tuple(entry.data.get(CONF_AVAILABLE_SENSORS, [])))


async def async_unload_entry(hass: HomeAssistant, entry: WaterlevelConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
