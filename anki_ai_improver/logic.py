"""Pure helpers shared by the add-on's UI flows."""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import replace

from .client import Proposal
from .gate import needs_fix
from .prompts import NoteSnapshot


def editor_mode(is_new_editor: bool, has_note_in_col: bool, is_add_window: bool) -> str:
    """Choose how an editor button can safely apply accepted suggestions."""
    if is_add_window:
        return "disabled" if is_new_editor else "fill_in_place"
    if has_note_in_col:
        return "update"
    return "disabled"


def review_shortcut(config: Mapping[str, object]) -> tuple[str, str] | None:
    """Return the configured reviewer shortcut and its menu label, if enabled."""
    shortcut = config.get("shortcut", "Ctrl+Alt+J")
    if not isinstance(shortcut, str) or not shortcut.strip():
        return None
    return shortcut, "Improve card with AI"


def merge_accepted(
    fields: dict[str, str], proposal: Proposal, accepted_names: Iterable[str]
) -> dict[str, str]:
    """Return a copy of fields with only the accepted proposal values applied."""
    accepted = set(accepted_names)
    merged = fields.copy()
    for name, value in proposal.changed.items():
        if name in accepted and name in merged:
            merged[name] = value
    return merged


def is_stale(
    snapshot: NoteSnapshot,
    current_note_id: int | None,
    current_mtime: int | None,
    current_target_id: int | None,
) -> bool:
    """Check whether the note or selected card changed while a request ran."""
    return (
        current_note_id is None
        or current_mtime is None
        or current_target_id is None
        or current_note_id != snapshot.note_id
        or current_mtime != snapshot.mtime
        or current_target_id != snapshot.card_id
    )


def gate_status(
    enabled: bool,
    available: bool,
    score: float | None,
    fixed: bool,
    error: Exception | str | None,
) -> str:
    """Return the concise quality-gate status shown alongside a proposal."""
    if not enabled:
        return ""
    if not available:
        return "⚠ unchecked: quality gate needs OpenRouter"
    if error is not None:
        reason = getattr(error, "message", str(error))
        return f"⚠ unchecked: {reason}"
    if fixed:
        return "✓ fixed after check"
    if score is not None:
        return "✓ checked"
    return ""


def run_gate(
    draft: Proposal,
    merged_text: dict[str, str],
    score_fn: Callable[[dict[str, str]], float],
    fix_fn: Callable[[float], Proposal],
    enabled: bool,
    available: bool,
    minimum: float,
) -> Proposal:
    """Score a draft and optionally repair it, preserving drafts on gate errors."""
    if not enabled:
        return draft
    if not available:
        return replace(draft, status=gate_status(True, False, None, False, None))

    try:
        score = score_fn(merged_text)
    except Exception as error:  # noqa: BLE001 - gate failures must preserve the draft
        return replace(draft, status=gate_status(True, True, None, False, error))

    if not needs_fix(score, minimum):
        return replace(draft, status=gate_status(True, True, score, False, None))

    try:
        fixed_draft = fix_fn(score)
    except Exception as error:  # noqa: BLE001 - fix failures must preserve the draft
        return replace(draft, status=gate_status(True, True, score, False, error))
    return replace(fixed_draft, status=gate_status(True, True, score, True, None))
