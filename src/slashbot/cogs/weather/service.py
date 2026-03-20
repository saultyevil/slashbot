"""Weather API service layer."""

import datetime
import json
from dataclasses import dataclass

import httpx
from geopy import GoogleV3
from geopy.exc import GeocoderQueryError
from geopy.location import Location

from slashbot.settings import BotSettings

from .error import GeocodeError, LocationNotFoundError, OneCallError


@dataclass
class ResolvedLocation:
    """A geocoded location with its display string."""

    display: str
    lat: float
    lon: float


@dataclass
class UnitConfig:
    """Display configuration for a chosen unit system."""

    temp_unit: str
    wind_unit: str
    wind_factor: float


@dataclass
class WeatherAlert:
    """A single active weather alert."""

    event: str
    start: datetime.datetime
    end: datetime.datetime


@dataclass
class CurrentWeather:
    """Current weather conditions returned by the OneCall API."""

    description: str
    temp: float
    feels_like: float
    humidity: int
    wind_speed: float
    wind_deg: float
    icon: str


@dataclass
class DailyForecast:
    """A single day's forecast from the OneCall API."""

    dt: datetime.datetime
    description: str
    temp_min: float
    temp_max: float
    humidity: int
    wind_speed: float
    wind_deg: float
    icon: str
    summary: str | None = None  # present in daily, absent in hourly


@dataclass
class HourlyForecast:
    """A single hour's forecast from the OneCall API."""

    dt: datetime.datetime
    description: str
    temp: float
    humidity: int
    wind_speed: float
    wind_deg: float
    icon: str


def parse_address_components(raw_components: list[dict]) -> str:
    """Extract a ``"City, CC"`` string from Google geocoder address components.

    Parameters
    ----------
    raw_components:
        The ``address_components`` list from a Google Geocoding API response.

    Returns
    -------
    str
        A formatted address string such as ``"Reading, GB"``.

    """
    locality = next((c["long_name"] for c in raw_components if "locality" in c["types"]), "")
    country = next((c["short_name"] for c in raw_components if "country" in c["types"]), "")
    return f"{locality}, {country}"


def parse_active_alerts(
    raw_alerts: list[dict] | None,
    timezone_offset: int,
) -> list[WeatherAlert]:
    """Return only those alerts that are currently active.

    Parameters
    ----------
    raw_alerts:
        The ``alerts`` list from the OneCall API, or ``None``.
    timezone_offset:
        Seconds east of UTC for the queried location.

    """
    if not raw_alerts:
        return []

    now = datetime.datetime.now(tz=datetime.UTC)
    tz = datetime.timezone(datetime.timedelta(seconds=timezone_offset))
    active = []
    for alert in raw_alerts:
        start = datetime.datetime.fromtimestamp(alert["start"], tz=datetime.UTC).astimezone(tz)
        end = datetime.datetime.fromtimestamp(alert["end"], tz=datetime.UTC).astimezone(tz)
        if start <= now <= end:
            active.append(WeatherAlert(event=alert["event"], start=start, end=end))
    return active


def parse_current_weather(raw: dict) -> CurrentWeather:
    """Construct a :class:`CurrentWeather` from a OneCall ``current`` dict."""
    return CurrentWeather(
        description=raw["weather"][0]["description"].capitalize(),
        temp=raw["temp"],
        feels_like=raw["feels_like"],
        humidity=raw["humidity"],
        wind_speed=raw["wind_speed"],
        wind_deg=raw["wind_deg"],
        icon=raw["weather"][0]["icon"],
    )


def parse_daily_forecasts(raw_list: list[dict], tz_offset: int) -> list[DailyForecast]:
    """Convert a list of raw daily forecast dicts into typed objects."""
    tz = datetime.timezone(datetime.timedelta(seconds=tz_offset))
    return [
        DailyForecast(
            dt=datetime.datetime.fromtimestamp(raw["dt"], tz=datetime.UTC).astimezone(tz),
            description=raw["weather"][0]["description"].capitalize(),
            temp_min=raw["temp"]["min"],
            temp_max=raw["temp"]["max"],
            humidity=raw["humidity"],
            wind_speed=raw["wind_speed"],
            wind_deg=raw["wind_deg"],
            icon=raw["weather"][0]["icon"],
            summary=raw.get("summary"),
        )
        for raw in raw_list
    ]


def parse_hourly_forecasts(raw_list: list[dict], tz_offset: int) -> list[HourlyForecast]:
    """Convert a list of raw hourly forecast dicts into typed objects."""
    tz = datetime.timezone(datetime.timedelta(seconds=tz_offset))
    return [
        HourlyForecast(
            dt=datetime.datetime.fromtimestamp(raw["dt"], tz=datetime.UTC).astimezone(tz),
            description=raw["weather"][0]["description"].capitalize(),
            temp=raw["temp"],
            humidity=raw["humidity"],
            wind_speed=raw["wind_speed"],
            wind_deg=raw["wind_deg"],
            icon=raw["weather"][0]["icon"],
        )
        for raw in raw_list
    ]


def get_unit_config(units: str) -> UnitConfig:
    """Return display strings and conversion factors for a unit system.

    Parameters
    ----------
    units:
        One of ``"metric"``, ``"mixed"``, or ``"imperial"``.

    Raises
    ------
    ValueError
        If *units* is not a recognised value.

    """
    match units:
        case "metric":
            return UnitConfig("C", "kph", 3.6)
        case "mixed":
            return UnitConfig("C", "mph", 2.237)
        case "imperial":
            return UnitConfig("F", "mph", 1.0)
        case _:
            msg = f"Unknown weather units: {units!r}"
            raise ValueError(msg)


class WeatherService:
    """Handles geocoding and OpenWeatherMap OneCall API requests.

    All methods are self-contained and raise typed exceptions; there is no
    Discord-specific logic here.
    """

    _OWM_BASE_URL = (
        "https://api.openweathermap.org/data/3.0/onecall?lat={lat}&lon={lon}&units={units}&exclude=minutely&appid={key}"
    )

    def __init__(self) -> None:
        self._geolocator = GoogleV3(api_key=BotSettings.keys.google, domain="maps.google.co.uk")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve_location(self, query: str) -> ResolvedLocation:
        """Geocode *query* and return a :class:`ResolvedLocation`.

        Raises
        ------
        GeocodeError
            If the Geocoding API raises an exception.
        LocationNotFoundError
            If the query returns no results.

        """
        try:
            result = self._geolocator.geocode(query, region="GB")
        except GeocoderQueryError as exc:
            msg = f"Geocoding API error for {query!r}"
            raise GeocodeError(msg) from exc

        if result is None or not isinstance(result, Location):
            msg = f"{query!r} could not be geocoded"
            raise LocationNotFoundError(msg)

        address = parse_address_components(result.raw["address_components"])
        if address.startswith(",") or address.endswith(","):
            address = str(result)

        return ResolvedLocation(
            display=f"{address}\n({result.latitude}, {result.longitude})",
            lat=result.latitude,
            lon=result.longitude,
        )

    async def fetch_weather(
        self,
        location: ResolvedLocation,
        units: str,
        fields: str | list[str],
    ) -> dict:
        """Fetch weather data from the OneCall API.

        Parameters
        ----------
        location:
            A previously resolved location.
        units:
            ``"metric"`` or ``"imperial"`` (``"mixed"`` is resolved to
            ``"metric"`` before the request is made).
        fields:
            A single field name (e.g. ``"current"``) or a list of field
            names (e.g. ``["current", "daily", "alerts"]``) to return.

        Returns
        -------
        dict
            A dict containing only the requested *fields* plus
            ``timezone_offset``.

        Raises
        ------
        LocationNotFoundError
            If OWM returns 404 for the co-ordinates.
        OneCallError
            For any other non-200 response.

        """
        api_units = "metric" if units == "mixed" else units
        url = self._OWM_BASE_URL.format(
            lat=location.lat,
            lon=location.lon,
            units=api_units,
            key=BotSettings.keys.openweathermap,
        )

        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=5)

        if response.status_code == httpx.codes.NOT_FOUND:
            msg = f"OWM could not find co-ordinates ({location.lat}, {location.lon})"
            raise LocationNotFoundError(msg)
        if response.status_code != httpx.codes.OK:
            msg = f"OWM OneCall returned {response.status_code}"
            raise OneCallError(msg)

        payload = json.loads(response.content)
        return self._extract_fields(payload, fields)

    @staticmethod
    def _extract_fields(payload: dict, fields: str | list[str]) -> dict:
        if isinstance(fields, str):
            return {
                fields: payload[fields],
                "timezone_offset": payload["timezone_offset"],
            }
        return {key: value for key, value in payload.items() if key in fields or key == "timezone_offset"}
