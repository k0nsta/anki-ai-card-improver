"""Prompt selection and chat message construction."""

import json
from dataclasses import dataclass

from .config import Settings


def candidate_deck_ids(current_did: int, parent_ids_root_first: list[int]) -> list[int]:
    """Return the current deck followed by its parents, nearest parent first."""
    return [current_did, *reversed(parent_ids_root_first)]


def resolve_prompt(candidate_deck_ids: list[int], settings: Settings) -> tuple[str, str]:
    """Choose the closest deck prompt that exists, or the configured default."""
    for deck_id in candidate_deck_ids:
        prompt_name = settings.decks.get(str(deck_id))
        if prompt_name is not None and prompt_name in settings.prompts:
            return prompt_name, settings.prompts[prompt_name]

    default_name = settings.default_prompt
    if default_name in settings.prompts:
        return default_name, settings.prompts[default_name]
    return default_name, settings.prompts.get("default", "")


@dataclass
class NoteSnapshot:
    """Values copied from the note and card before the background request."""

    note_id: int
    mtime: int
    card_id: int
    note_type: str
    deck_name: str
    tags: list[str]
    fields: dict[str, str]


def _output_rules(field_names: list[str]) -> str:
    """Return generic output instructions constrained to this note's fields."""
    names = json.dumps(field_names, ensure_ascii=False)
    return (
        "Output rules:\n"
        f'- Return {{"fields": {{...}}}} with exactly these note field names: {names}; '
        "each value is that field's full new content.\n"
        "- Field content is Anki HTML: use <br> for line breaks and <br><br> between blocks; "
        "do not use Markdown, code fences, or literal newlines.\n"
        "- Keep media references ([sound:...], <img ...>) unchanged.\n"
        "- The note's current content is the topic; improve it according to the instructions above."
    )


def _original_note(snapshot: NoteSnapshot) -> dict[str, object]:
    return {
        "note_type": snapshot.note_type,
        "deck": snapshot.deck_name,
        "tags": snapshot.tags,
        "fields": snapshot.fields,
    }


def build_messages(prompt_text: str, snapshot: NoteSnapshot) -> list[dict[str, str]]:
    """Build the OpenAI-compatible system and user messages for one note."""
    user_content = json.dumps(_original_note(snapshot), ensure_ascii=False)
    return [
        {"role": "system", "content": f"{prompt_text}\n\n{_output_rules(list(snapshot.fields))}"},
        {"role": "user", "content": user_content},
    ]


def build_fix_messages(
    prompt_text: str,
    snapshot: NoteSnapshot,
    draft_fields: dict[str, str],
    score: float,
) -> list[dict[str, str]]:
    """Build messages asking the model to repair a quality-gated draft."""
    fix_instructions = (
        f"An automatic quality check rated this card's correctness {score:.1f}/4. "
        "Find and fix factual, language and translation errors; keep everything that is correct."
    )
    user_content = json.dumps(
        {"original_note": _original_note(snapshot), "draft": draft_fields},
        ensure_ascii=False,
    )
    return [
        {
            "role": "system",
            "content": f"{prompt_text}\n\n{fix_instructions}\n\n{_output_rules(list(snapshot.fields))}",
        },
        {"role": "user", "content": user_content},
    ]
