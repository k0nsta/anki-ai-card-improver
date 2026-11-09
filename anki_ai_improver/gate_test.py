import pytest
import requests

from anki_ai_improver.config import Settings
from anki_ai_improver.errors import AiError
from anki_ai_improver.gate import card_text, decisions_url, needs_fix, score_correctness


class FakeResponse:
    def __init__(self, body: object, status_code: int = 200) -> None:
        self.body = body
        self.status_code = status_code

    def json(self) -> object:
        if isinstance(self.body, Exception):
            raise self.body
        return self.body


class FakeSession:
    def __init__(self, response: FakeResponse | Exception) -> None:
        self.response = response
        self.kwargs: dict[str, object] | None = None

    def post(self, url: str, **kwargs: object) -> FakeResponse:
        self.kwargs = {"url": url, **kwargs}
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _settings() -> Settings:
    return Settings(base_url="https://openrouter.ai/api/v1", model="chat-model")


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("https://openrouter.ai/api/v1", "https://openrouter.ai/api/alpha/decisions"),
        ("https://openrouter.ai/api/v1/", "https://openrouter.ai/api/alpha/decisions"),
        ("https://api.openrouter.ai/api/v1", "https://openrouter.ai/api/alpha/decisions"),
        ("https://example.test/api/v1", None),
    ],
)
def test_decisions_url(base_url: str, expected: str | None) -> None:
    assert decisions_url(base_url) == expected


def test_score_correctness_posts_expected_question_and_parses_score() -> None:
    session = FakeSession(FakeResponse({"answers": {"correctness": {"score": 3.25}}}))

    score = score_correctness(
        _settings(), "secret", {"Front": "A card"}, "Basic", "Biology", session
    )

    assert score == 3.25
    assert session.kwargs == {
        "url": "https://openrouter.ai/api/alpha/decisions",
        "headers": {"Authorization": "Bearer secret"},
        "json": {
            "model": "typesafe/jev-1.14",
            "state": {"fields": {"Front": "A card"}, "note_type": "Basic", "deck": "Biology"},
            "questions": {
                "correctness": {
                    "type": "score",
                    "instructions": "How correct is this flashcard: facts, language, translations, code and formulas, with no self-contradictions?",
                    "criteria": [
                        "several clear errors",
                        "one or two clear errors",
                        "minor issues",
                        "essentially correct, small awkwardness",
                        "fully correct and natural",
                    ],
                }
            },
        },
        "timeout": 60,
    }


@pytest.mark.parametrize(
    ("response", "kind"),
    [
        (FakeResponse({}, status_code=401), "auth"),
        (FakeResponse({}, status_code=429), "rate_limit"),
        (FakeResponse({}, status_code=503), "server"),
        (FakeResponse({}, status_code=400), "bad_response"),
        (FakeResponse(ValueError("bad json")), "bad_response"),
        (FakeResponse({"answers": {"correctness": {"score": "4"}}}), "bad_response"),
        (FakeResponse({"answers": {"correctness": {"score": 5}}}), "bad_response"),
        (requests.Timeout("slow"), "timeout"),
        (requests.ConnectionError("offline"), "network"),
        (requests.RequestException("failed"), "network"),
    ],
)
def test_score_correctness_maps_errors(response: FakeResponse | Exception, kind: str) -> None:
    session = FakeSession(response)

    with pytest.raises(AiError) as error:
        score_correctness(_settings(), "secret", {}, "Basic", "Biology", session)

    assert error.value.kind == kind


@pytest.mark.parametrize(
    ("score", "minimum", "expected"),
    [(0, 2.5, True), (2.49, 2.5, True), (2.5, 2.5, False), (4, 2.5, False)],
)
def test_needs_fix_boundaries(score: float, minimum: float, expected: bool) -> None:
    assert needs_fix(score, minimum) is expected


def test_card_text_strips_html_and_turns_br_into_newline() -> None:
    assert card_text({"Front": "<p>Hello<br/>world &amp; more</p>", "Back": "<b>Answer</b>"}) == {
        "Front": "Hello\nworld & more",
        "Back": "Answer",
    }
