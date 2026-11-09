"""Pure helpers and client for the optional card correctness quality gate."""

import math
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit

import requests

from .config import Settings
from .errors import AiError

_CORRECTNESS_QUESTION = {
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


def decisions_url(base_url: str) -> str | None:
    """Return the OpenRouter Decisions endpoint when the configured host supports it."""
    try:
        hostname = urlsplit(base_url).hostname
    except ValueError:
        return None
    if hostname is None or not (hostname == "openrouter.ai" or hostname.endswith(".openrouter.ai")):
        return None
    return "https://openrouter.ai/api/alpha/decisions"


def score_correctness(
    settings: Settings,
    api_key: str,
    snapshot_fields_text: dict[str, str],
    note_type: str,
    deck: str,
    session: Any = requests,
) -> float:
    """Ask the Decisions API to score a card's correctness on its 0–4 rubric."""
    url = decisions_url(settings.base_url)
    if url is None:
        raise AiError("bad_response", "The quality gate requires an OpenRouter endpoint")

    payload = {
        "model": settings.gate_model,
        "state": {
            "fields": snapshot_fields_text,
            "note_type": note_type,
            "deck": deck,
        },
        "questions": {"correctness": dict(_CORRECTNESS_QUESTION)},
    }
    try:
        response = session.post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=settings.timeout_s,
        )
    except requests.Timeout as error:
        raise AiError("timeout", "The quality check timed out") from error
    except requests.ConnectionError as error:
        raise AiError("network", "Could not connect to the quality check service") from error
    except requests.RequestException as error:
        raise AiError("network", "The quality check request failed") from error

    status = response.status_code
    if status in (401, 403):
        raise AiError("auth", "The quality check service rejected the API key")
    if status == 429:
        raise AiError("rate_limit", "The quality check service rate limit was reached")
    if 500 <= status <= 599:
        raise AiError("server", f"The quality check service returned HTTP {status}")
    if status >= 400:
        raise AiError("bad_response", f"The quality check service returned HTTP {status}")

    try:
        result = response.json()
    except (ValueError, requests.exceptions.JSONDecodeError) as error:
        raise AiError("bad_response", "The quality check returned invalid JSON") from error
    if not isinstance(result, dict):
        raise AiError("bad_response", "The quality check returned an invalid response")
    answers = result.get("answers")
    answer = answers.get("correctness") if isinstance(answers, dict) else None
    score = answer.get("score") if isinstance(answer, dict) else None
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise AiError("bad_response", "The quality check returned no numeric correctness score")
    if not math.isfinite(score) or not 0 <= score <= 4:
        raise AiError(
            "bad_response", "The quality check returned an out-of-range correctness score"
        )
    return float(score)


def needs_fix(score: float, minimum: float) -> bool:
    """Return whether a score below the configured threshold needs a fix pass."""
    return score < minimum


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "br":
            self.parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def card_text(fields: dict[str, str]) -> dict[str, str]:
    """Strip markup from each field, translating HTML line breaks to newlines."""
    plain: dict[str, str] = {}
    for name, value in fields.items():
        parser = _TextExtractor()
        parser.feed(value)
        parser.close()
        plain[name] = "".join(parser.parts)
    return plain
