import json

from anki_ai_improver.config import Settings
from anki_ai_improver.prompts import (
    NoteSnapshot,
    build_fix_messages,
    build_messages,
    candidate_deck_ids,
    resolve_prompt,
)


def make_settings() -> Settings:
    return Settings(
        base_url="https://example.test/v1",
        model="model",
        default_prompt="default",
        prompts={
            "default": "Default instructions",
            "english": "English instructions",
            "child": "Child instructions",
        },
        decks={"10": "english", "20": "child", "30": "english"},
    )


def test_candidate_deck_ids_orders_grandchild_parent_and_root() -> None:
    assert candidate_deck_ids(30, [10, 20]) == [30, 20, 10]


def test_resolve_prompt_uses_exact_deck_mapping() -> None:
    assert resolve_prompt([30, 20, 10], make_settings()) == ("english", "English instructions")


def test_resolve_prompt_subdeck_inherits_parent_mapping() -> None:
    assert resolve_prompt([25, 20, 10], make_settings()) == ("child", "Child instructions")


def test_resolve_prompt_uses_nearest_mapped_parent() -> None:
    assert resolve_prompt([35, 20, 10], make_settings()) == ("child", "Child instructions")


def test_resolve_prompt_uses_default_when_unmapped() -> None:
    assert resolve_prompt([40, 41], make_settings()) == ("default", "Default instructions")


def test_resolve_prompt_uses_default_when_mapping_names_missing_prompt() -> None:
    settings = make_settings()
    settings.decks = {"30": "missing"}

    assert resolve_prompt([30], settings) == ("default", "Default instructions")


def test_build_messages_include_all_fields_and_generic_output_rules() -> None:
    snapshot = NoteSnapshot(
        note_id=1,
        mtime=2,
        card_id=3,
        note_type="Basic",
        deck_name="Portuguese",
        tags=["vocabulary"],
        fields={"Front": "Olá", "Back": "Hello"},
    )

    messages = build_messages("Fix errors", snapshot)

    assert messages[0]["role"] == "system"
    rules = messages[0]["content"].split("Output rules:\n", 1)[1]
    assert 'these note field names: ["Front", "Back"]' in rules
    assert "Anki HTML" in rules
    assert "Keep media references" in rules
    assert "Portuguese" not in rules
    assert "language" not in rules.lower()
    user_message = json.loads(messages[1]["content"])
    assert list(user_message["fields"]) == ["Front", "Back"]
    assert user_message == {
        "note_type": "Basic",
        "deck": "Portuguese",
        "tags": ["vocabulary"],
        "fields": {"Front": "Olá", "Back": "Hello"},
    }


def test_build_fix_messages_include_score_original_note_and_draft() -> None:
    snapshot = NoteSnapshot(
        note_id=1,
        mtime=2,
        card_id=3,
        note_type="Basic",
        deck_name="Portuguese",
        tags=["vocabulary"],
        fields={"Front": "Olá", "Back": "Hello"},
    )

    messages = build_fix_messages(
        "Fix errors",
        snapshot,
        {"Front": "Oi", "Back": "Hello there"},
        1.25,
    )

    assert "correctness 1.2/4" in messages[0]["content"]
    assert 'these note field names: ["Front", "Back"]' in messages[0]["content"]
    user_message = json.loads(messages[1]["content"])
    assert user_message["original_note"] == {
        "note_type": "Basic",
        "deck": "Portuguese",
        "tags": ["vocabulary"],
        "fields": {"Front": "Olá", "Back": "Hello"},
    }
    assert user_message["draft"] == {"Front": "Oi", "Back": "Hello there"}
