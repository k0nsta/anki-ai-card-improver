# AI Card Improver — Anki desktop add-on

## Overview
- Anki desktop add-on: on any card, ask an AI (user's own API key) to improve the note using a prompt chosen by deck (English deck → English prompt, Portuguese → Portuguese prompt).
- Replaces the manual loop: copy card → paste into external AI chat with a saved prompt → copy result back.
- Integrates through Anki's public add-on hooks; no change to Anki itself. Edited notes sync to mobile as usual.

## Context (from discovery)
- Anki source checkout `~/anki` (upstream `ankitects/anki`) used as API reference and dev runner (`just run`).
- Hooks: `reviewer_will_show_context_menu` (`~/anki/qt/tools/genhooks_gui.py:198`), `editor_did_init_buttons` (`~/anki/qt/tools/genhooks_gui.py:1099`), `Editor.addButton` (`~/anki/qt/aqt/editor.py:169`).
- Background work: `QueryOp(...).with_progress()` (`~/anki/qt/aqt/operations/__init__.py:168`).
- Undoable note write: `update_note(parent=, note=)` (`~/anki/qt/aqt/operations/note.py:25`).
- Editor is the Svelte editor, identified by `nid` (`~/anki/qt/aqt/editor.py:402-447`); `call_after_note_saved` (`:459`) flushes edits; `reload_note()` re-renders from the collection.
- `requests` is an Anki dependency (`~/anki/qt/pyproject.toml:19`); add-on folder has `user_files/` preserved on update (`~/anki/qt/aqt/addons.py:739`).

## Development Approach
- **testing approach**: Regular (code first, then tests in the same task)
- complete each task fully before moving to the next; small focused changes
- every task with pure logic includes pytest tests next to the code (`tests/` mirrors modules only for shared fixtures); Qt glue is covered by the manual smoke test
- all tests must pass before the next task
- update this plan when scope changes

## Testing Strategy
- **unit tests** (pytest, no Anki import): `config.py`, `prompts.py`, `client.py` (HTTP mocked with a fake session object).
- **manual smoke test** in a dev profile: `just run` from `~/anki` with the add-on symlinked into the profile's `addons21/`.
- No e2e harness: Anki's `ts/tests/e2e` targets Anki's own web pages, not add-ons.

## Progress Tracking
- mark completed items `[x]` immediately; ➕ for new tasks; ⚠️ for blockers

## Solution Overview
- Pure core (`config`, `prompts`, `client`) has no `aqt` import → unit-testable with plain pytest.
- Qt layer (`__init__`, `dialog`, `settings`, `actions`) wires hooks, runs the AI call in `QueryOp`, shows a per-field diff, applies accepted fields.
- One shared flow for both triggers; only "apply" differs (reviewer: `update_note` op; editor: write note then `reload_note`).

## Technical Details

Config (`config.json`, via `mw.addonManager.getConfig(__name__)`):
```json
{
  "base_url": "https://openrouter.ai/api/v1",
  "model": "anthropic/claude-sonnet-5-5",
  "timeout_s": 60,
  "shortcut": "Ctrl+Shift+I",
  "default_prompt": "default",
  "prompts": {"default": "Fix errors and make the card clearer.", "english": "...", "portuguese": "..."},
  "decks": {"1690000000001": "english", "1690000000002": "portuguese"}
}
```
Key: env `ANKI_AI_API_KEY` → else `user_files/secret.json` `{"api_key": "..."}` (chmod 600). Never in `config.json`.

Prompt resolution: `did = card.odid or card.did` → look up `decks[did]` → parent deck ids (via deck name `A::B::C` → `A::B` → `A`) → `default_prompt`.

Request (`POST {base_url}/chat/completions`):
- system: `<prompt>\n\nReturn ONLY a JSON object {"fields": {<field name>: <html>}} using exactly the field names given. Keep HTML formatting and media references unchanged unless asked.`
- user: `{"note_type": "Basic", "deck": "Portuguese", "tags": [...], "fields": {"Front": "...", "Back": "..."}}`
- `response_format: {"type": "json_object"}`; on HTTP 400 mentioning response_format, retry once without it.

Response parse: `choices[0].message.content` → JSON (or first ```` ```json ```` fence) → `fields` dict → drop unknown names, keep missing unchanged, drop unchanged values → `Proposal(changed: dict[str, str], raw: str)`.

Errors (typed `AiError(kind, message)`): `no_config`, `auth` (401/403), `rate_limit` (429), `server` (5xx), `timeout`, `network`, `bad_response` (unparseable → raw shown, nothing applied).

Concurrency guard: remember note `mtime` before the call; on accept, re-fetch the note; if deleted or `mtime` changed → refuse with a warning.

## What Goes Where
- Implementation Steps: code + tests in `~/anki-ai-improver`.
- Post-Completion: manual smoke test, optional AnkiWeb publishing.

## Implementation Steps

### Task 1: Repo scaffold and test tooling

**Files:**
- Create: `anki_ai_improver/__init__.py` (empty stub), `anki_ai_improver/config.json`, `anki_ai_improver/manifest.json`
- Create: `pyproject.toml`, `Makefile`, `.gitignore`, `README.md`

- [ ] package dir `anki_ai_improver/` with `manifest.json` (`package`, `name`) and default `config.json` from Technical Details
- [ ] `pyproject.toml` with pytest + ruff + mypy dev deps (uv); `Makefile` targets `test`, `lint`, `link` (symlink package into a given `addons21/`), `package` (zip to `.ankiaddon`)
- [ ] `.gitignore` covers `user_files/`, `*.ankiaddon`, `.venv/`
- [ ] smoke test `tests/test_import.py`: pure modules import without `aqt`
- [ ] `make test lint` passes

### Task 2: Config and secret storage (`config.py`)

**Files:**
- Create: `anki_ai_improver/config.py`, `anki_ai_improver/config_test.py`

- [ ] `Settings` dataclass + `from_dict(dict)` with validation (missing `base_url`/`model` → `no_config`)
- [ ] `load_api_key(user_files: Path, env)`: env first, then `secret.json`; `save_api_key(...)` writes with mode 600
- [ ] tests: defaults, missing fields, env override wins, file round-trip + permissions, absent file → None
- [ ] run tests — must pass before Task 3

### Task 3: Prompt resolution and message build (`prompts.py`)

**Files:**
- Create: `anki_ai_improver/prompts.py`, `anki_ai_improver/prompts_test.py`

- [ ] `resolve_prompt_name(deck_id, deck_names: Callable[[id], name], name_to_id, settings)` with parent walk and default fallback
- [ ] `build_messages(prompt_text, NoteSnapshot)`; `NoteSnapshot` = note_type, deck, tags, ordered fields
- [ ] tests: exact deck, subdeck inherits parent, grandchild, unmapped → default, mapped prompt name missing from `prompts` → default, filtered deck uses home deck (caller passes `odid`)
- [ ] tests: messages contain all field names and the JSON contract
- [ ] run tests — must pass before Task 4

### Task 4: OpenAI-compatible client and response parsing (`client.py`)

**Files:**
- Create: `anki_ai_improver/client.py`, `anki_ai_improver/client_test.py`

- [ ] `complete(settings, api_key, messages, session=requests)` → content string; maps HTTP/timeout/network to `AiError`
- [ ] retry once without `response_format` on a 400 that mentions it
- [ ] `parse_proposal(content, current_fields)` → `Proposal` (unknown dropped, missing kept, unchanged dropped, fenced JSON accepted)
- [ ] tests (fake session): success, 401, 429, 500, timeout, connection error, response_format fallback
- [ ] tests: plain JSON, fenced JSON, prose + JSON, garbage → `bad_response` with raw, unknown/missing fields
- [ ] run tests — must pass before Task 5

### Task 5: Shared improve flow and diff dialog (`actions.py`, `dialog.py`)

**Files:**
- Create: `anki_ai_improver/actions.py`, `anki_ai_improver/dialog.py`

- [ ] `improve(parent, note, card_deck_id, apply: Callable[[dict], None])`: missing key/config → open settings; else `QueryOp` with progress calling prompts + client
- [ ] `DiffDialog`: per changed field old/new side by side (rendered text + HTML toggle), checkbox each (default ticked), prompt dropdown + Retry, raw-response view on `bad_response`
- [ ] errors → `showWarning`/`tooltip` with the `AiError` message; no write on any error
- [ ] concurrency guard: refuse apply if note deleted or `mtime` changed
- [ ] unit-test the pure helper that merges accepted fields into a field dict (`actions_test.py`)
- [ ] run tests — must pass before Task 6

### Task 6: Reviewer trigger

**Files:**
- Modify: `anki_ai_improver/__init__.py`

- [ ] context-menu entry via `gui_hooks.reviewer_will_show_context_menu`
- [ ] shortcut via `gui_hooks.state_shortcuts_will_change` (state `review`), key from config
- [ ] apply = set accepted fields on `card.note()` → `update_note(parent=mw, note=note).run_in_background()` (undo + reviewer redraw)
- [ ] manual check in dev profile: menu, shortcut, accept, Ctrl+Z undoes

### Task 7: Editor trigger

**Files:**
- Modify: `anki_ai_improver/__init__.py`, `anki_ai_improver/actions.py`

- [ ] ⚠️ spike first: confirm how a Python add-on reads/writes the current note in the Svelte editor (`nid`-based; Add window note may not exist in the collection yet). Record the finding here before coding.
- [ ] toolbar button via `gui_hooks.editor_did_init_buttons` + `Editor.addButton`
- [ ] Edit/Browse: `call_after_note_saved` → load note by `nid` → improve → apply = `update_note` then `editor.reload_note()`
- [ ] Add window: use the spike's approach, or disable the button there with a tooltip if no supported path exists
- [ ] manual check in Edit, Browse and Add windows

### Task 8: Settings dialog (`settings.py`)

**Files:**
- Create: `anki_ai_improver/settings.py`
- Modify: `anki_ai_improver/__init__.py`

- [ ] dialog: base URL, model, masked API key (writes `secret.json`; shows "set via env" when env var present), timeout
- [ ] prompt list editor (add/rename/delete, multiline text) and deck → prompt table using a deck picker (stores deck ids)
- [ ] register as add-on config action (`mw.addonManager.setConfigAction`) + Tools menu entry
- [ ] "Test connection" button: one tiny request, shows success or the `AiError`
- [ ] manual check: save, reopen, key never appears in `config.json`

### Task 9: Verify acceptance criteria
- [ ] English deck card → English prompt; Portuguese subdeck card → Portuguese prompt; unmapped deck → default
- [ ] filtered deck card uses home deck prompt
- [ ] partial accept writes only ticked fields; Ctrl+Z restores
- [ ] 401 / timeout / garbage response → warning, no write
- [ ] `make test lint` green

### Task 10: [Final] Update documentation
- [ ] README: install (symlink/`.ankiaddon`), configuration, example prompts, privacy note (card content is sent to the configured provider)
- [ ] add CLAUDE.md for the repo (layout, `make` targets, pure-core rule)
- [ ] move this plan to `docs/plans/completed/`

## Post-Completion
*Informational only*

**Manual verification:**
- daily use on real English/Portuguese decks for a week; tune default system contract
- check edited notes sync to AnkiMobile/AnkiDroid unchanged

**External:**
- optional: publish on AnkiWeb add-ons (needs repo made public → strip personal data first)
