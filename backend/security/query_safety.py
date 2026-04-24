"""
Query-safety helpers — defense against:
  - ReDoS (catastrophic backtracking in MongoDB $regex)
  - Regex syntax injection (e.g. `[`, `(`, `\\Q`) crashing the driver with 500 ISE
  - Anchor / wildcard enumeration (`?q=^a`, `?q=.*`) that turns a "search" into
    a full-collection enum the UI never intended
  - Unicode normalize bypass (`"alice"` vs fullwidth `"ＡＬＩＣＥ"`)

`safe_search_term()` returns a `re.escape`-d, NFKC-normalized, length-capped
string ready to drop into `{"$regex": ..., "$options": "i"}`. Returns None for
empty/None/all-whitespace input so callers can skip adding the filter.

The escaped output behaves as a *literal substring* match — exactly what the
"search box" UX promises.
"""

from __future__ import annotations

import re
import unicodedata

# 64 chars is enough for any realistic name/email/code search and bounds the
# worst-case regex compile/scan cost.
DEFAULT_MAX_LEN = 64


def safe_search_term(raw: str | None, *, max_len: int = DEFAULT_MAX_LEN) -> str | None:
    """Sanitize user-supplied search input for use as a MongoDB regex pattern.

    Returns a `re.escape`-d, NFKC-normalized literal substring, or None when
    the input is empty / whitespace-only after normalization.
    """
    if raw is None:
        return None
    s = unicodedata.normalize("NFKC", str(raw)).strip()
    if not s:
        return None
    if len(s) > max_len:
        s = s[:max_len]
    return re.escape(s)
