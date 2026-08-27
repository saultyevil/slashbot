import datetime

from slashbot.cogs.weather.service import parse_active_alerts


def test_parse_active_alerts_removes_duplicate_alerts() -> None:
    """Repeated API entries should only produce one weather alert."""
    now = int(datetime.datetime.now(tz=datetime.UTC).timestamp())
    raw_alert = {
        "event": "Flood Warning",
        "start": now - 60,
        "end": now + 3600,
    }

    alerts = parse_active_alerts([raw_alert, raw_alert.copy()], timezone_offset=0)

    assert len(alerts) == 1
    assert alerts[0].event == "Flood Warning"
