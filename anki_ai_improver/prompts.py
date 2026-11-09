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


def build_messages(prompt_text: str, snapshot: NoteSnapshot) -> list[dict[str, str]]:
    """Build the OpenAI-compatible system and user messages for one note."""
    contract = (
        'Return ONLY a JSON object {"fields": {<field name>: <html>}} using exactly '
        "the field names given. Keep HTML formatting and media references unchanged unless asked."
    )
    user_content = json.dumps(
        {
            "note_type": snapshot.note_type,
            "deck": snapshot.deck_name,
            "tags": snapshot.tags,
            "fields": snapshot.fields,
        },
        ensure_ascii=False,
    )
    return [
        {"role": "system", "content": f"{prompt_text}\n\n{contract}"},
        {"role": "user", "content": user_content},
    ]
