# services/feedback_fields.py
"""Shared user-feedback field helpers (no service imports — avoids circular deps)."""
from __future__ import annotations

from db.models import UserFeedback

TRADE_ENTRY_VALUES = frozenset({"ENTERED", "DID_NOT_TAKE"})
OUTCOME_VALUES = frozenset({"SUCCESSFUL", "FAILED", "DID_NOT_TAKE", "UNCLEAR"})
ALLOWED_FEEDBACK = TRADE_ENTRY_VALUES | OUTCOME_VALUES


def split_feedback_fields(row: UserFeedback | None) -> tuple[str | None, str | None]:
    """Return (trade_entry, outcome) with legacy single-column support."""
    if not row:
        return None, None
    trade_entry = row.trade_entry
    outcome = row.feedback
    if not trade_entry and outcome in TRADE_ENTRY_VALUES:
        return outcome, None
    return trade_entry, outcome


def effective_outcome_feedback(row: UserFeedback | None) -> str | None:
    """Outcome used for training cross-check (not trade entry)."""
    _, outcome = split_feedback_fields(row)
    return outcome
