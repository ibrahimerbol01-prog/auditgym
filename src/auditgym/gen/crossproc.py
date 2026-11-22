"""Child process of the cross-process reproducibility check (C4): print the SHA-256 of one generated episode.

Run as ``python -m auditgym.gen.crossproc SEED CONFIG_JSON``. A named module rather than ``python -c``, so the packaged
desktop app (whose executable runs only known modules) can repeat the check too.
"""
from __future__ import annotations

import hashlib
import json
import sys

from .build import generate


def main(argv: list) -> int:
    seed, config = int(argv[0]), json.loads(argv[1])
    print(hashlib.sha256(json.dumps(generate(seed, config), sort_keys=True).encode()).hexdigest())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
