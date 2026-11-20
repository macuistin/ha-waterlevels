"""Each country is a provider: its own coordinator, intervals, options and sensors."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.components.sensor import SensorEntity

from custom_components.water_levels import sensor
from custom_components.water_levels.const import (
    SEPA_SCAN_INTERVAL,
    SOURCE_EA,
    SOURCE_OPW,
    SOURCE_SEPA,
)
from custom_components.water_levels.coordinator import StationCoordinator, WaterlevelCoordinator
from custom_components.water_levels.ea_coordinator import EnvironmentAgencyCoordinator
from custom_components.water_levels.providers import PROVIDERS, provider_for
from custom_components.water_levels.sepa_coordinator import SepaCoordinator


def test_each_source_has_its_own_provider() -> None:
    assert provider_for(SOURCE_OPW) is WaterlevelCoordinator
    assert provider_for(SOURCE_EA) is EnvironmentAgencyCoordinator
    assert provider_for(SOURCE_SEPA) is SepaCoordinator
    assert set(PROVIDERS) == {SOURCE_OPW, SOURCE_EA, SOURCE_SEPA}


def test_an_entry_with_no_source_is_ireland() -> None:
    assert provider_for(None) is WaterlevelCoordinator
    assert provider_for("") is WaterlevelCoordinator


def test_providers_set_their_own_options() -> None:
    assert WaterlevelCoordinator.supports_redetect
    assert not EnvironmentAgencyCoordinator.supports_redetect
    assert not SepaCoordinator.supports_redetect
    assert SepaCoordinator.min_scan_interval == SEPA_SCAN_INTERVAL
    assert SepaCoordinator.default_scan_interval == SEPA_SCAN_INTERVAL
    assert EnvironmentAgencyCoordinator.min_scan_interval < SEPA_SCAN_INTERVAL


async def test_the_base_provider_has_no_extras() -> None:
    assert await StationCoordinator.async_prepare(MagicMock()) is None
    assert await StationCoordinator.async_load_background(MagicMock()) is None
    assert StationCoordinator.extra_sensors(MagicMock()) == []


async def test_a_providers_own_sensors_are_added() -> None:
    """A country can add sensors that only it has, next to the shared ones."""
    extra = MagicMock(spec=SensorEntity)
    coordinator = MagicMock()
    coordinator.available_sensors = []
    coordinator.extra_sensors.return_value = [extra]
    entry = MagicMock(runtime_data=coordinator)
    add = MagicMock()
    await sensor.async_setup_entry(MagicMock(), entry, add)
    add.assert_called_once_with([extra])
