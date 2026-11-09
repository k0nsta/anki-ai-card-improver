# AI Card Improver — Anki desktop add-on

## Overview
- Anki desktop add-on: on any card, ask an AI (user's own API key) to improve the note using a prompt chosen by deck (English deck → English prompt, Portuguese → Portuguese prompt).
- Replaces the manual loop: copy card → paste into external AI chat with a saved prompt → copy result back.
- Integrates through Anki's public add-on hooks; no change to Anki itself. Edited notes sync to mobile as usual.

## Context (from discovery)
- Anki source checkout `~/anki` (upstream `ankitects/anki`) used as API reference and dev runner (`just run`).
- Reviewer: `reviewer_will_show_context_menu` (`~/anki/qt/tools/genhooks_gui.py:198`, fired `reviewer.py:1063`); shortcuts via `state_shortcuts_will_change` (`genhooks_gui.py:645`, fired `main.py:1229`).
- Two editors: default legacy `Editor` (`~/anki/qt/aqt/editor_legacy.py:148`, has `.note`, `loadNote()`) and experimental Svelte `NewEditor` (`~/anki/qt/aqt/editor.py:56`, `nid`-based, `reload_note()`), switched by `ExperimentFlag.SVELTE_EDITOR` (`main.py:1316`). `editor_did_init_buttons` (`genhooks_gui.py:1099`) passes either; `addButton` already wraps callbacks in `call_after_note_saved` (`editor.py:186`, `editor_legacy.py:283`).
- Background work: `QueryOp(...).without_collection().failure(...).with_progress()` (`~/anki/qt/aqt/operations/__init__.py:168`).
- Undoable note write: `update_note(parent=, note=)` (`~/anki/qt/aqt/operations/note.py:25`); reviewer redraws itself after it (`reviewer.py:225`), legacy browser/edit-current reload themselves (`browser.py:188`, `editcurrent_legacy.py:49`).
- Deck helpers: `card.current_deck_id()` (`~/anki/pylib/anki/cards.py:194`), `col.decks.parents(did)` (`~/anki/pylib/anki/decks.py:485`).
- `requests` is an Anki dependency (`~/anki/qt/pyproject.toml:19`); `user_files/` survives add-on updates (`~/anki/qt/aqt/addons.py:743`); user config is written to `meta.json` (`addons.py:733`).
- Shortcut `Ctrl+Shift+I` is taken (Import, Browser Info); `Ctrl+Alt+J` is unused in `qt/aqt` and `ts/`.

## Development Approach
- **testing approach**: Regular (code first, then tests in the same task)
- complete each task fully before moving to the next; small focused changes
- pure logic lives in modules without `aqt` imports and is unit-tested (`*_test.py` next to the code); Qt glue is thin, its decisions extracted into pure helpers with tests; the rest is covered by the manual smoke test
- all tests must pass before the next task
- update this plan when scope changes

## Testing Strategy
- **unit tests** (pytest, no Anki import): `config.py`, `prompts.py`, `client.py`, `logic.py`.
- `__init__.py` imports the Qt wiring only when `aqt.mw` is present, so pytest can import the package.
- mypy runs on pure modules only; Qt modules (`addon.py`, `dialog.py`, `settings.py`) are excluded in `pyproject.toml` (no `aqt` wheel as dev dep).
- **manual smoke test** in a dev profile: `just run` from `~/anki` with the add-on symlinked into the profile's `addons21/`, once with the legacy editor and once with the Svelte editor experiment on.

## Progress Tracking
- mark completed items `[x]` immediately; ➕ for new tasks; ⚠️ for blockers

## Solution Overview
- Pure core (`config`, `prompts`, `client`, `logic`) has no `aqt` import.
- Qt layer (`addon.py` hook wiring, `dialog.py` diff, `settings.py`) captures a note snapshot on the main thread, runs the AI call in a `QueryOp` without the collection, shows a per-field diff, applies accepted fields to the **captured** note.
- One shared flow for all triggers; only "apply" differs per context (reviewer, legacy editor Edit/Browse/Add, Svelte editor Edit).

## Technical Details

Default `config.json` (user edits land in `meta.json`):
```json
{
  "base_url": "https://openrouter.ai/api/v1",
  "model": "anthropic/claude-sonnet-5-5",
  "timeout_s": 60,
  "shortcut": "Ctrl+Alt+J",
  "default_prompt": "default",
  "prompts": {"default": "Fix factual and spelling errors, make the card clearer and more concise. Keep the language of each field."},
  "decks": {}
}
```
`decks` maps deck id (string) → prompt name. Example English/Portuguese prompts go in the README.

Key: env `ANKI_AI_API_KEY` → else `user_files/secret.json` `{"api_key": "..."}` (chmod 600). Never in `config.json` or `meta.json`.

Prompt resolution: candidates = `[card.current_deck_id()] + [d["id"] for d in reversed(col.decks.parents(did))]` (nearest parent first) → first id present in `decks` whose prompt exists → else `default_prompt`. Pure function takes the ordered id list.

Request (`POST {base_url}/chat/completions`, `response_format: {"type": "json_object"}`):
- system: `<prompt>\n\nReturn ONLY a JSON object {"fields": {<field name>: <html>}} using exactly the field names given. Keep HTML formatting and media references unchanged unless asked.`
- user: `{"note_type": "Basic", "deck": "Portuguese", "tags": [...], "fields": {"Front": "...", "Back": "..."}}`

Response parse → `Proposal(changed: dict[str, str], raw: str)`:
- `bad_response` (raw kept, nothing applied) when: empty `choices`, `content` null, `finish_reason == "length"`, no JSON object (plain or first ```` ```json ```` fence), `fields` missing/not a dict, a value not a string.
- otherwise: drop unknown field names, keep missing fields unchanged, drop values equal to current.

Errors (`AiError(kind, message)`): `no_config`, `auth` (401/403), `rate_limit` (429), `server` (5xx), `timeout`, `network`, `bad_response`.

Staleness guard (pure `is_stale(snapshot, current)`): on accept, refuse when the note is deleted, its `mtime` changed, or the reviewer card / editor note is no longer the one sent.

## What Goes Where
- Implementation Steps: code + tests in `~/anki-ai-improver`.
- Post-Completion: manual daily use, optional AnkiWeb publishing.

## Implementation Steps

### Task 1: Repo scaffold and test tooling

**Files:**
- Create: `anki_ai_improver/__init__.py`, `anki_ai_improver/config.json`, `anki_ai_improver/manifest.json`, `anki_ai_improver/import_test.py`
- Create: `pyproject.toml`, `Makefile`, `.gitignore`, `README.md`

- [ ] `__init__.py`: `try: from aqt import mw` / `except ImportError: mw = None`; `if mw: from . import addon` (addon.py added in Task 5)
- [ ] `manifest.json` (`package`, `name`) and default `config.json` from Technical Details
- [ ] `pyproject.toml`: pytest, ruff, mypy (uv dev deps); mypy excludes Qt modules
- [ ] `Makefile`: `test`, `lint`, `link ADDONS=<addons21 dir>` (symlink), `package` (zip to `.ankiaddon`, excluding `*_test.py`, `__pycache__`, `user_files/`)
- [ ] `.gitignore`: `user_files/`, `*.ankiaddon`, `.venv/`
- [ ] `import_test.py`: package and pure modules import without `aqt`
- [ ] `make test lint` passes

### Task 2: Config and secret storage (`config.py`)

**Files:**
- Create: `anki_ai_improver/config.py`, `anki_ai_improver/config_test.py`

- [ ] `Settings` dataclass + `from_dict(dict)`; missing `base_url`/`model` → `AiError("no_config")`
- [ ] `load_api_key(user_files: Path, env: Mapping)`: env first, then `secret.json`; `save_api_key(...)` writes with mode 600
- [ ] tests: defaults, missing fields, env override wins, file round-trip + mode 600, absent file → None
- [ ] run tests — must pass before Task 3

### Task 3: Prompt resolution and message build (`prompts.py`)

**Files:**
- Create: `anki_ai_improver/prompts.py`, `anki_ai_improver/prompts_test.py`

- [ ] `resolve_prompt(candidate_deck_ids: list[int], settings) -> (name, text)`
- [ ] `NoteSnapshot` (note id, mtime, card id, note type, deck name, tags, ordered fields) + `build_messages(prompt_text, snapshot)`
- [ ] tests: exact deck, subdeck inherits parent, grandchild picks nearest mapped parent, unmapped → default, mapped prompt name missing from `prompts` → default
- [ ] tests: messages contain all field names and the JSON contract
- [ ] run tests — must pass before Task 4

### Task 4: OpenAI-compatible client and response parsing (`client.py`)

**Files:**
- Create: `anki_ai_improver/client.py`, `anki_ai_improver/client_test.py`

- [ ] `complete(settings, api_key, messages, session=requests) -> dict` (response JSON); maps HTTP/timeout/network to `AiError`
- [ ] `parse_proposal(response, current_fields) -> Proposal` per Technical Details
- [ ] tests (fake session): success, 401, 429, 500, timeout, connection error
- [ ] tests: plain JSON, fenced JSON, prose + JSON, garbage, empty choices, null content, `finish_reason=length`, non-string value → `bad_response` with raw; unknown/missing/unchanged fields
- [ ] run tests — must pass before Task 5

### Task 5: Shared flow, minimal key dialog and diff dialog

**Files:**
- Create: `anki_ai_improver/logic.py`, `anki_ai_improver/logic_test.py`
- Create: `anki_ai_improver/addon.py`, `anki_ai_improver/dialog.py`, `anki_ai_improver/settings.py`

- [ ] `logic.py` (pure): `merge_accepted(fields, proposal, accepted_names)`, `is_stale(snapshot, current_note_id, current_mtime, current_target_id)`
- [ ] `settings.py`: minimal dialog with masked API key (writes `secret.json`; shows "set via ANKI_AI_API_KEY" when env present), base URL, model; registered via `mw.addonManager.setConfigAction` + Tools menu
- [ ] `addon.py` `improve(parent, snapshot, candidate_deck_ids, apply)`: no key/config → open the key dialog; else `QueryOp(op=network call).without_collection().failure(show AiError).with_progress().run_in_background()`; snapshot built on main thread before the op
- [ ] `dialog.py` `DiffDialog`: per changed field old/new as plain text in `QTextBrowser` (never `AnkiWebView`), checkbox each (default ticked), prompt dropdown + Retry, raw response view on `bad_response`
- [ ] on accept: `is_stale` → warn and stop; else `apply(merge_accepted(...))`
- [ ] tests for `merge_accepted` and `is_stale` (note deleted, mtime changed, target switched, fresh)
- [ ] run tests — must pass before Task 6

### Task 6: Reviewer trigger

**Files:**
- Modify: `anki_ai_improver/addon.py`, `anki_ai_improver/logic.py`, `anki_ai_improver/logic_test.py`

- [ ] context-menu entry via `gui_hooks.reviewer_will_show_context_menu`
- [ ] shortcut via `gui_hooks.state_shortcuts_will_change`, only when `state == "review"`; key from config via pure `review_shortcut(config) -> (key, name)`
- [ ] apply = fields onto the captured note → `update_note(parent=mw, note=note).run_in_background()` (undo + reviewer redraw)
- [ ] tests for `review_shortcut` (default, custom, empty → disabled)
- [ ] run tests — must pass before Task 7
- [ ] manual check in dev profile: menu, shortcut, accept, Ctrl+Z undoes

### Task 7: Editor trigger (both editors)

**Files:**
- Modify: `anki_ai_improver/addon.py`, `anki_ai_improver/logic.py`, `anki_ai_improver/logic_test.py`

- [ ] `buttons.append(editor.addButton(...))` in `gui_hooks.editor_did_init_buttons` (callback already runs after save)
- [ ] pure `editor_mode(is_new_editor, has_note_in_col, is_add_window) -> "update" | "fill_in_place" | "disabled"` + tests for every combination
- [ ] legacy `Editor` Edit/Browse: `update_note(parent=editor.parentWindow, note=captured)`; windows reload themselves
- [ ] legacy `Editor` Add: write fields onto `editor.note`, `editor.loadNote()`; no collection write
- [ ] `NewEditor` Edit: `update_note` then `editor.reload_note()`; `NewEditor` Add (`nid` None): button disabled with tooltip
- [ ] run tests — must pass before Task 8
- [ ] manual check: Edit, Browse, Add in legacy editor; Edit + Add in Svelte editor experiment

### Task 8: Deck → prompt mapping UI

**Files:**
- Modify: `anki_ai_improver/settings.py`, `anki_ai_improver/config.py`, `anki_ai_improver/config_test.py`

- [ ] settings dialog gets a table: deck (picker, stores deck id) → prompt name (dropdown from `prompts`); prompt texts stay in Anki's JSON config editor
- [ ] pure `set_deck_prompt(config, deck_id, name)` / `remove_deck_prompt(...)` + tests (add, replace, remove, unknown prompt rejected)
- [ ] run tests — must pass before Task 9
- [ ] manual check: save, reopen; API key appears in neither `meta.json` nor `config.json`

### Task 9: Verify acceptance criteria
- [ ] English deck card → English prompt; Portuguese subdeck card → Portuguese prompt; unmapped deck → default
- [ ] filtered deck card uses home deck prompt
- [ ] partial accept writes only ticked fields; Ctrl+Z restores
- [ ] 401 / timeout / garbage / truncated response → warning, no write
- [ ] card advanced while request in flight → accept refused
- [ ] `make test lint` green; `make package` zip has no tests

### Task 10: [Final] Update documentation
- [ ] README: install (symlink/`.ankiaddon`), configuration, example English/Portuguese prompts, privacy note (card content is sent to the configured provider)
- [ ] add CLAUDE.md for the repo (layout, `make` targets, pure-core rule)
- [ ] move this plan to `docs/plans/completed/`

## Post-Completion
*Informational only*

**Manual verification:**
- daily use on real English/Portuguese decks for a week; tune the default system contract
- check edited notes sync to AnkiMobile/AnkiDroid unchanged

**External:**
- optional: publish on AnkiWeb add-ons (needs repo made public → strip personal data first)
