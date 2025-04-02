import datetime


def add_days_to_datetime(
    now: datetime.datetime, original_date: datetime.datetime, days_to_add: float
) -> datetime.datetime:
    """Add a week to a datetime object.

    Parameters
    ----------
    now: datetime.datetime:
        The current datetime.
    original_date: datetime.datetime
        The datetime to calculate from.
    days_to_add: float
        The number of additional days to sleep for

    Returns
    -------
    A datetime object a week after the given one.

    """
    if days_to_add < 0:
        msg = "Invalid value for days_to_add, cannot be < 0"
        raise ValueError(msg)
    if not isinstance(original_date, datetime.datetime):
        msg = "Need to pass time as a datetime.datetime"
        raise TypeError(msg)

    time_delta = original_date + datetime.timedelta(days=days_to_add)
    next_date = datetime.datetime(
        year=time_delta.year,
        month=time_delta.month,
        day=time_delta.day,
        hour=original_date.hour,
        minute=original_date.minute,
        second=original_date.second,
        tzinfo=original_date.tzinfo,
    )

    return (next_date - now).total_seconds()


def calculate_seconds_until(weekday: int, hour: int, minute: int, frequency_days: int) -> int:
    """Calculate how long to sleep till a hour:minute time for a given weekday.

    If the requested moment is time is beyond the current time, the number of
    days provided in frequency are added.

    Parameters
    ----------
    weekday : int
        An integer representing the weekday, where Monday is 0. If < 0, the
        current day is used.
    hour : int
        The hour for the requested time.
    minute : int
        The minute for the requested time.
    frequency_days : Frequency
        The frequency at which to repeat this, in days.

    Returns
    -------
    int
        The time to sleep for in seconds.

    """
    if frequency_days < 0:
        msg = "Invalid value for frequency, cannot be < 0"
        raise ValueError(msg)
    if not isinstance(weekday, int) or weekday > 6:
        msg = "Invalid value for weekday: 0 <= weekday <= 6 and must be int"
        raise ValueError(msg)

    my_timezone = datetime.datetime.now(datetime.UTC).astimezone().tzinfo
    now = datetime.datetime.now(my_timezone)

    if weekday < 0:
        weekday = now.weekday()

    day_delta = now + datetime.timedelta(days=(weekday - now.weekday()) % 7)
    next_date = datetime.datetime(
        year=day_delta.year,
        month=day_delta.month,
        day=day_delta.day,
        hour=hour,
        minute=minute,
        second=0,
        tzinfo=now.tzinfo,
    )
    sleep_for_seconds = (next_date - now).total_seconds()

    if sleep_for_seconds <= 0:
        sleep_for_seconds = add_days_to_datetime(now, next_date, frequency_days)

    return sleep_for_seconds
