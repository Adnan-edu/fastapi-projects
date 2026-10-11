"""Opaque cursor encoding for keyset pagination.

Big picture
-----------
A "cursor" is just a bookmark that says: *"the previous page ended at this exact
row — give me the rows immediately after it"*. For that to be unambiguous, the
bookmark needs to identify a single, well-defined position in the result set.

We paginate by the composite key `(created_at, id)`:
- `created_at` is the user-meaningful sort dimension (newest/oldest first).
- `id` is the tiebreaker that makes the order *total*. Two rows can share the
  same `created_at` second (especially during bulk inserts). Without a tiebreaker
  the cursor position would be ambiguous — "all rows at 14:12:31" is a set, not
  a point — and the same row could appear on two pages or get skipped entirely.

Cursor format
-------------
Wire format: base64url-encoded JSON, e.g. `eyJjIjoiMjAyNC0wOC0xNiIsImkiOjV9`.

We chose this shape deliberately:
1. **JSON inside** — trivially debuggable. Paste into `base64 -d` to inspect.
2. **base64url outside** — URL-safe (uses `-` and `_` instead of `+` and `/`),
   no need for clients to percent-encode it when echoing it back in a query string.
3. **Padding stripped** — shorter URLs; we re-add `=` padding on decode.
4. **Opaque** — clients are *not* supposed to parse or build cursors. They
   receive a string from one response and pass it verbatim to the next request.
   This lets us change the internal shape later (add fields, sign it with HMAC,
   compress it) without breaking clients.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime

from fastapi import HTTPException, status


@dataclass(frozen=True, slots=True)
class Cursor:
    """In-memory representation of a cursor position.

    `frozen=True`  — instances are immutable; safe to share across requests.
    `slots=True`   — skips `__dict__`, saving memory; minor perf win on creation.

    The two fields mirror the columns of our composite index `(created_at, id)`.
    Anything you store in a cursor MUST also appear in the index — otherwise the
    `WHERE (...) > (...)` comparison cannot do a B-tree seek and degrades to a
    sequential scan.
    """

    created_at: datetime
    id: int

    def encode(self) -> str:
        """Serialize this cursor position into a URL-safe opaque token.

        Steps:
        1. Build a small JSON object. Short keys (`c`, `i`) keep the encoded
           token short — cursors travel in query strings on every page request
           and there's no reason to spend bytes on prettiness.
        2. `separators=(",", ":")` strips the spaces that `json.dumps` would
           otherwise insert (`{"c": "..."}` vs `{"c":"..."}`). Saves a few bytes
           per cursor; matters when you're issuing millions of paginated
           requests per day.
        3. Encode to bytes (UTF-8) — base64 operates on bytes, not str.
        4. base64url-encode. The "url" variant replaces `+` → `-` and `/` → `_`
           so the cursor is safe to drop into a URL without percent-encoding.
        5. Strip trailing `=` padding. base64 always pads the output to a
           multiple of 4 characters; stripping it makes the token shorter and
           prettier. We re-add the padding on decode.
        6. Decode the bytes back to ASCII str — what FastAPI returns in JSON.
        """
        payload = json.dumps(
            {"c": self.created_at.isoformat(), "i": self.id},
            separators=(",", ":"),
        ).encode("utf-8")
        return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")

    @classmethod
    def decode(cls, raw: str) -> Cursor:
        """Parse an opaque cursor token back into a Cursor.

        This is the inverse of `encode`, plus *defensive validation*: clients
        can send any string here — typos, truncated tokens, deliberate junk —
        and we must respond with a clean 400, never a 500.

        Why every exception type is caught:
        - `ValueError`           — `b64decode` rejects non-base64 chars; also
                                   `datetime.fromisoformat` rejects bad timestamps;
                                   also `int(...)` rejects non-numeric strings.
        - `KeyError`             — JSON parsed but missing `"c"` or `"i"`.
        - `TypeError`            — `int(None)` if `"i"` is null, etc.
        - `json.JSONDecodeError` — payload decoded from base64 wasn't valid JSON.

        All of them collapse to the same 400 response with a generic message;
        we deliberately do NOT echo back the raw input or internal error
        details — that would be a tiny information-disclosure footgun.
        """
        try:
            # base64 requires the input length to be a multiple of 4. We
            # stripped padding on encode, so add it back here. The arithmetic
            # `-len(raw) % 4` yields the number of `=` chars needed
            # (0, 1, 2, or 3).
            padded = raw + "=" * (-len(raw) % 4)
            # urlsafe_b64decode accepts bytes; encoding to ASCII is fine because
            # base64url's alphabet is a strict subset of ASCII.
            payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
            return cls(
                # `fromisoformat` is the inverse of `isoformat()` used in encode.
                # It parses RFC 3339 / ISO 8601 timestamps. From Python 3.11+ it
                # accepts a much wider range including timezone offsets.
                created_at=datetime.fromisoformat(payload["c"]),
                # `int(...)` is defensive — even if the client somehow sends
                # `"i": "5"` instead of `"i": 5`, we still get a usable int.
                id=int(payload["i"]),
            )
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            # `from exc` preserves the original traceback in logs (useful when
            # debugging a real malformed-cursor incident) while the client just
            # sees the clean 400.
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid cursor.",
            ) from exc
