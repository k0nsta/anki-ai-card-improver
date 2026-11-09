import json
from typing import Any

import pytest
import requests

from anki_ai_improver.client import Proposal, complete, normalise_field, parse_proposal
from anki_ai_improver.config import Settings
from anki_ai_improver.errors import AiError


class FakeResponse:
    def __init__(self, status_code: int = 200, body: Any = None, text: str = "") -> None:
        self.status_code = status_code
        self._body = body
        self.text = text or json.dumps(body)

    def json(self) -> Any:
        return self._body


class FakeSession:
    def __init__(self, *responses: Any) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> Any:
        self.calls.append({"url": url, **kwargs})
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _settings(base_url: str = "https://example.test/v1/") -> Settings:
    return Settings(base_url=base_url, model="test-model", timeout_s=7)


def test_complete_posts_openai_compatible_request_and_normalizes_url() -> None:
    expected: dict[str, Any] = {"choices": []}
    session = FakeSession(FakeResponse(body=expected))

    result = complete(
        _settings(), "test-key", [{"role": "user", "content": "hi"}], ["Front", "Back"], session
    )

    assert result == expected
    call = session.calls[0]
    assert call["url"] == "https://example.test/v1/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer test-key"
    assert call["json"]["model"] == "test-model"
    assert call["json"]["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "anki_card",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["fields"],
                "properties": {
                    "fields": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["Front", "Back"],
                        "properties": {
                            "Front": {"type": "string"},
                            "Back": {"type": "string"},
                        },
                    }
                },
            },
        },
    }
    assert call["timeout"] == 7


@pytest.mark.parametrize(
    ("status", "kind"),
    [(401, "auth"), (403, "auth"), (429, "rate_limit"), (500, "server")],
)
def test_complete_maps_http_errors(status: int, kind: str) -> None:
    session = FakeSession(FakeResponse(status_code=status, text="provider error"))

    with pytest.raises(AiError) as error:
        complete(_settings(), "key", [], [], session)

    assert error.value.kind == kind
    assert len(session.calls) == 1


@pytest.mark.parametrize(
    ("exception", "kind"),
    [
        (requests.Timeout("slow"), "timeout"),
        (requests.ConnectionError("offline"), "network"),
    ],
)
def test_complete_maps_transport_errors(exception: Exception, kind: str) -> None:
    with pytest.raises(AiError) as error:
        complete(_settings(), "key", [], [], FakeSession(exception))

    assert error.value.kind == kind


def test_complete_falls_back_from_schema_to_object_to_no_format() -> None:
    expected: dict[str, Any] = {"choices": []}
    session = FakeSession(
        FakeResponse(status_code=400, text="response_format is unsupported"),
        FakeResponse(status_code=400, text="response_format is unsupported"),
        FakeResponse(body=expected),
    )

    assert complete(_settings(), "key", [], ["Front"], session) == expected
    assert len(session.calls) == 3
    assert session.calls[0]["json"]["response_format"]["type"] == "json_schema"
    assert session.calls[1]["json"]["response_format"] == {"type": "json_object"}
    assert "response_format" not in session.calls[2]["json"]


def test_complete_does_not_retry_other_400() -> None:
    session = FakeSession(FakeResponse(status_code=400, text="bad request"))

    with pytest.raises(AiError) as error:
        complete(_settings(), "key", [], [], session)

    assert error.value.kind == "bad_response"
    assert len(session.calls) == 1


def _response(content: Any, finish_reason: str = "stop") -> dict[str, Any]:
    return {"choices": [{"message": {"content": content}, "finish_reason": finish_reason}]}


@pytest.mark.parametrize(
    "content",
    [
        '{"fields":{"Front":"New"}}',
        '```json\n{"fields":{"Front":"New"}}\n```',
        'Suggested update:\n{"fields":{"Front":"New"}}\nDone.',
    ],
)
def test_parse_proposal_accepts_json_formats(content: str) -> None:
    result = parse_proposal(_response(content), {"Front": "Old"})

    assert result == Proposal(changed={"Front": "New"}, raw=content)


@pytest.mark.parametrize(
    "response",
    [
        {"choices": []},
        _response(None),
        _response('{"fields":{"Front":"New"}}', finish_reason="length"),
        _response("This is not JSON"),
        _response('{"other":{}}'),
        _response('{"fields":[]}'),
        _response('{"fields":{"Front":42}}'),
    ],
)
def test_parse_proposal_rejects_invalid_response_with_raw(response: dict[str, Any]) -> None:
    with pytest.raises(AiError) as error:
        parse_proposal(response, {"Front": "Old"})

    assert error.value.kind == "bad_response"
    assert "Raw response:" in error.value.message


def test_parse_proposal_drops_unknown_missing_and_unchanged_fields() -> None:
    content = '{"fields":{"Front":"Updated","Back":"Same","Unknown":"Ignored"}}'

    result = parse_proposal(_response(content), {"Front": "Old", "Back": "Same", "Extra": "Keep"})

    assert result.changed == {"Front": "Updated"}
    assert result.raw == content


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("first\nsecond", "first<br>second"),
        ("```html\n<p>first\nsecond</p>\n```", "<p>first<br>second</p>"),
        ("first<br>second", "first<br>second"),
        ('<img src="media:card.png">', '<img src="media:card.png">'),
        ("before\n<pre>keep\nthis</pre>\nafter", "before<br><pre>keep\nthis</pre><br>after"),
    ],
)
def test_normalise_field(value: str, expected: str) -> None:
    assert normalise_field(value) == expected


def test_parse_proposal_normalizes_values_and_drops_normalized_unchanged_fields() -> None:
    content = '{"fields":{"Front":"same\\nvalue","Back":"new\\nline"}}'

    result = parse_proposal(_response(content), {"Front": "same<br>value", "Back": "old"})

    assert result.changed == {"Back": "new<br>line"}


def test_parse_proposal_compares_original_with_newlines_and_preserves_pre_content() -> None:
    original = "<p>same\nline</p>\n<pre>keep\nline</pre>"
    content = '{"fields":{"Front":"<p>same\\nline</p>\\n<pre>keep\\nline</pre>"}}'

    result = parse_proposal(_response(content), {"Front": original})

    assert result.changed == {}
    assert original == "<p>same\nline</p>\n<pre>keep\nline</pre>"
