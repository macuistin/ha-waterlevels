"""Repair issue for a station that has stopped reporting for good."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import StationCoordinator

# A gauge that has reported nothing for this long has most likely been decommissioned.
# Shorter outages are shown by Data Stale and Last Reading, which need no action.
DEAD_AFTER = timedelta(days=30)


def issue_id(coordinator: StationCoordinator) -> str:
    """The repair issue's id: one per station, so it can't be raised twice."""
    return f"station_not_reporting_{coordinator.config_entry.entry_id}"


@callback
def async_update_station_issue(hass: HomeAssistant, coordinator: StationCoordinator) -> None:
    """Raise the repair issue when the station's newest reading is DEAD_AFTER old, else clear it."""
    last = coordinator.last_reading_time
    if last is None or dt_util.utcnow() - last <= DEAD_AFTER:
        ir.async_delete_issue(hass, DOMAIN, issue_id(coordinator))
        return
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id(coordinator),
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="station_not_reporting",
        translation_placeholders={
            "station": coordinator.station_name,
            "days": str((dt_util.utcnow() - last).days),
        },
    )


@callback
def async_delete_station_issue(hass: HomeAssistant, coordinator: StationCoordinator) -> None:
    """Remove the issue when the station is removed or unloaded."""
    ir.async_delete_issue(hass, DOMAIN, issue_id(coordinator))
