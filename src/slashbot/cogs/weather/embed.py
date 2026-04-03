import disnake

from .service import CurrentWeather, DailyForecast, HourlyForecast, UnitConfig, WeatherAlert

_CARDINAL_DIRECTIONS = [
    "N",
    "NNE",
    "NE",
    "ENE",
    "E",
    "ESE",
    "SE",
    "SSE",
    "S",
    "SSW",
    "SW",
    "WSW",
    "W",
    "WNW",
    "NW",
    "NNW",
]


def degrees_to_cardinal(degrees: float) -> str:
    """Convert a compass bearing in degrees to a cardinal direction string.

    Parameters
    ----------
    degrees:
        Bearing in degrees (0-360).

    Returns
    -------
    str
        Cardinal direction label, e.g. "NNW".

    """
    index = round(degrees / (360.0 / len(_CARDINAL_DIRECTIONS))) % len(_CARDINAL_DIRECTIONS)
    return _CARDINAL_DIRECTIONS[index]


def weather_icon_url(icon_code: str) -> str:
    """Return the OpenWeatherMap icon URL for *icon_code*.

    Parameters
    ----------
    icon_code : str
        The icon code returned by the OpenWeatherMap API.

    Returns
    -------
    str
        The full URL to the icon image.

    """
    return f"https://openweathermap.org/img/wn/{icon_code}@2x.png"


class WeatherEmbedBuilder:
    """Embed builder for weather in Discord chat."""

    @staticmethod
    def _add_alerts(embed: disnake.Embed, alerts: list[WeatherAlert]) -> None:
        """Add weather alerts to an embed.

        If an empty list is passed, method will return immediately.

        Parameters
        ----------
        embed : disnake.Embed
            The embed to add alerts to.
        alerts : list[WeatherAlert]
            Weather alerts to be added.

        """
        if not alerts:
            return
        label = "Weather Alert" if len(alerts) == 1 else "Weather Alerts"
        date_str = alerts[0].start.strftime(r"%d %B %Y")
        lines = [f"{a.event}: {a.start.strftime(r'%H:%M')} to {a.end.strftime(r'%H:%M')}" for a in alerts]
        embed.add_field(name=f"{label} [{date_str}]", value="\n".join(lines), inline=False)

    @staticmethod
    def _add_forecast_field(embed: disnake.Embed, forecast: DailyForecast | HourlyForecast, units: UnitConfig) -> None:
        """Add a forecast entry to an embed.

        Parameters
        ----------
        embed : disnake.Embed
            The embed to add the forecast to.
        forecast : DailyForecast | HourlyForecast
            The forecast to add.
        units: UnitConfig
            The units to use.

        """
        wind_speed = forecast.wind_speed * units.wind_factor
        cardinal = degrees_to_cardinal(forecast.wind_deg)
        wind_str = f"{wind_speed:.0f} {units.wind_unit} @ {forecast.wind_deg:.0f}° ({cardinal})"
        humidity_str = f"({forecast.humidity}% RH)"

        if isinstance(forecast, DailyForecast):
            date_str = forecast.dt.strftime(r"%a, %d %b %Y")
            temp_str = f"{forecast.temp_min:.0f} / {forecast.temp_max:.0f} °{units.temp_unit}"
        else:
            date_str = forecast.dt.strftime(r"%H:%M")
            temp_str = f"{forecast.temp} °{units.temp_unit}"

        embed.add_field(
            name=date_str,
            value=f"{forecast.description:^30s}\n{temp_str} {humidity_str:^30s}\n{wind_str:^30s}",
            inline=False,
        )

    @staticmethod
    def current(
        location_display: str,
        current: CurrentWeather,
        daily: list[DailyForecast],
        alerts: list[WeatherAlert],
        units: UnitConfig,
        footer_text: str,
    ) -> disnake.Embed:
        """Build an embed showing current weather conditions.

        Parameters
        ----------
        location_display : str
            The human-readable location string to use as the embed title.
        current : CurrentWeather
            The current weather data.
        daily : list[DailyForecast]
            Daily forecasts; the first entry is used for today's min/max temperatures.
        alerts : list[WeatherAlert]
            Active weather alerts to display in the embed.
        units : UnitConfig
            The unit configuration controlling temperature, wind speed, and conversion factors.
        footer_text : str
            Text to display in the embed footer.

        Returns
        -------
        disnake.Embed
            The constructed embed.

        """
        embed = disnake.Embed(title=location_display, colour=disnake.Colour.default())
        embed.set_footer(text=footer_text)
        embed.set_thumbnail(url=weather_icon_url(current.icon))

        conditions = (
            f"{current.description}, "
            f"{current.temp:.0f} °{units.temp_unit} "
            f"and feels like {current.feels_like:.0f} °{units.temp_unit}"
        )
        embed.add_field(name="Conditions", value=conditions, inline=False)

        WeatherEmbedBuilder._add_alerts(embed, alerts)

        today = daily[0]
        embed.add_field(
            name="Temperature",
            value=f"{today.temp_min:.0f} / {today.temp_max:.0f} °{units.temp_unit}",
            inline=False,
        )
        embed.add_field(name="Humidity", value=f"{current.humidity}%", inline=False)

        wind_speed = current.wind_speed * units.wind_factor
        cardinal = degrees_to_cardinal(current.wind_deg)
        embed.add_field(
            name="Wind",
            value=f"{wind_speed:.0f} {units.wind_unit} @ {current.wind_deg:.0f}° ({cardinal})",
            inline=False,
        )

        return embed

    @staticmethod
    def daily_forecast(
        location_display: str,
        forecasts: list[DailyForecast],
        units: UnitConfig,
        footer_text: str,
    ) -> disnake.Embed:
        """Build an embed showing a multi-day forecast.

        Parameters
        ----------
        location_display : str
            The human-readable location string to use as the embed title.
        forecasts : list[DailyForecast]
            The daily forecasts to display.
        units : UnitConfig
            The unit configuration controlling temperature, wind speed, and conversion factors.
        footer_text : str
            Text to display in the embed footer.

        Returns
        -------
        disnake.Embed
            The constructed embed.

        """
        embed = disnake.Embed(title=location_display, colour=disnake.Colour.default())
        embed.set_footer(text=footer_text)
        embed.set_thumbnail(url=weather_icon_url(forecasts[0].icon))
        for day in forecasts:
            WeatherEmbedBuilder._add_forecast_field(embed, day, units)

        return embed

    @staticmethod
    def hourly_forecast(
        location_display: str,
        forecasts: list[HourlyForecast],
        units: UnitConfig,
        footer_text: str,
    ) -> disnake.Embed:
        """Build an embed showing an hourly forecast.

        Parameters
        ----------
        location_display : str
            The human-readable location string to use as the embed title.
        forecasts : list[HourlyForecast]
            The hourly forecasts to display.
        units : UnitConfig
            The unit configuration controlling temperature, wind speed, and conversion factors.
        footer_text : str
            Text to display in the embed footer.

        Returns
        -------
        disnake.Embed
            The constructed embed.

        """
        embed = disnake.Embed(title=location_display, colour=disnake.Colour.default())
        embed.set_footer(text=footer_text)
        embed.set_thumbnail(url=weather_icon_url(forecasts[0].icon))

        for hour in forecasts:
            WeatherEmbedBuilder._add_forecast_field(embed, hour, units)

        return embed
