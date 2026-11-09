# Structured output, deck-agnostic defaults and optional quality gate

## Overview
- Make every "Improve" robust and deck-agnostic: the add-on owns the output format (strict JSON schema, Anki `<br>` HTML), the user's per-deck prompt owns only content.
- Ship a generic default prompt that works for any deck (languages, history, programming, medicine) and example prompts for English and European Portuguese decks.
- Add an optional quality gate: a cheap OpenRouter decisions model (`typesafe/jev-1.14`, ~$0.00002 and ~0.3 s per call) scores correctness; a low score triggers one automatic fix call. Off by default.
- Make `openai/gpt-6-luna` the default model (~$0.0005/card, ~8 s).

## Context (from discovery)
- Evidence (prompt experiments, 2026-11-09, OpenRouter): gpt-6-luna matched expensive models; JSON-mode-only output produced invalid JSON (unescaped quotes, DeepSeek) and literal newlines (Gemini); a second full self-review call tripled latency without measurable gain; a correctness-only gate is the useful part (readability/recall judges penalise the user's own preferred cards; Jev's front-leak flag has false positives on short definitional cards).
- `anki_ai_improver/client.py:21` `complete()` sends `response_format: json_object`, retries without it on HTTP 400.
- `anki_ai_improver/client.py:76` `parse_proposal()` / `:128` `_extract_json()`.
- `anki_ai_improver/prompts.py:40` `build_messages()` appends a one-line JSON contract to the user's prompt.
- `anki_ai_improver/addon.py:63` `improve()`, `:124` `_run_request()` (QueryOp), `anki_ai_improver/dialog.py:24` `DiffDialog`, `anki_ai_improver/settings.py:45` `SettingsDialog`.
- `anki_ai_improver/config.json`: default `model` `anthropic/claude-sonnet-5-5`, default prompt one sentence.
- Decisions API: `POST https://openrouter.ai/api/alpha/decisions` body `{"model", "state": <JSON>, "questions": {id: {"type": "score", "instructions", "criteria": [levels low→high]}}}` → `answers[id].score` (0..len-1, probability-weighted), `confidence`; `usage.cost`. Same request shape as https://developers.cloudflare.com/workers-ai/models/clef/ . Not available on `/chat/completions`.

## Development Approach
- **testing approach**: Regular (code first, then tests in the same task)
- pure logic stays free of `aqt` imports and is unit-tested next to the code (`*_test.py`); Qt glue is thin
- complete each task fully before the next; all tests must pass
- update this plan when scope changes

## Testing Strategy
- unit tests (pytest, fake HTTP session) for request building, schema fallback, normalisation, gate request/response parsing and the gate decision.
- no live network in tests.

## Progress Tracking
- mark completed items `[x]` immediately; ➕ for new tasks; ⚠️ for blockers

## Solution Overview
```
click → snapshot + deck prompt
  → call 1: chat/completions, system = <deck prompt> + ADD-ON OUTPUT RULES, strict json_schema {fields: {<note field names>}}
       (400 on json_schema → retry once with json_object)
  → normalise: literal newlines → <br>, strip ``` fences
  → [gate on] decisions(jev-1.14, state = note type + deck + fields as text, question: correctness 0-4)
       score < gate_min_correctness → call 2: fix call (same model) told "an automatic check rated correctness low", same schema → normalise
       gate error → keep the draft, status "unchecked"
  → DiffDialog with a status line: "" | "✓ checked" | "✓ fixed after check" | "⚠ unchecked: <reason>"
```

## Technical Details
- Output rules appended by the add-on (generic, never deck-specific):
  - Return `{"fields": {...}}` with exactly the note's field names; each value is that field's full new content.
  - Field content is Anki HTML: `<br>` for line breaks, `<br><br>` between blocks; no Markdown, no code fences, no literal newlines.
  - Keep media references (`[sound:...]`, `<img ...>`) unchanged.
  - The note's current content is the topic; improve it according to the instructions above.
- JSON schema: `{"type":"json_schema","json_schema":{"name":"anki_card","strict":true,"schema":{"type":"object","additionalProperties":false,"required":["fields"],"properties":{"fields":{"type":"object","additionalProperties":false,"required":[<names>],"properties":{<name>:{"type":"string"}}}}}}}`.
- Fallback chain on HTTP 400 mentioning `response_format`: json_schema → json_object → none (each at most once).
- Decisions URL derived from `base_url`: `https://openrouter.ai/api/v1` → `https://openrouter.ai/api/alpha/decisions` (replace a trailing `/v1`). The gate is available only when `base_url` is on `openrouter.ai`; otherwise the setting is disabled with a hint.
- Gate question (deck-agnostic):
  - id `correctness`, type `score`, instructions "How correct is this flashcard: facts, language, translations, code and formulas, with no self-contradictions?", criteria `["several clear errors", "one or two clear errors", "minor issues", "essentially correct, small awkwardness", "fully correct and natural"]`.
- Gate input: the merged full card (original fields with the proposal applied), HTML stripped (`<br>` → newline, other tags removed), plus note type and deck. The fix call gets the merged full fields as HTML.
- Gate status strings: off → `""`; on but `base_url` not OpenRouter → `"⚠ unchecked: quality gate needs OpenRouter"`; passed → `"✓ checked"`; fixed → `"✓ fixed after check"`; gate or fix call failed → `"⚠ unchecked: <reason>"` with the draft kept.
- `Proposal` gains `status: str = ""`; the op, Retry and `DiffDialog.receive` carry it unchanged.
- `gate_min_correctness` not a number or outside 0–4 → falls back to 2.5 (no error).
- Migration of saved configs (only untouched values): `prompts.default` equal to the old one-liner `Fix factual and spelling errors, make the card clearer and more concise. Keep the language of each field.` → the generic prompt; `model` equal to `anthropic/claude-sonnet-5-5` → `openai/gpt-6-luna`; anything else stays. Applied when settings load, written back with `mw.addonManager.writeConfig`.
- New config keys (defaults): `"gate_enabled": false`, `"gate_model": "typesafe/jev-1.14"`, `"gate_min_correctness": 2.5`.
- Fix-call system message: deck prompt + "An automatic quality check rated this card's correctness {score:.1f}/4. Find and fix factual, language and translation errors; keep everything that is correct." + output rules; user message: `{"original_note": …, "draft": …}`.

## What Goes Where
- Implementation Steps: code, tests, config defaults and docs in this repo.
- Post-Completion: manual check in Anki on the Mac.

## Implementation Steps

### Task 1: Strict JSON schema request with fallback chain

**Files:**
- Modify: `anki_ai_improver/client.py`
- Modify: `anki_ai_improver/client_test.py`
- Modify: `anki_ai_improver/addon.py`

- [x] `complete(settings, api_key, messages, field_names, session=requests)`: send the json_schema from Technical Details built from `field_names`
- [x] on HTTP 400 mentioning `response_format`: retry with `json_object`, then without `response_format`; each step once
- [x] update the caller `addon.py` (`_run_request`) to pass `list(snapshot.fields)`
- [x] tests: schema payload shape and field names, 400 → json_object → none chain, non-response_format 400 does not retry, existing error mapping unchanged
- [x] run tests — must pass before Task 2

### Task 2: Normalise model output

**Files:**
- Modify: `anki_ai_improver/client.py`
- Modify: `anki_ai_improver/client_test.py`

- [x] `normalise_field(value)`: strip a wrapping ``` fence, `\r\n`/`\n` → `<br>` except inside `<pre>…</pre>`, trim; applied in `parse_proposal` to the proposal, and to both sides of the unchanged-field comparison (the original field itself is never rewritten)
- [x] tests: literal newlines, fenced value, already-`<br>` value unchanged, media references untouched, unchanged-after-normalise field dropped, original value containing `\n` (and a `<pre>` block) not reported as changed

### Task 3: Add-on output rules in the prompt

**Files:**
- Modify: `anki_ai_improver/prompts.py`
- Modify: `anki_ai_improver/prompts_test.py`

- [ ] `build_messages` appends the output rules from Technical Details (field names listed) instead of the one-line contract
- [ ] `build_fix_messages(prompt_text, snapshot, draft_fields, score)` for the gate's fix call
- [ ] tests: rules list the exact field names, no deck- or language-specific text in the rules, fix message contains the score, the draft and the original note

### Task 4: Quality gate client (pure)

**Files:**
- Create: `anki_ai_improver/gate.py`
- Create: `anki_ai_improver/gate_test.py`
- Modify: `anki_ai_improver/config.py`
- Modify: `anki_ai_improver/config_test.py`
- Modify: `anki_ai_improver/import_test.py`

- [ ] `decisions_url(base_url) -> str | None` (None when not openrouter.ai)
- [ ] `score_correctness(settings, api_key, snapshot_fields_text, note_type, deck, session=requests) -> float` posting the question from Technical Details; maps HTTP/timeout/network/bad JSON to `AiError`
- [ ] `needs_fix(score, minimum) -> bool`
- [ ] `Settings`: `gate_enabled`, `gate_model`, `gate_min_correctness` with defaults; a non-number or out-of-range minimum falls back to 2.5
- [ ] `card_text(fields) -> dict[str, str]`: strip HTML for the gate input (`<br>` → newline)
- [ ] tests: URL derivation (openrouter, trailing slash, other host → None), request body shape, score parsing, error mapping, `needs_fix` boundaries, `card_text`, settings defaults and the 2.5 fallback (string, -1, 5)
- [ ] run tests — must pass before Task 5

### Task 5: Wire the gate into the improve flow and dialog

**Files:**
- Modify: `anki_ai_improver/addon.py`
- Modify: `anki_ai_improver/dialog.py`
- Modify: `anki_ai_improver/logic.py`
- Modify: `anki_ai_improver/logic_test.py`
- Modify: `anki_ai_improver/client.py`
- Modify: `anki_ai_improver/client_test.py`

- [ ] `Proposal` (`client.py`) gains `status: str = ""`
- [ ] in the background op: draft → if gate enabled and available: score the merged card text → fix call when `needs_fix` → return the proposal with its status
- [ ] pure `gate_status(enabled, available, score, fixed, error) -> str` producing the dialog status line from Solution Overview
- [ ] gate or fix-call errors never fail the request: draft kept, status "⚠ unchecked: <reason>"; gate enabled with a non-OpenRouter `base_url` → "⚠ unchecked: quality gate needs OpenRouter"
- [ ] `DiffDialog` shows the status line; Retry re-runs the whole flow
- [ ] pure `run_gate(draft: Proposal, merged_text, score_fn, fix_fn, enabled, available, minimum) -> Proposal` in `logic.py` with injected callables; `addon.py` only calls it inside the QueryOp
- [ ] tests for `gate_status` (off, needs OpenRouter, passed, fixed, gate error, fix-call error)
- [ ] tests for `run_gate`: off → draft unchanged and score_fn not called; unavailable; pass; low score → fix_fn result with "✓ fixed after check"; score_fn raises → draft + "⚠ unchecked"; fix_fn raises → draft + "⚠ unchecked"
- [ ] test in `client_test.py` that `Proposal.status` defaults to `""`
- [ ] run tests — must pass before Task 6

### Task 6: Settings: gate controls

**Files:**
- Modify: `anki_ai_improver/settings.py`
- Modify: `anki_ai_improver/config.json`

- [ ] General tab: checkbox "Quality gate (checks correctness, ~0.3 s, OpenRouter only)", min-correctness spin box (0–4, step 0.1), disabled with a hint when `base_url` is not OpenRouter
- [ ] `config.json` gains the three gate keys with defaults

### Task 7: Deck-agnostic defaults and example prompts

**Files:**
- Modify: `anki_ai_improver/config.json`
- Modify: `anki_ai_improver/config.py`
- Modify: `anki_ai_improver/config_test.py`
- Modify: `anki_ai_improver/addon.py`
- Modify: `anki_ai_improver/settings.py`
- Create: `docs/prompts/generic.md`, `docs/prompts/english.md`, `docs/prompts/portuguese.md`
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] `config.json`: `"model": "openai/gpt-6-luna"`; `prompts.default` = the generic prompt below (verbatim)
- [ ] `config.py` `_DEFAULT_PROMPTS['default']` = the same generic prompt; test that it equals `config.json`'s `prompts.default`
- [ ] pure `migrate_config(values) -> (values, changed)` per Technical Details; `addon.py` (when loading settings) and `settings.py` (when the dialog opens) apply it and write the config back only when `changed`
- [ ] tests for `migrate_config`: old prompt replaced, edited prompt kept, old model replaced, other model kept, already-migrated config unchanged
- [ ] create the three prompt files with the verbatim texts below (file content = the text only, no fences)
- [ ] README: "Prompts" section — the default works for any deck; per-deck prompts own content only; links to the three examples; how to map them in the Decks tab
- [ ] README: "Quality gate" section — what it checks, cost/latency, OpenRouter only, off by default; model cost table (gpt-6-luna ~$0.0005/card ~8 s, claude-haiku-5.5 ~$0.001/card)
- [ ] CLAUDE.md: output rules live in `prompts.py` and stay deck-agnostic; gate lives in `gate.py`

Generic prompt (`docs/prompts/generic.md` and `prompts.default`):
~~~text
You improve one Anki flashcard for spaced repetition. The deck can be about anything (a language, history, medicine, programming...): infer the subject and the card's direction from its current content.

- Keep the card's purpose, direction, language(s) and field roles. Do not turn it into a different card.
- Never drop content in another language or notation (translations, transcriptions/IPA, formulas, code); fix it instead.
- Keep the spelling variety already used (British/American, European/Brazilian Portuguese...).
- Front: one clear cue that makes the learner recall a single answer; it must not contain that answer.
- Back: the answer first, short and precise; then only the detail needed to remember and understand it.
- Extra fields (examples, notes, sources): keep their role; fix, tighten, and add one concrete example or mnemonic only if it really helps recall.
- Fix factual, spelling and grammar errors. Never invent facts; if unsure, keep the original wording.
- Concise and readable on a phone: short lines, no filler, no repetition between fields.
- If the card tries to teach several things, keep the core one and end the last field with `MORE CARDS: <topic>, <topic>`.
~~~

English prompt (`docs/prompts/english.md`):
~~~text
# Anki English Card — vocabulary & grammar (lean)

You are my English tutor and Anki card writer. I am an intermediate-to-advanced learner (native Russian) and a software engineer.

The note's current content is the topic (a bare word, a draft or an old card). Rebuild it into a card I can review in under a minute. Keep what is already good; fix what is wrong.

## Principles

- One card = one item to recall. Prefer fewer, sharper lines over completeness.
- Max 4 senses (most common first); drop rare or specialised ones.
- Never reveal the target word/expression (or its parts) on the Front.
- Natural, common English and natural Russian; never invent phrases to show a pattern; do not mark a usage as wrong if natives commonly say it.
- Varied contexts (everyday life, friends, travel, work, emotions); at most one tech example.
- British English spelling.

## Style

- Labels and block titles in ENGLISH CAPS (`FORMS:`, `1. RECONNECT`), never Russian or transliteration.
- `→` for examples, `✗` / `✓` for mistakes.
- Short lines for a phone; each Russian translation on its own line under the English.

## Front — one cue, max 4 lines

Vocabulary:
- Russian meanings only, ` / ` between senses, one line per sense group (short glosses, no explanations, no English hints).

Grammar:
- Topic name + ONE concrete question about its core use (not "what, when, how, exceptions" at once).

## Back — the answer, max ~400 characters

Vocabulary:
1. Target + part of speech, British IPA on the next line.
2. Numbered senses: Russian gloss + one short `→` example (≤ 8 words).
3. `FORMS:` one line (e.g. `catch – caught – caught · catching`), only for verbs or irregular forms.

Grammar:
- Formula; one positive / negative / question line each; the core use in one line.

## Example — max ~1,200 characters

1. Per sense: CAPS title + 1–2 examples with Russian translation.
2. `PATTERNS:` max 4 lines, structure → short example; include every common preposition variant and the use with no object.
3. `X vs Y:` the one contrast learners mix up most, 2 lines.
4. `MISTAKES:` 2 pairs `✗` / `✓`, real Russian-speaker errors, never contradicting the card.
5. `REMEMBER:` 1–2 lines.

If the topic is too big for one card (e.g. a whole tense, a verb with 6+ senses), cover the core only and end Example with one line `MORE CARDS: <topic>, <topic>` naming what deserves its own card.
~~~

Portuguese prompt (`docs/prompts/portuguese.md`):
~~~text
# Anki Portuguese Card (European Portuguese → English / Russian)

You are my European Portuguese tutor (Portugal, not Brazil) and Anki card writer. I am a native Russian speaker with advanced English.

The note's current content is the topic (a bare word, a draft or an old card). Rebuild it into a card I can review in under a minute. Keep what is already good; fix what is wrong.

## Front
- The Portuguese word or expression with its grammar tag: `n.m.`, `n.f.`, `v.`, `adj.`, `adv.`, `expr.`; plural or irregular forms only if unusual.

## Back
- English meaning(s), English IPA only if useful, then ` / ` and the Russian meaning, on one line.
- Max 3 senses, most common first.

## Example
- 2–3 natural European Portuguese sentences (one per sense), each followed by `→` and its English translation on the next line.
- `Common expressions:` 2–4 `*` lines, `expression → English`.
- Portugal usage and spelling (e.g. `facto`, `autocarro`, `stock`); mark Brazilian variants as `(BR)` only when they differ.

## Rules
- Natural sentences a Portuguese speaker would say; never invent collocations.
- Translations must match the sentence's actual meaning.
- Plain text; short lines for a phone.
~~~

## Acceptance Criteria
- Run: `uv run python -c "import json; c=json.load(open('anki_ai_improver/config.json')); assert c['model']=='openai/gpt-6-luna' and c['gate_enabled'] is False and c['gate_model']=='typesafe/jev-1.14' and c['gate_min_correctness']==2.5 and 'any' in c['prompts']['default']"`
- Run: `test -s docs/prompts/generic.md && test -s docs/prompts/english.md && test -s docs/prompts/portuguese.md`
- Run: `uv run python -c "import json, pathlib; c=json.load(open('anki_ai_improver/config.json')); assert pathlib.Path('docs/prompts/generic.md').read_text().strip() == c['prompts']['default'].strip()"`
- Run: `grep -q 'json_schema' anki_ai_improver/client.py && grep -q 'alpha/decisions' anki_ai_improver/gate.py`
- Run: `! grep -niE 'english|russian|portug' anki_ai_improver/prompts.py anki_ai_improver/gate.py`
- Run: `uv run python -c "import sys, anki_ai_improver.gate; assert 'aqt' not in sys.modules"`
- `client_test.py` covers the json_schema → json_object → none fallback chain and newline/fence normalisation
- `gate_test.py` covers URL derivation, request shape, score parsing, error mapping and `needs_fix` boundaries
- `logic_test.py` covers every `gate_status` outcome; a gate or fix-call error never blocks the proposal
- `config_test.py` covers `migrate_config` (untouched values migrated, edited values kept) and the 2.5 fallback

## Post-Completion
*Informational only*

**Manual verification** (Mac, Anki 26.09+):
- English deck with `docs/prompts/english.md`: "come by" → card with Russian-only front, ~1,000 chars
- a non-language deck (e.g. history) with the default prompt: fixes errors, keeps structure
- gate on: dialog shows "✓ checked" or "✓ fixed after check"; gate on with a non-OpenRouter base URL: setting disabled
- wrong gate model id → "⚠ unchecked", draft still applies

**Housekeeping:**
- move this plan to `docs/plans/completed/`
