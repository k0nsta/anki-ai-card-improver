"""Configuration parsing and API key storage for the add-on."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import AiError

_DEFAULT_PROMPTS = {
    "default": (
        "Fix factual and spelling errors, make the card clearer and more concise. "
        "Keep the language of each field."
    )
}


@dataclass
class Settings:
    base_url: str
    model: str
    timeout_s: int = 60
    shortcut: str = "Ctrl+Alt+J"
    default_prompt: str = "default"
    prompts: dict[str, str] = field(default_factory=lambda: _DEFAULT_PROMPTS.copy())
    decks: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "Settings":
        """Build settings from Anki's add-on config, requiring endpoint and model."""
        base_url = values.get("base_url")
        model = values.get("model")
        if not isinstance(base_url, str) or not base_url:
            raise AiError("no_config", "Missing base_url in add-on config")
        if not isinstance(model, str) or not model:
            raise AiError("no_config", "Missing model in add-on config")

        return cls(
            base_url=base_url,
            model=model,
            timeout_s=values.get("timeout_s", 60),
            shortcut=values.get("shortcut", "Ctrl+Alt+J"),
            default_prompt=values.get("default_prompt", "default"),
            prompts=values.get("prompts", _DEFAULT_PROMPTS.copy()),
            decks=values.get("decks", {}),
        )


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
