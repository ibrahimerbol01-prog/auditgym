"""Episode configuration: defaults, strict validation, canonical hash.

Any valid config must yield a valid, solvable episode (plan §5.6). Unknown keys and
out-of-range values raise ConfigError with a short, bounded message.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

from .money import EXPONENTS
from .timeutil import TZ_OFFSETS_MIN
from .version import CONFIG_VERSION

ERROR_TYPES = ("duplicate_invoice", "payment_allocation", "date_or_fx", "period_classification")
INTERACTIONS = ("A", "B")
MAX_ERRORS = 12


class ConfigError(ValueError):
    """Bounded, user-facing configuration error."""


@dataclass(frozen=True)
class EpisodeConfig:
    config_version: str = CONFIG_VERSION
    n_invoices: int = 50
    n_expenses: int = 80
    errors: Dict[str, int] = field(default_factory=lambda: {
        "duplicate_invoice": 1, "payment_allocation": 1, "date_or_fx": 1, "period_classification": 1})
    clean: bool = False
    interactions: List[str] = field(default_factory=list)
    base_currency: str = "KZT"
    foreign_currencies: List[str] = field(default_factory=lambda: ["USD", "EUR"])
    foreign_share: float = 0.4
    timezone: str = "Asia/Tashkent"
    period_year: int = 2026
    period_start_month: int = 1
    period_months: int = 3
    distractor_level: int = 1
    layout_seed: int = 0
    id_seed: int = 0

    def total_issues(self) -> int:
        if self.clean:
            return 0
        extra = {"A": 3, "B": 2}
        return sum(self.errors.values()) + sum(extra[i] for i in self.interactions)

    def canonical(self) -> Dict[str, Any]:
        d = asdict(self)
        d["errors"] = {k: d["errors"].get(k, 0) for k in ERROR_TYPES}
        d["interactions"] = sorted(d["interactions"])
        d["foreign_currencies"] = list(d["foreign_currencies"])
        return d

    def content_hash(self) -> str:
        """Hash of everything except layout_seed/id_seed (those only rename and reorder)."""
        d = self.canonical()
        d.pop("layout_seed")
        d.pop("id_seed")
        return hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()


_FIELDS = {f for f in EpisodeConfig.__dataclass_fields__}


def _int(d: Dict[str, Any], key: str, lo: int, hi: int) -> int:
    v = d[key]
    if isinstance(v, bool) or not isinstance(v, int):
        raise ConfigError(f"{key} must be an integer")
    if not lo <= v <= hi:
        raise ConfigError(f"{key} must be in [{lo}, {hi}]")
    return v


def make_config(raw: Any = None) -> EpisodeConfig:
    """Fill defaults and validate. ``raw`` may be None, a partial dict or an EpisodeConfig."""
    if isinstance(raw, EpisodeConfig):
        raw = raw.canonical()
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigError("config must be an object")
    unknown = sorted(set(raw) - _FIELDS)
    if unknown:
        raise ConfigError(f"unknown config key: {unknown[0][:40]}")
    base = EpisodeConfig().canonical()
    merged = dict(base)
    for k, v in raw.items():
        if k == "errors" and isinstance(v, dict):
            e = {t: 0 for t in ERROR_TYPES}
            e.update(v)
            merged[k] = e
        else:
            merged[k] = v
    d = merged
    if d["config_version"] != CONFIG_VERSION:
        raise ConfigError("unsupported config_version")
    _int(d, "n_invoices", 20, 100)
    _int(d, "n_expenses", 20, 600)
    if not isinstance(d["clean"], bool):
        raise ConfigError("clean must be a boolean")
    if not isinstance(d["errors"], dict):
        raise ConfigError("errors must be an object")
    for k, v in d["errors"].items():
        if k not in ERROR_TYPES:
            raise ConfigError(f"unknown error type: {str(k)[:40]}")
        if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 4:
            raise ConfigError(f"errors.{k} must be an integer in [0, 4]")
    if not isinstance(d["interactions"], list) or any(i not in INTERACTIONS for i in d["interactions"]):
        raise ConfigError("interactions must be a list of 'A'/'B'")
    if len(set(d["interactions"])) != len(d["interactions"]):
        raise ConfigError("interactions must not repeat")
    if d["base_currency"] not in EXPONENTS:
        raise ConfigError("unsupported base_currency")
    fc = d["foreign_currencies"]
    if not isinstance(fc, list) or not 1 <= len(fc) <= 3 or len(set(fc)) != len(fc):
        raise ConfigError("foreign_currencies must list 1-3 distinct currencies")
    if any(c not in EXPONENTS or c == d["base_currency"] for c in fc):
        raise ConfigError("foreign_currencies must be supported and differ from base")
    fs = d["foreign_share"]
    if isinstance(fs, bool) or not isinstance(fs, (int, float)) or not 0.2 <= fs <= 0.8:
        raise ConfigError("foreign_share must be in [0.2, 0.8]")
    if d["timezone"] not in TZ_OFFSETS_MIN:
        raise ConfigError("unsupported timezone")
    _int(d, "period_year", 2020, 2030)
    _int(d, "period_start_month", 1, 12)
    _int(d, "period_months", 1, 3)
    _int(d, "distractor_level", 0, 2)
    _int(d, "layout_seed", 0, 2**63 - 1)
    _int(d, "id_seed", 0, 2**63 - 1)
    cfg = EpisodeConfig(**{**d, "foreign_share": float(fs)})
    if cfg.total_issues() > MAX_ERRORS:
        raise ConfigError(f"at most {MAX_ERRORS} issues per episode")
    # Each interaction scenario needs foreign invoices near the boundary; keep room for hosts.
    if cfg.total_issues() > cfg.n_invoices // 4:
        raise ConfigError("too many issues for n_invoices (need n_invoices >= 4 x issues)")
    return cfg


def validate_seed(seed: Any) -> int:
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**63:
        raise ConfigError("seed must be an integer in [0, 2^63)")
    return seed
