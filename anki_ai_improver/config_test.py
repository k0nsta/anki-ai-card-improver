import json
import stat
from pathlib import Path

import pytest

from anki_ai_improver.config import Settings, load_api_key, save_api_key
from anki_ai_improver.errors import AiError


def test_settings_defaults() -> None:
    settings = Settings.from_dict({"base_url": "https://example.test/v1", "model": "model"})

    assert settings.timeout_s == 60
    assert settings.shortcut == "Ctrl+Alt+J"
    assert settings.default_prompt == "default"
    assert settings.prompts["default"]
    assert settings.decks == {}


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
