"""Small Supabase / PostgREST helpers shared across the pipeline."""

from __future__ import annotations

from typing import Any


def maybe_one(query: Any) -> dict | None:
    """Run a PostgREST query expecting at most one row; return the row dict or None.

    Pass the query builder WITHOUT a trailing ``.maybe_single()`` /
    ``.execute()`` / ``.data`` — this helper appends them.

    Why this exists: some supabase-py / postgrest versions return ``None`` from
    ``.maybe_single().execute()`` (rather than a response object with
    ``data == None``) when no row matches. Chaining ``.data`` onto that then raises
    ``AttributeError: 'NoneType' object has no attribute 'data'`` — which crashes
    on any lookup against an empty table (e.g. the first backfill of a channel).
    Centralising the call makes every 0-or-1-row lookup safe regardless of version.
    """
    resp = query.maybe_single().execute()
    return resp.data if resp is not None else None
