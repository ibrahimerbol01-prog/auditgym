"""Fixed-offset time zones (no zoneinfo: offsets must not depend on the host tzdata)."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

TZ_OFFSETS_MIN = {
    "UTC": 0,
    "Asia/Tashkent": 300,
    "Asia/Almaty": 300,
    "Asia/Dubai": 240,
    "Asia/Tokyo": 540,
    "Asia/Kolkata": 330,
    "Asia/Shanghai": 480,
}


def tz(name: str) -> timezone:
    try:
        return timezone(timedelta(minutes=TZ_OFFSETS_MIN[name]))
    except KeyError as exc:
        raise ValueError(f"unsupported timezone {name}") from exc


def offset_str(name: str) -> str:
    m = TZ_OFFSETS_MIN[name]
    sign = "+" if m >= 0 else "-"
    m = abs(m)
    return f"{sign}{m // 60:02d}:{m % 60:02d}"


def parse_ts(text: str) -> datetime:
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        raise ValueError("timestamp without offset")
    return dt


def local_date(ts: str, tz_name: str) -> date:
    """Calendar date of a timestamp in the company time zone."""
    return parse_ts(ts).astimezone(tz(tz_name)).date()


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")
