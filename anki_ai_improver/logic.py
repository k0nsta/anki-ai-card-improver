"""Pure helpers shared by the add-on's UI flows."""

from collections.abc import Iterable, Mapping

from .client import Proposal
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
