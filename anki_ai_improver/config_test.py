import json
import stat
from pathlib import Path
from typing import Any

import pytest

from anki_ai_improver.config import (
    Settings,
    add_prompt,
    delete_prompt,
    load_api_key,
    migrate_config,
    remove_deck_prompt,
    rename_prompt,
    save_api_key,
    set_deck_prompt,
)
from anki_ai_improver.errors import AiError


def test_settings_defaults() -> None:
    settings = Settings.from_dict({"base_url": "https://example.test/v1", "model": "model"})

    assert settings.timeout_s == 60
    assert settings.shortcut == "Ctrl+Alt+J"
    assert settings.default_prompt == "default"
    assert settings.prompts["default"]
    assert settings.decks == {}
    assert settings.gate_enabled is False
    assert settings.gate_model == "typesafe/jev-1.14"
    assert settings.gate_min_correctness == 2.5


def test_default_prompt_matches_config_json() -> None:
    config_path = Path(__file__).with_name("config.json")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    settings = Settings.from_dict({"base_url": "url", "model": "model"})

    assert settings.prompts["default"] == config["prompts"]["default"]


def test_migrate_config_replaces_untouched_prompt() -> None:
    values: dict[str, Any] = {
        "model": "custom/model",
        "prompts": {
            "default": (
                "Fix factual and spelling errors, make the card clearer and more concise. "
                "Keep the language of each field."
            )
        },
    }

    migrated, changed = migrate_config(values)

    assert changed is True
    assert (
        migrated["prompts"]["default"]
        == Settings.from_dict({"base_url": "url", "model": "model"}).prompts["default"]
    )
    assert values["prompts"]["default"] != migrated["prompts"]["default"]


def test_migrate_config_keeps_edited_prompt() -> None:
    values = {"prompts": {"default": "My edited prompt"}}

    migrated, changed = migrate_config(values)

    assert migrated == values
    assert changed is False


def test_migrate_config_replaces_old_model() -> None:
    migrated, changed = migrate_config({"model": "anthropic/claude-sonnet-5-5"})

    assert migrated["model"] == "openai/gpt-6-luna"
    assert changed is True


def test_migrate_config_keeps_other_model() -> None:
    values = {"model": "provider/custom"}

    migrated, changed = migrate_config(values)

    assert migrated == values
    assert changed is False


def test_migrate_config_already_migrated_is_unchanged() -> None:
    values = json.loads(Path(__file__).with_name("config.json").read_text(encoding="utf-8"))

    migrated, changed = migrate_config(values)

    assert migrated == values
    assert changed is False


@pytest.mark.parametrize("minimum", ["3", -1, 5])
def test_settings_invalid_gate_minimum_falls_back(minimum: object) -> None:
    settings = Settings.from_dict(
        {
            "base_url": "https://example.test/v1",
            "model": "model",
            "gate_min_correctness": minimum,
        }
    )

    assert settings.gate_min_correctness == 2.5


@pytest.mark.parametrize("missing", ["base_url", "model"])
def test_settings_reject_missing_required_fields(missing: str) -> None:
    values = {"base_url": "https://example.test/v1", "model": "model"}
    del values[missing]

    with pytest.raises(AiError) as error:
        Settings.from_dict(values)

    assert error.value.kind == "no_config"


def test_api_key_round_trip_and_permissions(tmp_path: Path) -> None:
    user_files = tmp_path / "user_files"

    save_api_key(user_files, "secret-value")

    secret_path = user_files / "secret.json"
    assert load_api_key(user_files) == "secret-value"
    assert stat.S_IMODE(secret_path.stat().st_mode) == 0o600
    assert json.loads(secret_path.read_text(encoding="utf-8")) == {"api_key": "secret-value"}


def test_load_api_key_returns_none_for_absent_or_corrupt_file(tmp_path: Path) -> None:
    user_files = tmp_path / "user_files"
    assert load_api_key(user_files) is None

    user_files.mkdir()
    (user_files / "secret.json").write_text("{invalid", encoding="utf-8")
    assert load_api_key(user_files) is None


def test_save_api_key_creates_missing_user_files(tmp_path: Path) -> None:
    user_files = tmp_path / "missing" / "user_files"

    save_api_key(user_files, "secret-value")

    assert user_files.is_dir()
    assert load_api_key(user_files) == "secret-value"


def test_add_prompt_rejects_duplicate_name() -> None:
    settings = Settings(
        base_url="https://example.test/v1",
        model="model",
        prompts={"default": "Keep it clear."},
    )

    with pytest.raises(ValueError, match="already exists"):
        add_prompt(settings, "default", "Another prompt")


def test_rename_prompt_updates_deck_mappings_and_default() -> None:
    settings = Settings(
        base_url="https://example.test/v1",
        model="model",
        default_prompt="old",
        prompts={"default": "Default", "old": "Prompt"},
        decks={"10": "old", "20": "default"},
    )

    renamed = rename_prompt(settings, "old", "new")

    assert renamed.prompts == {"default": "Default", "new": "Prompt"}
    assert renamed.decks == {"10": "new", "20": "default"}
    assert renamed.default_prompt == "new"
    assert settings.default_prompt == "old"


def test_delete_prompt_refuses_default() -> None:
    settings = Settings(base_url="url", model="model")

    with pytest.raises(ValueError, match="default prompt"):
        delete_prompt(settings, "default")


def test_delete_prompt_clears_deck_mappings() -> None:
    settings = Settings(
        base_url="url",
        model="model",
        prompts={"default": "Default", "other": "Other"},
        decks={"10": "other", "20": "default"},
    )

    deleted = delete_prompt(settings, "other")

    assert deleted.prompts == {"default": "Default"}
    assert deleted.decks == {"20": "default"}


def test_set_replace_and_remove_deck_prompt_mapping() -> None:
    settings = Settings(
        base_url="url",
        model="model",
        prompts={"default": "Default", "other": "Other"},
    )

    mapped = set_deck_prompt(settings, 10, "default")
    replaced = set_deck_prompt(mapped, "10", "other")
    removed = remove_deck_prompt(replaced, 10)

    assert mapped.decks == {"10": "default"}
    assert replaced.decks == {"10": "other"}
    assert removed.decks == {}
    assert settings.decks == {}


def test_set_deck_prompt_rejects_unknown_prompt() -> None:
    settings = Settings(base_url="url", model="model")

    with pytest.raises(ValueError, match="Unknown prompt"):
        set_deck_prompt(settings, 10, "missing")
