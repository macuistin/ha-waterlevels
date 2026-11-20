"""The sources of Water Levels, one provider per country.

A provider is a coordinator class. It reads its own API, says how its station appears as a
device, and may add its own sensors and options by overriding the hooks on
`StationCoordinator`. Everything else (platforms, entities, thresholds, stale tracking) is
shared. To add a country, subclass `StationCoordinator`, add its source key here and give
it config flow steps.
"""

from __future__ import annotations

from .const import SOURCE_EA, SOURCE_OPW, SOURCE_SEPA
from .coordinator import StationCoordinator, WaterlevelCoordinator
from .ea_coordinator import EnvironmentAgencyCoordinator
from .sepa_coordinator import SepaCoordinator

# An entry with no source is OPW (Ireland), as every entry made before other countries was
PROVIDERS: dict[str, type[StationCoordinator]] = {
    SOURCE_OPW: WaterlevelCoordinator,
    SOURCE_EA: EnvironmentAgencyCoordinator,
    SOURCE_SEPA: SepaCoordinator,
}


def provider_for(source: str | None) -> type[StationCoordinator]:
    """The coordinator class for an entry's source."""
    return PROVIDERS.get(source or SOURCE_OPW, WaterlevelCoordinator)
