"""OpenAI-compatible chat completion client and response parsing."""

import json
from dataclasses import dataclass
from typing import Any

import requests

from .config import Settings
from .errors import AiError


@dataclass
class Proposal:
    """Suggested field updates and the model's original response text."""

    changed: dict[str, str]
    raw: str


def complete(
    settings: Settings,
    api_key: str,
    messages: list[dict[str, str]],
    session: Any = requests,
) -> dict[str, Any]:
    """Send one chat completion request, retrying without JSON mode if unsupported."""
    url = f"{settings.base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    payload: dict[str, Any] = {
        "model": settings.model,
        "messages": messages,
        "response_format": {"type": "json_object"},
    }

    for attempt in range(2):
        try:
            response = session.post(
                url,
                headers=headers,
                json=payload,
                timeout=settings.timeout_s,
            )
        except requests.Timeout as error:
            raise AiError("timeout", "The AI request timed out") from error
        except requests.ConnectionError as error:
            raise AiError("network", "Could not connect to the AI service") from error
        except requests.RequestException as error:
            raise AiError("network", "The AI request failed") from error

        status = response.status_code
        body = response.text
        if status == 400 and "response_format" in body.lower() and attempt == 0:
            payload = {key: value for key, value in payload.items() if key != "response_format"}
            continue
        if status in (401, 403):
            raise AiError("auth", "The AI service rejected the API key")
        if status == 429:
            raise AiError("rate_limit", "The AI service rate limit was reached")
        if 500 <= status <= 599:
            raise AiError("server", f"The AI service returned HTTP {status}")
        if status >= 400:
            raise AiError("bad_response", f"The AI service returned HTTP {status}: {body}")

        try:
            result = response.json()
        except (ValueError, json.JSONDecodeError) as error:
            raise AiError("bad_response", f"Invalid JSON response: {body}") from error
        if not isinstance(result, dict):
            raise AiError("bad_response", f"Expected a JSON object response: {body}")
        return result

    raise AiError("bad_response", "The AI service rejected response_format")


def parse_proposal(response: dict[str, Any], current_fields: dict[str, str]) -> Proposal:
    """Parse model output and retain only changed values for known fields."""
    raw = _response_content(response)
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise _bad_response(raw, "The response contained no choices")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise _bad_response(raw, "The response choice was invalid")
    if choice.get("finish_reason") == "length":
        raise _bad_response(raw, "The response was truncated")
    message = choice.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if content is None:
        raise _bad_response(raw, "The response content was empty")
    if not isinstance(content, str):
        raise _bad_response(raw, "The response content was not text")
    raw = content

    parsed = _extract_json(content)
    if not isinstance(parsed, dict):
        raise _bad_response(raw, "No JSON object was found")
    fields = parsed.get("fields")
    if not isinstance(fields, dict):
        raise _bad_response(raw, "The JSON response had no fields object")
    for name, value in fields.items():
        if not isinstance(value, str):
            raise _bad_response(raw, f"Field {name!r} was not text")

    changed = {
        name: value
        for name, value in fields.items()
        if name in current_fields and value != current_fields[name]
    }
    return Proposal(changed=changed, raw=raw)


def _response_content(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if isinstance(choices, list) and choices:
        choice = choices[0]
        if isinstance(choice, dict):
            message = choice.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content
                if content is not None:
                    return str(content)
    return json.dumps(response, ensure_ascii=False, default=str)


def _extract_json(content: str) -> Any:
    """Accept a JSON document, a fenced document, or JSON embedded in prose."""
    stripped = content.strip()
    if stripped.startswith("```"):
        first_newline = stripped.find("\n")
        if first_newline >= 0:
            end_fence = stripped.find("```", first_newline + 1)
            if end_fence >= 0:
                fenced = stripped[first_newline + 1 : end_fence].strip()
                try:
                    return json.loads(fenced)
                except json.JSONDecodeError:
                    pass
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for index, char in enumerate(content):
        if char == "{":
            try:
                value, _ = decoder.raw_decode(content[index:])
                if isinstance(value, dict):
                    return value
            except json.JSONDecodeError:
                continue
    return None


def _bad_response(raw: str, reason: str) -> AiError:
    return AiError("bad_response", f"{reason}. Raw response: {raw}")
