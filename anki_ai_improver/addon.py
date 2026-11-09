"""Anki-specific shared flow for requesting and reviewing improvements."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from anki.errors import NotFoundError
from aqt import mw
from aqt.operations import QueryOp
from aqt.qt import QDialog, QMessageBox, QTextBrowser, QVBoxLayout

from .client import Proposal, complete, parse_proposal
from .config import Settings, load_api_key
from .dialog import DiffDialog
from .errors import AiError
from .prompts import NoteSnapshot, build_messages, resolve_prompt
from .settings import register_settings, show_settings


def _addon_name() -> str:
    return mw.addonManager.addonFromModule(__name__)


def _load_settings() -> Settings:
    values = mw.addonManager.getConfig(_addon_name())
    if not isinstance(values, dict):
        raise AiError("no_config", "Add-on configuration is missing")
    return Settings.from_dict(values)


def _show_error(error: Exception) -> None:
    if isinstance(error, AiError) and error.kind == "bad_response":
        dialog = QDialog(mw)
        dialog.setWindowTitle("AI service returned an invalid response")
        browser = QTextBrowser(dialog)
        browser.setPlainText(error.message)
        layout = QVBoxLayout(dialog)
        layout.addWidget(browser)
        dialog.resize(640, 400)
        dialog.exec()
        return
    QMessageBox.warning(mw, "AI Card Improver", str(error))


def _current_state(snapshot: NoteSnapshot) -> tuple[int | None, int | None, int | None]:
    try:
        note = mw.col.get_note(snapshot.note_id)
    except NotFoundError:
        return None, None, None
    if note is None:
        return None, None, None
    current_target_id = snapshot.card_id
    reviewer = getattr(mw, "reviewer", None)
    card = getattr(reviewer, "card", None)
    if card is not None:
        current_target_id = getattr(card, "id", None)
    return note.id, note.mod, current_target_id


def improve(
    parent: Any,
    snapshot: NoteSnapshot,
    candidate_deck_ids: list[int],
    apply: Callable[[dict[str, str]], None],
) -> None:
    """Request a proposal, then show a guarded field-by-field review dialog."""
    try:
        settings = _load_settings()
        api_key = load_api_key(Path(__file__).parent / "user_files")
        if not api_key:
            show_settings(parent)
            return
    except AiError:
        show_settings(parent)
        return

    prompt_name, prompt_text = resolve_prompt(candidate_deck_ids, settings)

    def present(proposal: Proposal, selected_prompt: str) -> None:
        def retry(name: str, receive: Callable[[Proposal], None]) -> None:
            selected_text = settings.prompts.get(
                name, settings.prompts.get(settings.default_prompt, "")
            )

            def done(result: Proposal) -> None:
                receive(result)

            _run_request(parent, snapshot, settings, api_key, selected_text, done)

        dialog = DiffDialog(
            parent,
            snapshot,
            proposal,
            selected_prompt,
            list(settings.prompts),
            retry,
            apply,
            lambda: _current_state(snapshot),
        )
        dialog.exec()

    def on_success(proposal: Proposal) -> None:
        present(proposal, prompt_name)

    _run_request(parent, snapshot, settings, api_key, prompt_text, on_success)


def _run_request(
    parent: Any,
    snapshot: NoteSnapshot,
    settings: Settings,
    api_key: str,
    prompt_text: str,
    on_success: Callable[[Proposal], None],
) -> None:
    messages = build_messages(prompt_text, snapshot)

    def op(_collection: Any) -> Proposal:
        response = complete(settings, api_key, messages)
        return parse_proposal(response, snapshot.fields)

    (
        QueryOp(parent=parent, op=op, success=on_success)
        .without_collection()
        .failure(_show_error)
        .with_progress()
        .run_in_background()
    )


register_settings()
