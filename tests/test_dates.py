from datetime import datetime, timedelta, timezone

import pytest

from tgcs.dates import cutoff, today


def test_one_day_window_is_today_only():
    assert cutoff(1) == today().isoformat()


def test_window_ends_today_and_is_inclusive():
    assert cutoff(7) == (today() - timedelta(days=6)).isoformat()


def test_a_nonpositive_window_is_rejected():
    # a cutoff in the future would silently select nothing
    for last_days in (0, -1):
        with pytest.raises(ValueError, match="at least 1"):
            cutoff(last_days)


def test_today_is_utc_not_local():
    # history folders are named after the utc date, so the window must match
    assert today() == datetime.now(timezone.utc).date()
