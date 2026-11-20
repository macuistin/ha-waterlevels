"""Config flow for Waterlevel.ie — browse by river or enter a station number."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
import logging
import re
from typing import Any

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_LOCATION, CONF_RADIUS
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    LocationSelector,
    LocationSelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.util.location import distance

# Home Assistant 2026.10 replaced voluptuous with probatio, which has the same API.
try:
    import probatio as vol
except ImportError:  # pragma: no cover - Home Assistant before 2026.10
    import voluptuous as vol  # type: ignore[no-redef]

from .api import StationNotFound, WaterlevelApi, WaterlevelError
from .const import (
    CONF_ALERT_STAGE,
    CONF_AVAILABLE_SENSORS,
    CONF_FLOW_MEASURE,
    CONF_FLOW_TS,
    CONF_LATITUDE,
    CONF_LEVEL_MEASURE,
    CONF_LEVEL_TS,
    CONF_LONGITUDE,
    CONF_REDETECT,
    CONF_RLOI_ID,
    CONF_SCAN_INTERVAL,
    CONF_SOURCE,
    CONF_STALE_HOURS,
    CONF_STATION,
    CONF_STATION_INFO,
    CONF_STATION_NAME,
    DEFAULT_ALERT_STAGE,
    DEFAULT_STALE_HOURS,
    DOMAIN,
    FLOOD_STAGES,
    GROUP_LIST_URL,
    SOURCE_EA,
    SOURCE_OPW,
    SOURCE_SEPA,
    WATER_LEVEL,
)
from .coordinator import StationCoordinator
from .ea_api import EnvironmentAgencyApi
from .providers import provider_for
from .sepa_api import SepaApi

_LOGGER = logging.getLogger(__name__)
CONF_GROUP = "group"
DEFAULT_NEARBY_RADIUS = 15000  # metres
# The Environment Agency search is limited to this distance, in km
MAX_EA_DISTANCE_KM = 100


def normalize_station(raw: str) -> str | None:
    """Turn user input into a 5-digit station number, or None if it isn't one.

    Accepts a plain number ("14029", "0000014029") or a pasted station URL
    ("https://waterlevel.ie/0000014029/").
    """
    raw = raw.strip()
    if m := re.search(r"\d{10}", raw):
        digits = m.group(0)
    elif raw.isdigit():
        digits = raw
    else:
        return None
    if int(digits) == 0:
        return None
    return str(int(digits)).zfill(5)


@dataclass(frozen=True)
class Found:
    """A station from a country's list, and how far it is from a search location."""

    country: str
    ref: str
    name: str
    latitude: float | None
    longitude: float | None
    river: str = ""
    # The Environment Agency or SEPA station as their API gave it; empty for Ireland
    data: dict[str, Any] = field(default_factory=dict)
    distance: float = 0.0


# English names of the countries, for the list that mixes them
COUNTRY_NAMES = {SOURCE_OPW: "Ireland", SOURCE_EA: "England", SOURCE_SEPA: "Scotland"}


def _unique_id(country: str, ref: str) -> str:
    """A station's config entry unique id: Irish ones have no country in them."""
    return f"{DOMAIN}_{ref}" if country == SOURCE_OPW else f"{DOMAIN}_{country}_{ref}"


def _found_nearby(
    location: dict[str, Any], configured: set[str | None], stations: Iterable[Found]
) -> list[Found]:
    """The stations inside the search radius that aren't added yet, closest first."""
    nearby = []
    for station in stations:
        if _unique_id(station.country, station.ref) in configured:
            continue
        dist = distance(
            location[CONF_LATITUDE], location[CONF_LONGITUDE], station.latitude, station.longitude
        )
        if dist is not None and dist <= location[CONF_RADIUS]:
            nearby.append(replace(station, distance=dist))
    return sorted(nearby, key=lambda found: found.distance)


async def _search_ireland(
    hass: HomeAssistant, location: dict[str, Any], configured: set[str | None]
) -> list[Found]:
    """Irish stations near a location. Raises WaterlevelError if waterlevel.ie is down."""
    stations = await WaterlevelApi(async_get_clientsession(hass)).stations()
    return _found_nearby(
        location,
        configured,
        (Found(SOURCE_OPW, sid, name, lat, lon) for sid, (name, lat, lon) in stations.items()),
    )


async def _search_england(
    hass: HomeAssistant, location: dict[str, Any], configured: set[str | None]
) -> list[Found]:
    """English stations near a location. Raises WaterlevelError if the API is down."""
    stations = await EnvironmentAgencyApi(async_get_clientsession(hass)).stations_near(
        location[CONF_LATITUDE],
        location[CONF_LONGITUDE],
        min(location[CONF_RADIUS] / 1000, MAX_EA_DISTANCE_KM),
    )
    return _found_nearby(location, configured, (_found(SOURCE_EA, item) for item in stations))


async def _search_scotland(
    hass: HomeAssistant, location: dict[str, Any], configured: set[str | None]
) -> list[Found]:
    """Scottish stations near a location. Raises WaterlevelError if SEPA is down."""
    stations = await SepaApi(async_get_clientsession(hass)).stations()
    return _found_nearby(location, configured, (_found(SOURCE_SEPA, item) for item in stations))


def _found(country: str, station: dict[str, Any]) -> Found:
    """A station from the Environment Agency or SEPA, as a Found."""
    return Found(
        country,
        station["station"],
        station["name"],
        station["latitude"],
        station["longitude"],
        station["river"],
        station,
    )


def _label_with_country(found: Found) -> str:
    """A station's list label with its country, for lists that mix countries."""
    return f"{_station_label(found)}, {COUNTRY_NAMES[found.country]}"


def _station_label(found: Found) -> str:
    """How a station reads in a list: name, river, number and distance."""
    river = f", {found.river}" if found.river else ""
    return f"{found.name}{river} ({found.ref}), {found.distance / 1000:.1f} km"


async def _detect_station(
    api: WaterlevelApi, station: str, name_hint: str | None = None
) -> dict[str, Any]:
    """Probe a station and build its config entry data.

    name_hint: preferred display name (e.g. from the river group picker).
    Falls back to the station page title, then to 'Station {station}'.
    """
    page_name, available = await api.detect_station(station)
    result: dict[str, Any] = {
        CONF_STATION: station,
        CONF_STATION_NAME: name_hint or page_name or f"Station {station}",
        CONF_AVAILABLE_SENSORS: available,
    }
    if coords := await api.station_coords(station):
        result[CONF_LATITUDE], result[CONF_LONGITUDE] = coords
    return result


def _england_entry_data(station: dict[str, Any]) -> dict[str, Any]:
    """The config entry data for an Environment Agency station from EnvironmentAgencyApi."""
    available = [WATER_LEVEL] + (["discharge"] if station["flow_measure"] else [])
    details = {"status": "active"}
    if station["catchment"]:
        details["catchment"] = station["catchment"]
    return {
        CONF_SOURCE: SOURCE_EA,
        CONF_STATION: station["station"],
        CONF_STATION_NAME: station["name"],
        CONF_AVAILABLE_SENSORS: available,
        CONF_LATITUDE: station["latitude"],
        CONF_LONGITUDE: station["longitude"],
        CONF_LEVEL_MEASURE: station["level_measure"],
        CONF_FLOW_MEASURE: station["flow_measure"],
        CONF_RLOI_ID: station["rloi_id"],
        # The stage scale becomes the default flood thresholds (see thresholds.py)
        CONF_STATION_INFO: {"details": details, "levels": station["stage_scale"]},
    }


def _scotland_entry_data(
    station: dict[str, Any], level_ts: str, flow_ts: str | None
) -> dict[str, Any]:
    """The config entry data for a SEPA station and its time series."""
    return {
        CONF_SOURCE: SOURCE_SEPA,
        CONF_STATION: station["station"],
        CONF_STATION_NAME: station["name"],
        CONF_AVAILABLE_SENSORS: [WATER_LEVEL] + (["discharge"] if flow_ts else []),
        CONF_LATITUDE: station["latitude"],
        CONF_LONGITUDE: station["longitude"],
        CONF_LEVEL_TS: level_ts,
        CONF_FLOW_TS: flow_ts,
        CONF_STATION_INFO: {"details": {"river": station["river"]} if station["river"] else {}},
    }


class WaterlevelConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow: choose how to find a station, then add it."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> WaterlevelOptionsFlow:
        return WaterlevelOptionsFlow()

    def __init__(self) -> None:
        self._groups: dict[str, str] = {}
        self._selected_group: str | None = None
        self._stations: dict[str, str] = {}
        self._found: dict[str, Found] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask which country the station is in."""
        return self.async_show_menu(
            step_id="user", menu_options=["ireland", "england", "scotland", "anywhere"]
        )

    async def async_step_ireland(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask how to find an Irish station: nearby, by river or by station number.

        England and Scotland can only search near a location, so they go straight to it.
        """
        return self.async_show_menu(
            step_id="ireland", menu_options=["nearby", "river", "station_number"]
        )

    def _location_form(
        self, step_id: str, user_input: dict[str, Any] | None, errors: dict[str, str]
    ) -> ConfigFlowResult:
        """The location and radius form every search step shows (the home location by default)."""
        default = (user_input or {}).get(CONF_LOCATION) or {
            CONF_LATITUDE: self.hass.config.latitude,
            CONF_LONGITUDE: self.hass.config.longitude,
            CONF_RADIUS: DEFAULT_NEARBY_RADIUS,
        }
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_LOCATION, default=default): LocationSelector(
                        LocationSelectorConfig(radius=True)
                    ),
                }
            ),
            errors=errors,
        )

    def _station_form(
        self,
        step_id: str,
        errors: dict[str, str],
        label: Callable[[Found], str] = _station_label,
    ) -> ConfigFlowResult:
        """The list of stations found by a search, closest first, with how far each is."""
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_STATION): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(value=key, label=label(found))
                                for key, found in self._found.items()
                            ],
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_nearby(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Pick a location and radius (the home location by default)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                found = await _search_ireland(
                    self.hass, user_input[CONF_LOCATION], self._async_current_ids()
                )
            except WaterlevelError as err:
                _LOGGER.warning("Failed to fetch the station list: %s", err)
                errors["base"] = "cannot_connect"
            else:
                if found:
                    self._found = {item.ref: item for item in found}
                    return await self.async_step_nearby_station()
                errors["base"] = "no_nearby_stations"
        return self._location_form("nearby", user_input, errors)

    async def async_step_nearby_station(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick one of the stations found nearby, closest first."""
        errors: dict[str, str] = {}
        if user_input is not None:
            station = user_input[CONF_STATION]
            result = await self._async_add_station(
                station, errors, name_hint=self._found[station].name
            )
            if result is not None:
                return result
        return self._station_form("nearby_station", errors)

    async def async_step_england(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a location and radius to look for Environment Agency stations in England."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                found = await _search_england(
                    self.hass, user_input[CONF_LOCATION], self._async_current_ids()
                )
            except WaterlevelError as err:
                _LOGGER.warning("Failed to fetch the Environment Agency station list: %s", err)
                errors["base"] = "england_unreachable"
            else:
                if found:
                    self._found = {item.ref: item for item in found}
                    return await self.async_step_england_station()
                errors["base"] = "no_nearby_stations"
        return self._location_form("england", user_input, errors)

    async def async_step_england_station(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick one of the Environment Agency stations found nearby, closest first."""
        errors: dict[str, str] = {}
        if user_input is not None:
            result = await self._async_add_england(user_input[CONF_STATION], errors)
            if result is not None:
                return result
        return self._station_form("england_station", errors)

    async def async_step_scotland(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a location and radius to look for SEPA stations in Scotland."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                found = await _search_scotland(
                    self.hass, user_input[CONF_LOCATION], self._async_current_ids()
                )
            except WaterlevelError as err:
                _LOGGER.warning("Failed to fetch the SEPA station list: %s", err)
                errors["base"] = "scotland_unreachable"
            else:
                if found:
                    self._found = {item.ref: item for item in found}
                    return await self.async_step_scotland_station()
                errors["base"] = "no_nearby_stations"
        return self._location_form("scotland", user_input, errors)

    async def async_step_scotland_station(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick one of the SEPA stations found nearby, closest first."""
        errors: dict[str, str] = {}
        if user_input is not None:
            ref = user_input[CONF_STATION]
            result = await self._async_add_scotland(self._found[ref], errors)
            if result is not None:
                return result
        return self._station_form("scotland_station", errors)

    async def async_step_anywhere(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Search all three countries around a location, so a border isn't a problem."""
        errors: dict[str, str] = {}
        if user_input is not None:
            found = await self._async_search_everywhere(user_input[CONF_LOCATION])
            if found is None:
                errors["base"] = "anywhere_unreachable"
            elif found:
                self._found = {f"{item.country}:{item.ref}": item for item in found}
                return await self.async_step_anywhere_station()
            else:
                errors["base"] = "no_nearby_stations"
        return self._location_form("anywhere", user_input, errors)

    async def _async_search_everywhere(self, location: dict[str, Any]) -> list[Found] | None:
        """Every country's stations near a location, closest first.

        A country that is down is skipped and logged. None means every country failed.
        For now all three are searched whatever the radius. Searching only the countries the
        radius reaches would save two requests, and is a later optimisation.
        """
        configured = self._async_current_ids()
        results = await asyncio.gather(
            _search_ireland(self.hass, location, configured),
            _search_england(self.hass, location, configured),
            _search_scotland(self.hass, location, configured),
            return_exceptions=True,
        )
        found: list[Found] = []
        failed = 0
        for country, result in zip(COUNTRY_NAMES, results, strict=True):
            if isinstance(result, WaterlevelError):
                _LOGGER.warning("Failed to search %s: %s", COUNTRY_NAMES[country], result)
                failed += 1
            elif isinstance(result, BaseException):
                raise result
            else:
                found.extend(result)
        if failed == len(results):
            return None
        return sorted(found, key=lambda item: item.distance)

    async def async_step_anywhere_station(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a station from any country, closest first."""
        errors: dict[str, str] = {}
        if user_input is not None:
            found = self._found[user_input[CONF_STATION]]
            if found.country == SOURCE_EA:
                result = await self._async_add_england(found.ref, errors)
            elif found.country == SOURCE_SEPA:
                result = await self._async_add_scotland(found, errors)
            else:
                result = await self._async_add_station(found.ref, errors, name_hint=found.name)
            if result is not None:
                return result
        return self._station_form("anywhere_station", errors, _label_with_country)

    async def _async_add_england(self, ref: str, errors: dict[str, str]) -> ConfigFlowResult | None:
        """Read the English station and create its entry; on failure fill errors."""
        await self.async_set_unique_id(_unique_id(SOURCE_EA, ref))
        self._abort_if_unique_id_configured()
        try:
            # The station list leaves out some measures, so read the station itself
            api = EnvironmentAgencyApi(async_get_clientsession(self.hass))
            station = await api.station(ref)
            # A station can stay listed as active long after its gauge stops reporting
            reporting = station["level_measure"] in await api.latest()
        except StationNotFound:
            errors[CONF_STATION] = "england_station_not_found"
        except WaterlevelError:
            errors["base"] = "england_unreachable"
        else:
            if not reporting:
                errors[CONF_STATION] = "england_station_silent"
                return None
            return self.async_create_entry(title=station["name"], data=_england_entry_data(station))
        return None

    async def _async_add_scotland(
        self, found: Found, errors: dict[str, str]
    ) -> ConfigFlowResult | None:
        """Find the Scottish station's time series and create its entry; on failure fill errors."""
        await self.async_set_unique_id(_unique_id(SOURCE_SEPA, found.ref))
        self._abort_if_unique_id_configured()
        try:
            level_ts, flow_ts = await SepaApi(async_get_clientsession(self.hass)).station_series(
                found.ref
            )
        except StationNotFound:
            errors[CONF_STATION] = "scotland_station_not_found"
        except WaterlevelError:
            errors["base"] = "scotland_unreachable"
        else:
            return self.async_create_entry(
                title=found.name, data=_scotland_entry_data(found.data, level_ts, flow_ts)
            )
        return None

    async def async_step_river(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Pick a river, then load its stations."""
        errors: dict[str, str] = {}
        api = WaterlevelApi(async_get_clientsession(self.hass))
        if user_input is not None:
            group_id = user_input[CONF_GROUP]
            try:
                stations = await api.group_stations(group_id)
            except WaterlevelError as err:
                _LOGGER.warning("Failed to fetch stations for river %s: %s", group_id, err)
                errors["base"] = "cannot_connect"
            else:
                configured = self._async_current_ids()
                stations = {
                    sid: name
                    for sid, name in stations.items()
                    if f"{DOMAIN}_{sid}" not in configured
                }
                if stations:
                    self._selected_group = group_id
                    self._stations = stations
                    return await self.async_step_select_station()
                errors[CONF_GROUP] = "no_stations"
        if not self._groups:
            try:
                self._groups = await api.groups()
            except WaterlevelError as err:
                _LOGGER.warning("Failed to fetch river list: %s", err)
            if not self._groups:
                # Nothing to pick from; the user can still type a station number.
                return self.async_abort(reason="cannot_load_rivers")
        return self.async_show_form(
            step_id="river",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_GROUP): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(value=gid, label=name)
                                for gid, name in self._groups.items()
                            ],
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_select_station(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a station on the chosen river."""
        errors: dict[str, str] = {}
        if user_input is not None:
            station = user_input[CONF_STATION]
            result = await self._async_add_station(
                station, errors, name_hint=self._stations.get(station)
            )
            if result is not None:
                return result
        return self.async_show_form(
            step_id="select_station",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_STATION): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(value=sid, label=f"{name} ({sid})")
                                for sid, name in self._stations.items()
                            ],
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders={
                "river_name": self._groups.get(self._selected_group or "", "selected river"),
            },
        )

    async def async_step_station_number(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Enter a station number (or paste a station URL) directly."""
        errors: dict[str, str] = {}
        if user_input is not None:
            station = normalize_station(user_input[CONF_STATION])
            if station is None:
                errors[CONF_STATION] = "invalid_station"
            else:
                result = await self._async_add_station(station, errors)
                if result is not None:
                    return result
        return self.async_show_form(
            step_id="station_number",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_STATION): TextSelector(
                            TextSelectorConfig(
                                type=TextSelectorType.TEXT,
                            )
                        ),
                    }
                ),
                user_input,
            ),
            errors=errors,
            description_placeholders={"stations_url": GROUP_LIST_URL, "example": "14029"},
        )

    async def _async_add_station(
        self, station: str, errors: dict[str, str], name_hint: str | None = None
    ) -> ConfigFlowResult | None:
        """Probe the station and create the entry; on failure fill errors and return None."""
        await self.async_set_unique_id(f"{DOMAIN}_{station}")
        self._abort_if_unique_id_configured()
        try:
            info = await _detect_station(
                WaterlevelApi(async_get_clientsession(self.hass)), station, name_hint=name_hint
            )
        except StationNotFound:
            errors[CONF_STATION] = "station_not_found"
        except WaterlevelError:
            errors["base"] = "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected error adding station %s", station)
            errors["base"] = "unknown"
        else:
            return self.async_create_entry(title=info[CONF_STATION_NAME], data=info)
        return None


class WaterlevelOptionsFlow(config_entries.OptionsFlow):
    """Change how often a station updates and when it counts as stale."""

    @property
    def _provider(self) -> type[StationCoordinator]:
        """The entry's source, which says its own update intervals and options."""
        return provider_for(self.config_entry.data.get(CONF_SOURCE))

    @property
    def _default_interval(self) -> int:
        return self._provider.default_scan_interval

    @property
    def _min_interval(self) -> int:
        return self._provider.min_scan_interval

    @property
    def _is_opw(self) -> bool:
        """Only sources that can look for sensors again offer it; the others' are fixed."""
        return self._provider.supports_redetect

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            options = {
                CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                CONF_STALE_HOURS: int(user_input[CONF_STALE_HOURS]),
                CONF_ALERT_STAGE: user_input.get(CONF_ALERT_STAGE, DEFAULT_ALERT_STAGE),
            }
            if user_input.get(CONF_REDETECT) and self._is_opw:
                api = WaterlevelApi(async_get_clientsession(self.hass))
                try:
                    _, available = await api.detect_station(self.config_entry.data[CONF_STATION])
                except StationNotFound:
                    errors["base"] = "station_not_found"
                except WaterlevelError:
                    errors["base"] = "cannot_connect"
                else:
                    # Sensors and options in one update, so the station reloads once
                    self.hass.config_entries.async_update_entry(
                        self.config_entry,
                        data={**self.config_entry.data, CONF_AVAILABLE_SENSORS: available},
                        options=options,
                    )
            if not errors:
                # Saving reloads the station, which picks up the settings and any new sensors
                return self.async_create_entry(data=options)
        saved = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=saved.get(CONF_SCAN_INTERVAL, self._default_interval),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=self._min_interval,
                            max=180,
                            step=5,
                            unit_of_measurement="min",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_STALE_HOURS,
                        default=saved.get(CONF_STALE_HOURS, DEFAULT_STALE_HOURS),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=1,
                            max=72,
                            step=1,
                            unit_of_measurement="h",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_ALERT_STAGE,
                        default=saved.get(CONF_ALERT_STAGE, DEFAULT_ALERT_STAGE),
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=[stage for stage in FLOOD_STAGES if stage != "normal"],
                            translation_key=CONF_ALERT_STAGE,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                    **(
                        {vol.Optional(CONF_REDETECT, default=False): BooleanSelector()}
                        if self._is_opw
                        else {}
                    ),
                }
            ),
            errors=errors,
        )
