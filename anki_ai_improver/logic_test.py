from anki_ai_improver.client import Proposal
from anki_ai_improver.logic import is_stale, merge_accepted
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
