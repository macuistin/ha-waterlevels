"""Tests for the repair issue raised when a station stops reporting for good."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.water_levels.const import DOMAIN, LATEST_GEOJSON_URL

from .test_init import _entry, _feature, _mock_station


def _issue(hass: HomeAssistant, entry_id: str) -> ir.IssueEntry | None:
    return ir.async_get(hass).async_get_issue(DOMAIN, f"station_not_reporting_{entry_id}")


async def test_dead_station_raises_and_clears_a_repair_issue(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, frozen_now: FrozenDateTimeFactory
) -> None:
    # The last reading is 40 days old
    _mock_station(aioclient_mock)
    aioclient_mock.get(
        LATEST_GEOJSON_URL,
        json={"features": [_feature("14029", "0002", "9.0", "2026-09-09T18:00:00Z")]},
    )
    entry = _entry(hass, sensors=["0002"])
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    issue = _issue(hass, entry.entry_id)
    assert issue is not None
    assert issue.translation_key == "station_not_reporting"
    assert issue.translation_placeholders == {"station": "Graiguenamanagh", "days": "40"}
    assert not issue.is_fixable

    # The station reports again: the issue clears itself
    aioclient_mock.clear_requests()
    _mock_station(aioclient_mock)
    aioclient_mock.get(
        LATEST_GEOJSON_URL,
        json={"features": [_feature("14029", "0002", "9.5", "2026-10-19T18:30:00Z")]},
    )
    frozen_now.tick(timedelta(minutes=15))
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert _issue(hass, entry.entry_id) is None


async def test_quiet_station_raises_no_issue(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    # A day without a reading is an outage, shown by Data Stale, not a repair issue
    _mock_station(aioclient_mock)
    aioclient_mock.get(
        LATEST_GEOJSON_URL,
        json={"features": [_feature("14029", "0002", "9.0", "2026-10-18T18:00:00Z")]},
    )
    entry = _entry(hass, sensors=["0002"])
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert _issue(hass, entry.entry_id) is None


async def test_unloading_removes_the_issue(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    _mock_station(aioclient_mock)
    aioclient_mock.get(
        LATEST_GEOJSON_URL,
        json={"features": [_feature("14029", "0002", "9.0", "2026-09-09T18:00:00Z")]},
    )
    entry = _entry(hass, sensors=["0002"])
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert _issue(hass, entry.entry_id) is not None

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert _issue(hass, entry.entry_id) is None
