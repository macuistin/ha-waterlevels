# Changelog

What each release changed, newest first.

## Unreleased

**Changed**
- A Scottish station's device now links to its page on SEPA's water levels website (**Visit** on the device page), as Irish and English stations already link to theirs.

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
