from datetime import datetime, timedelta, timezone

from run_pipeline import age_color, relative_time


# ---------------------------------------------------------------------------
# relative_time
# ---------------------------------------------------------------------------

def test_relative_time_none_is_unknown():
    assert relative_time(None) == "unknown"


def test_relative_time_seconds_singular():
    dt = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert relative_time(dt) == "1 second ago"


def test_relative_time_seconds_plural():
    dt = datetime.now(timezone.utc) - timedelta(seconds=30)
    assert relative_time(dt) == "30 seconds ago"


def test_relative_time_minutes():
    dt = datetime.now(timezone.utc) - timedelta(minutes=5)
    assert relative_time(dt) == "5 minutes ago"


def test_relative_time_hours():
    dt = datetime.now(timezone.utc) - timedelta(hours=2)
    assert relative_time(dt) == "2 hours ago"


def test_relative_time_days():
    dt = datetime.now(timezone.utc) - timedelta(days=3)
    assert relative_time(dt) == "3 days ago"


def test_relative_time_handles_naive_datetime_as_utc():
    naive = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=10)
    assert relative_time(naive) == "10 minutes ago"


# ---------------------------------------------------------------------------
# age_color
# ---------------------------------------------------------------------------

def test_age_color_none_is_grey():
    assert age_color(None) == "grey58"


def test_age_color_fresh_posting_is_green():
    dt = datetime.now(timezone.utc)
    assert age_color(dt) == "rgb(90,230,110)"


def test_age_color_max_age_is_red():
    # MAX_POSTING_AGE_DAYS = 3 in run_pipeline.py
    dt = datetime.now(timezone.utc) - timedelta(days=3)
    assert age_color(dt) == "rgb(235,70,70)"


def test_age_color_beyond_max_age_clamps_to_red():
    dt = datetime.now(timezone.utc) - timedelta(days=30)
    assert age_color(dt) == "rgb(235,70,70)"


def test_age_color_midpoint_is_yellow():
    dt = datetime.now(timezone.utc) - timedelta(days=1.5)
    assert age_color(dt) == "rgb(240,210,60)"
