from datetime import date, datetime, timedelta, timezone


def today() -> date:
    """Today in utc.

    Telegram timestamps are utc and history folders are named after the utc
    date, so every date comparison in the project has to use utc as well.
    """
    return datetime.now(timezone.utc).date()


def cutoff(last_days: int) -> str:
    """First date of a window of `last_days` calendar days ending today.

    `last_days=1` is today alone. Returned as YYYY-MM-DD so it can be compared
    directly against the date-named history folders.
    """
    if last_days < 1:
        # a zero or negative window puts the cutoff in the future, which
        # silently selects nothing
        raise ValueError(f"last_days must be at least 1, got {last_days}")
    return (today() - timedelta(days=last_days - 1)).isoformat()
