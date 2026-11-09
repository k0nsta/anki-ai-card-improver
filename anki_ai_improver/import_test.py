import sys

import anki_ai_improver
from anki_ai_improver import errors


def test_package_imports_without_aqt() -> None:
    assert anki_ai_improver is not None
    assert errors.AiError is not None
    assert "aqt" not in sys.modules
