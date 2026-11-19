"""One entry point: generate(seed, config) -> {'public', 'private'} (plan §5)."""
from __future__ import annotations

from typing import Any, Dict

from ..config import EpisodeConfig, make_config, validate_seed
from .export import assemble
from .history import build_world, policy_doc
from .inject import inject_all


def generate(seed: int, config: Any = None) -> Dict[str, Any]:
    seed = validate_seed(seed)
    cfg: EpisodeConfig = make_config(config)
    world = build_world(seed, cfg)
    clean = world.tables.copy()
    inj = inject_all(world)
    return assemble(world, clean, inj, policy_doc(world))
