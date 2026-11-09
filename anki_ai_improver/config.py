"""Configuration parsing and API key storage for the add-on."""

import json
import math
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .errors import AiError

_GENERIC_PROMPT = """You improve one Anki flashcard for spaced repetition. The deck can be about anything (a language, history, medicine, programming...): infer the subject and the card's direction from its current content.

- Keep the card's purpose, direction, language(s) and field roles. Do not turn it into a different card.
- Never drop content in another language or notation (translations, transcriptions/IPA, formulas, code); fix it instead.
- Keep the spelling variety already used (British/American, European/Brazilian Portuguese...).
- Front: one clear cue that makes the learner recall a single answer; it must not contain that answer.
- Back: the answer first, short and precise; then only the detail needed to remember and understand it.
- Extra fields (examples, notes, sources): keep their role; fix, tighten, and add one concrete example or mnemonic only if it really helps recall.
- Fix factual, spelling and grammar errors. Never invent facts; if unsure, keep the original wording.
- Concise and readable on a phone: short lines, no filler, no repetition between fields.
- If the card tries to teach several things, keep the core one and end the last field with `MORE CARDS: <topic>, <topic>`."""
_DEFAULT_PROMPTS = {"default": _GENERIC_PROMPT}
_OLD_DEFAULT_PROMPT = (
    "Fix factual and spelling errors, make the card clearer and more concise. "
    "Keep the language of each field."
)
_OLD_DEFAULT_MODEL = "anthropic/claude-sonnet-5-5"
_DEFAULT_MODEL = "openai/gpt-6-luna"
_DEFAULT_GATE_MODEL = "typesafe/jev-1.14"
_DEFAULT_GATE_MIN_CORRECTNESS = 2.5


def migrate_config(values: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Migrate only untouched legacy defaults without mutating the input."""
    migrated = values.copy()
    changed = False
    prompts = values.get("prompts")
    if isinstance(prompts, dict) and prompts.get("default") == _OLD_DEFAULT_PROMPT:
        migrated["prompts"] = prompts.copy()
        migrated["prompts"]["default"] = _GENERIC_PROMPT
        changed = True
    if values.get("model") == _OLD_DEFAULT_MODEL:
        migrated["model"] = _DEFAULT_MODEL
        changed = True
    return migrated, changed


@dataclass
class Settings:
    base_url: str
    model: str
    timeout_s: int = 60
    shortcut: str = "Ctrl+Alt+J"
    default_prompt: str = "default"
    prompts: dict[str, str] = field(default_factory=lambda: _DEFAULT_PROMPTS.copy())
    decks: dict[str, str] = field(default_factory=dict)
    gate_enabled: bool = False
    gate_model: str = _DEFAULT_GATE_MODEL
    gate_min_correctness: float = _DEFAULT_GATE_MIN_CORRECTNESS

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "Settings":
        """Build settings from Anki's add-on config, requiring endpoint and model."""
        base_url = values.get("base_url")
        model = values.get("model")
        if not isinstance(base_url, str) or not base_url:
            raise AiError("no_config", "Missing base_url in add-on config")
        if not isinstance(model, str) or not model:
            raise AiError("no_config", "Missing model in add-on config")

        gate_min_correctness = values.get("gate_min_correctness", _DEFAULT_GATE_MIN_CORRECTNESS)
        if (
            isinstance(gate_min_correctness, bool)
            or not isinstance(gate_min_correctness, (int, float))
            or not math.isfinite(float(gate_min_correctness))
            or not 0 <= gate_min_correctness <= 4
        ):
            gate_min_correctness = _DEFAULT_GATE_MIN_CORRECTNESS

        return cls(
            base_url=base_url,
            model=model,
            timeout_s=values.get("timeout_s", 60),
            shortcut=values.get("shortcut", "Ctrl+Alt+J"),
            default_prompt=values.get("default_prompt", "default"),
            prompts=values.get("prompts", _DEFAULT_PROMPTS.copy()),
            decks=values.get("decks", {}),
            gate_enabled=values.get("gate_enabled", False),
            gate_model=values.get("gate_model", _DEFAULT_GATE_MODEL),
            gate_min_correctness=float(gate_min_correctness),
        )


def add_prompt(settings: Settings, name: str, text: str) -> Settings:
    """Return settings with a new named prompt."""
    name = name.strip()
    if not name:
        raise ValueError("Prompt name cannot be empty")
    if name in settings.prompts:
        raise ValueError(f"Prompt already exists: {name}")
    prompts = settings.prompts.copy()
    prompts[name] = text
    return replace(settings, prompts=prompts)


def rename_prompt(settings: Settings, old_name: str, new_name: str) -> Settings:
    """Rename a prompt and update every reference to it."""
    new_name = new_name.strip()
    if old_name not in settings.prompts:
        raise ValueError(f"Unknown prompt: {old_name}")
    if not new_name:
        raise ValueError("Prompt name cannot be empty")
    if new_name != old_name and new_name in settings.prompts:
        raise ValueError(f"Prompt already exists: {new_name}")
    prompts = settings.prompts.copy()
    prompts[new_name] = prompts.pop(old_name)
    decks = {
        deck_id: new_name if prompt_name == old_name else prompt_name
        for deck_id, prompt_name in settings.decks.items()
    }
    default_prompt = new_name if settings.default_prompt == old_name else settings.default_prompt
    return replace(settings, prompts=prompts, decks=decks, default_prompt=default_prompt)


def delete_prompt(settings: Settings, name: str) -> Settings:
    """Delete a non-default prompt and any deck mappings that use it."""
    if name == settings.default_prompt:
        raise ValueError("Cannot delete the default prompt")
    if name not in settings.prompts:
        raise ValueError(f"Unknown prompt: {name}")
    prompts = settings.prompts.copy()
    del prompts[name]
    decks = {
        deck_id: prompt_name
        for deck_id, prompt_name in settings.decks.items()
        if prompt_name != name
    }
    return replace(settings, prompts=prompts, decks=decks)


def set_deck_prompt(settings: Settings, deck_id: int | str, prompt_name: str) -> Settings:
    """Set or replace the prompt assigned to a deck."""
    if prompt_name not in settings.prompts:
        raise ValueError(f"Unknown prompt: {prompt_name}")
    decks = settings.decks.copy()
    decks[str(deck_id)] = prompt_name
    return replace(settings, decks=decks)


def remove_deck_prompt(settings: Settings, deck_id: int | str) -> Settings:
    """Remove a deck's prompt assignment if one exists."""
    decks = settings.decks.copy()
    decks.pop(str(deck_id), None)
    return replace(settings, decks=decks)


def load_api_key(user_files: Path) -> str | None:
    """Read the API key from user_files/secret.json, returning None if unavailable."""
    try:
        data = json.loads((user_files / "secret.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    api_key = data.get("api_key")
    return api_key if isinstance(api_key, str) else None


def save_api_key(user_files: Path, api_key: str) -> None:
    """Write the API key with owner-only permissions, creating user_files as needed."""
    user_files.mkdir(parents=True, exist_ok=True)
    secret_path = user_files / "secret.json"
    descriptor = os.open(secret_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as secret_file:
        json.dump({"api_key": api_key}, secret_file)
        secret_file.write("\n")
    secret_path.chmod(0o600)
