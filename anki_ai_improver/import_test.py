import sys

import anki_ai_improver
from anki_ai_improver import config, errors, prompts


def test_package_imports_without_aqt() -> None:
    assert anki_ai_improver is not None
    assert errors.AiError is not None
    assert config.Settings is not None
    assert prompts.NoteSnapshot is not None
    assert "aqt" not in sys.modules
