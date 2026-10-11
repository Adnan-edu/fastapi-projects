"""Deterministic idempotency keys derived from filter sets.

Same filters → same key → same output file path. This is what makes a
crashed-and-retried job safe: the second run finds the file already
written and returns it instead of duplicating work.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def idempotency_key(filters: dict[str, Any]) -> str:
    """Stable 16-char hex key from a normalized filter dict.

    Normalization rules:
    - ``None`` values are dropped (an explicit ``status=None`` is the
      same request as omitting ``status`` entirely).
    - Keys are sorted so ``{a, b}`` and ``{b, a}`` hash identically.
    - JSON is rendered with the most compact separators so whitespace
      differences in the caller can't change the key.
    """

    clean = {k: v for k, v in filters.items() if v is not None}
    canonical = json.dumps(clean, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]
