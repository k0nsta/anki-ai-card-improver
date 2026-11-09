from anki_ai_improver.client import Proposal
from anki_ai_improver.logic import (
    editor_mode,
    gate_status,
    is_stale,
    merge_accepted,
    review_shortcut,
    run_gate,
)
from anki_ai_improver.prompts import NoteSnapshot


def _snapshot() -> NoteSnapshot:
    return NoteSnapshot(
        note_id=10,
        mtime=100,
        card_id=20,
        note_type="Basic",
        deck_name="Default",
        tags=[],
        fields={"Front": "old front", "Back": "old back"},
    )


def test_merge_accepted_updates_only_selected_fields() -> None:
    fields = {"Front": "old front", "Back": "old back"}
    proposal = Proposal({"Front": "new front", "Back": "new back", "Unknown": "ignored"}, "")

    assert merge_accepted(fields, proposal, ["Back", "Unknown"]) == {
        "Front": "old front",
        "Back": "new back",
    }
    assert fields["Back"] == "old back"


def test_is_stale_when_note_was_deleted() -> None:
    assert is_stale(_snapshot(), None, None, 20)


def test_is_stale_when_mtime_changed() -> None:
    assert is_stale(_snapshot(), 10, 101, 20)


def test_is_stale_when_target_switched() -> None:
    assert is_stale(_snapshot(), 10, 100, 21)


def test_is_not_stale_when_snapshot_is_current() -> None:
    assert not is_stale(_snapshot(), 10, 100, 20)


def test_review_shortcut_uses_default() -> None:
    assert review_shortcut({}) == ("Ctrl+Alt+J", "Improve card with AI")


def test_review_shortcut_uses_custom_value() -> None:
    assert review_shortcut({"shortcut": "Alt+Shift+I"}) == (
        "Alt+Shift+I",
        "Improve card with AI",
    )


def test_review_shortcut_can_be_disabled() -> None:
    assert review_shortcut({"shortcut": ""}) is None


def test_editor_mode_combinations() -> None:
    assert editor_mode(False, False, False) == "disabled"
    assert editor_mode(False, True, False) == "update"
    assert editor_mode(False, False, True) == "fill_in_place"
    assert editor_mode(False, True, True) == "fill_in_place"
    assert editor_mode(True, False, False) == "disabled"
    assert editor_mode(True, True, False) == "update"
    assert editor_mode(True, False, True) == "disabled"
    assert editor_mode(True, True, True) == "disabled"


def test_gate_statuses() -> None:
    assert gate_status(False, True, None, False, None) == ""
    assert gate_status(True, False, None, False, None) == (
        "⚠ unchecked: quality gate needs OpenRouter"
    )
    assert gate_status(True, True, 3.0, False, None) == "✓ checked"
    assert gate_status(True, True, 1.0, True, None) == "✓ fixed after check"
    assert gate_status(True, True, None, False, ValueError("gate offline")) == (
        "⚠ unchecked: gate offline"
    )
    assert gate_status(True, True, 1.0, False, ValueError("fix offline")) == (
        "⚠ unchecked: fix offline"
    )


def test_run_gate_off_returns_draft_without_scoring() -> None:
    draft = Proposal({"Front": "draft"}, "raw")

    def score(_text: dict[str, str]) -> float:
        raise AssertionError("score should not be called")

    assert run_gate(draft, {}, score, lambda _score: draft, False, True, 2.5) is draft


def test_run_gate_unavailable_keeps_draft_with_status() -> None:
    draft = Proposal({"Front": "draft"}, "raw")

    result = run_gate(draft, {}, lambda _text: 4.0, lambda _score: draft, True, False, 2.5)

    assert result.changed == draft.changed
    assert result.status == "⚠ unchecked: quality gate needs OpenRouter"


def test_run_gate_pass_keeps_draft_as_checked() -> None:
    draft = Proposal({"Front": "draft"}, "raw")
    seen: list[dict[str, str]] = []

    def score(text: dict[str, str]) -> float:
        seen.append(text)
        return 3.0

    result = run_gate(
        draft,
        {"Front": "draft text"},
        score,
        lambda _score: Proposal({}, "fixed"),
        True,
        True,
        2.5,
    )

    assert seen == [{"Front": "draft text"}]
    assert result.changed == draft.changed
    assert result.status == "✓ checked"


def test_run_gate_low_score_uses_fix_result() -> None:
    fixed = Proposal({"Front": "fixed"}, "fixed raw")
    result = run_gate(
        Proposal({"Front": "draft"}, "raw"),
        {},
        lambda _text: 1.0,
        lambda score: fixed if score == 1.0 else Proposal({}, ""),
        True,
        True,
        2.5,
    )

    assert result.changed == fixed.changed
    assert result.status == "✓ fixed after check"


def test_run_gate_score_error_keeps_draft_unchecked() -> None:
    draft = Proposal({"Front": "draft"}, "raw")

    def fail(_text: dict[str, str]) -> float:
        raise RuntimeError("score failed")

    result = run_gate(draft, {}, fail, lambda _score: Proposal({}, ""), True, True, 2.5)

    assert result.changed == draft.changed
    assert result.status == "⚠ unchecked: score failed"


def test_run_gate_fix_error_keeps_draft_unchecked() -> None:
    draft = Proposal({"Front": "draft"}, "raw")

    def fail(_score: float) -> Proposal:
        raise RuntimeError("fix failed")

    result = run_gate(draft, {}, lambda _text: 1.0, fail, True, True, 2.5)

    assert result.changed == draft.changed
    assert result.status == "⚠ unchecked: fix failed"
