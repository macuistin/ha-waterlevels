# Changelog

What each release changed, newest first.

## v1.0.0

The first stable release since 0.1.0, and the first for HACS's default store. It rolls up the 0.2.0 betas: a country step when adding a station, a search across all countries, a Scottish device link, a README section on coastal and tidal stations, and fixes for English stations. Nothing changes for stations you have already added. It is an unofficial community integration that uses public data.

**Added**
- **Search all countries** when adding a station: one location and radius search across Ireland, England and Scotland, closest first. See v0.2.0b1.
- A README section on coastal and tidal stations (Irish ports, piers, quays and docks, and English tidal gauges): how the tide affects the trend, Flood Stage and Flood Alert, and where their thresholds come from.

**Changed**
- Adding a station starts with the country (Ireland, England or Scotland), under the title **Add a station**.
- A Scottish station's device links to its page on SEPA's water levels website.

**Fixes**
- English stations with a retired level measure, or a single measure, can now be added.
- An English station that has stopped reporting is refused when adding it, with a clear message.

**Upgrading**
- Stable installs move from 0.1.0 straight to 1.0.0. Beta testers on 0.2.0b2 get the same code plus the README section.

## v0.2.0b2

A second beta. It fixes two problems adding English stations found while testing 0.2.0b1. It is a pre-release: stable installs stay on v0.1.0.

**Fixes**
- An English station whose API record lists a single measure, such as Ellamsbridge Road (694122) and Haydock West End Road (694015), was refused with "No water level data was found for that station". It can now be added.
- An English station that is listed as active but has stopped reporting, such as Rivington Road (694121, silent since July), was added and then failed setup for ever. Adding it now stops with a clear message to choose another station. Stations you added before this keep retrying and recover if the gauge returns.

## v0.2.0b1

A beta of the next release, for HACS users who enable beta versions. It adds a country step when adding a station, a search across all countries and a fix for English stations with a retired level measure. It is a pre-release: stable installs stay on v0.1.0.

**Added**
- **Search all countries** when adding a station: one location and radius search across Ireland, England and Scotland, closest first, with the country on each station. It is useful near a border. A country that can't be reached is skipped, and the search fails only when none can be.

**Changed**
- Adding a station now starts with the country (Ireland, England or Scotland), under the title **Add a station**. Ireland then offers its three ways to find a station: near a location, by river or by station number. England and Scotland go straight to the location search, which is their only method. Nothing changes for stations you have already added.
- A Scottish station's device now links to its page on SEPA's water levels website (**Visit** on the device page), as Irish and English stations already link to theirs.

**Fixes**
- An English station that keeps a retired level measure beside its live one (for example Ivy Street, Ashton-In-Makerfield, station 694020) failed setup with "no reading available". Adding a station now picks the measure that still reports. A station saved with the retired one looks itself up again and switches, without being re-added.

## v0.1.0

The first release of Water Levels: live water levels and flows from public government monitoring stations, with flood alerts and Home Assistant sensors for each station. It reads Irish stations from waterlevel.ie (OPW), English stations from the Environment Agency and Scottish stations from SEPA. Wales is not supported yet, because Natural Resources Wales needs a per-user API key. It is an unofficial community integration that uses public data.

**Added**
- **Ireland**, from waterlevel.ie (OPW): add stations near a location, by river or by station number.
- **England**, from the Environment Agency's real-time flood-monitoring API (Open Government Licence): find stations near a location. Flood thresholds start from the station's stage scale.
- **Scotland**, from SEPA's time series API (Open Government Licence, no account): find stations near a location. Scottish stations update every 30 minutes, because SEPA limits anonymous access per IP address, and the setup steps warn about it.
- Each country is its own device type with the same entity names: Water Level, Water Level Trend, Discharge where measured, Flood Stage, Flood Alert, the three threshold numbers, Station Information, Last Reading, Data Age and Data Stale. Irish stations also have Flow Percentile and the other OPW sensors.
- Station options under **Configure**: update interval, how long without a reading counts as stale, the lowest stage that turns Flood Alert on, and (Ireland) re-checking the station for new sensors.
- A **River flood warning** automation blueprint, diagnostics download, an Irish translation (a first draft, corrections welcome) and a brand icon and logo.
- Each country is a provider with its own coordinator, update interval, options and optional extra sensors, so another country can be added without touching the others.

**Upgrading**
- This is the first release. It is not a flood warning service: see the README.
