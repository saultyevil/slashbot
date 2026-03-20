import disnake

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
        Bearing in degrees (0–360).

    Returns
    -------
    str
        Cardinal direction label, e.g. ``"NNW"``.

    """
    index = round(degrees / (360.0 / len(_CARDINAL_DIRECTIONS))) % len(_CARDINAL_DIRECTIONS)
    return _CARDINAL_DIRECTIONS[index]


def weather_icon_url(icon_code: str) -> str:
    """Return the OpenWeatherMap icon URL for *icon_code*."""
    return f"https://openweathermap.org/img/wn/{icon_code}@2x.png"


class WeatherEmbedBuilder:
    @staticmethod
    def current(
        location_display: str,
        current: CurrentWeather,
        daily: list[DailyForecast],
        alerts: list[WeatherAlert],
        unit_cfg: UnitConfig,
        footer_text: str,
    ) -> disnake.Embed:
        """Build an embed showing current conditions."""
        embed = disnake.Embed(title=location_display, colour=disnake.Colour.default())
        embed.set_footer(text=footer_text)
        embed.set_thumbnail(url=weather_icon_url(current.icon))

        conditions = (
            f"{current.description}, "
            f"{current.temp:.0f} °{unit_cfg.temp_unit} "
            f"and feels like {current.feels_like:.0f} °{unit_cfg.temp_unit}"
        )
        embed.add_field(name="Conditions", value=conditions, inline=False)

        WeatherEmbedBuilder._add_alerts(embed, alerts)

        today = daily[0]
        embed.add_field(
            name="Temperature",
            value=f"{today.temp_min:.0f} / {today.temp_max:.0f} °{unit_cfg.temp_unit}",
            inline=False,
        )
        embed.add_field(name="Humidity", value=f"{current.humidity}%", inline=False)

        wind_speed = current.wind_speed * unit_cfg.wind_factor
        cardinal = degrees_to_cardinal(current.wind_deg)
        embed.add_field(
            name="Wind",
            value=f"{wind_speed:.0f} {unit_cfg.wind_unit} @ {current.wind_deg:.0f}° ({cardinal})",
            inline=False,
        )

        return embed

    @staticmethod
    def daily_forecast(
        location_display: str,
        forecasts: list[DailyForecast],
        unit_cfg: UnitConfig,
        footer_text: str,
    ) -> disnake.Embed:
        """Build an embed showing a multi-day forecast."""
        embed = disnake.Embed(title=location_display, colour=disnake.Colour.default())
        embed.set_footer(text=footer_text)
        embed.set_thumbnail(url=weather_icon_url(forecasts[0].icon))

        for day in forecasts:
            date_str = day.dt.strftime(r"%a, %d %b %Y")
            temp_str = f"{day.temp_min:.0f} / {day.temp_max:.0f} °{unit_cfg.temp_unit}"
            WeatherEmbedBuilder._add_forecast_field(embed, date_str, day.description, temp_str, day, unit_cfg)

        return embed

    @staticmethod
    def hourly_forecast(
        location_display: str,
        forecasts: list[HourlyForecast],
        unit_cfg: UnitConfig,
        footer_text: str,
    ) -> disnake.Embed:
        """Build an embed showing an hourly forecast."""
        embed = disnake.Embed(title=location_display, colour=disnake.Colour.default())
        embed.set_footer(text=footer_text)
        embed.set_thumbnail(url=weather_icon_url(forecasts[0].icon))

        for hour in forecasts:
            date_str = hour.dt.strftime(r"%H:%M")
            temp_str = f"{hour.temp} °{unit_cfg.temp_unit}"
            WeatherEmbedBuilder._add_forecast_field(embed, date_str, hour.description, temp_str, hour, unit_cfg)

        return embed

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _add_alerts(embed: disnake.Embed, alerts: list[WeatherAlert]) -> None:
        if not alerts:
            return
        label = "Weather Alert" if len(alerts) == 1 else "Weather Alerts"
        date_str = alerts[0].start.strftime(r"%d %B %Y")
        lines = [f"{a.event}: {a.start.strftime(r'%H:%M')} to {a.end.strftime(r'%H:%M')}" for a in alerts]
        embed.add_field(name=f"{label} [{date_str}]", value="\n".join(lines), inline=False)

    @staticmethod
    def _add_forecast_field(
        embed: disnake.Embed,
        date_str: str,
        description: str,
        temp_str: str,
        entry: DailyForecast | HourlyForecast,
        unit_cfg: UnitConfig,
    ) -> None:
        humidity_str = f"({entry.humidity}% RH)"
        wind_speed = entry.wind_speed * unit_cfg.wind_factor
        cardinal = degrees_to_cardinal(entry.wind_deg)
        wind_str = f"{wind_speed:.0f} {unit_cfg.wind_unit} @ {entry.wind_deg:.0f}° ({cardinal})"
        embed.add_field(
            name=date_str,
            value=f"{description:^30s}\n{temp_str} {humidity_str:^30s}\n{wind_str:^30s}",
            inline=False,
        )
