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

Key: only `user_files/secret.json` `{"api_key": "..."}` (chmod 600), set through the masked key dialog. No env var (Dock/menu-launched Anki never sees it). Never in `config.json` or `meta.json`.

Prompt resolution: candidates = `[card.current_deck_id()] + [d["id"] for d in reversed(col.decks.parents(did))]` (nearest parent first) → first id present in `decks` whose prompt exists → else `default_prompt`. Pure `candidate_deck_ids(current_did, parent_ids_root_first) -> list[int]` builds the list; `resolve_prompt` takes it.

Provider-agnostic: any OpenAI-compatible `/chat/completions` endpoint (OpenRouter for testing; OpenAI, Groq, Gemini's and Anthropic's OpenAI-compatible endpoints, Ollama/LM Studio). `client.py` holds no provider hostnames or provider-specific branches; only `base_url`, `model`, key.

Request (`POST {base_url}/chat/completions`, `Authorization: Bearer <key>`, `response_format: {"type": "json_object"}`; on HTTP 400 whose body mentions `response_format`, retry once without it — providers/models differ in JSON-mode support):
- system: `<prompt>\n\nReturn ONLY a JSON object {"fields": {<field name>: <html>}} using exactly the field names given. Keep HTML formatting and media references unchanged unless asked.`
- user: `{"note_type": "Basic", "deck": "Portuguese", "tags": [...], "fields": {"Front": "...", "Back": "..."}}`

Response parse → `Proposal(changed: dict[str, str], raw: str)`:
- `bad_response` (raw kept, nothing applied) when: empty `choices`, `content` null, `finish_reason == "length"`, no JSON object (plain or first ```` ```json ```` fence), `fields` missing/not a dict, a value not a string.
- otherwise: drop unknown field names, keep missing fields unchanged, drop values equal to current.

Errors (`AiError(kind, message)` in `errors.py`, created in Task 1): `no_config`, `auth` (401/403), `rate_limit` (429), `server` (5xx), `timeout`, `network`, `bad_response`.

Staleness guard (pure `is_stale(snapshot, current_note_id: int | None, current_mtime: int | None, current_target_id: int | None) -> bool`; `None` id = note deleted): on accept, refuse when the note is deleted, its `mtime` changed, or the reviewer card / editor note is no longer the one sent.

## What Goes Where
- Implementation Steps: code + tests in `~/anki-ai-improver`.
- Post-Completion: manual daily use, optional AnkiWeb publishing.

## Implementation Steps

### Task 1: Repo scaffold and test tooling

**Files:**
- Create: `anki_ai_improver/__init__.py`, `anki_ai_improver/errors.py`, `anki_ai_improver/config.json`, `anki_ai_improver/manifest.json`, `anki_ai_improver/import_test.py`
- Modify: `pyproject.toml`, `uv.lock`, `.gitignore` (bootstrapped before the run; `Makefile` is final, do not change it)
- Create: `README.md`

- [x] `__init__.py`: `try: from aqt import mw` / `except ImportError: mw = None`; `if mw: from . import addon` (addon.py added in Task 5)
- [x] `manifest.json` (`package`, `name`, `min_point_version`: 260900 — Anki 26.09+, both editors present there) and default `config.json` from Technical Details
- [x] `errors.py`: `AiError(kind, message)` with the kinds from Technical Details
- [x] `pyproject.toml`: add `requests` and `types-requests` to dev deps (Anki provides `requests` at runtime), `uv lock`; mypy overrides for `aqt`/`anki` and the Qt modules are already bootstrapped
- [x] `.gitignore`: add `user_files/`, `*.ankiaddon`, `dist/`
- [x] `import_test.py`: `anki_ai_improver` and `anki_ai_improver.errors` import without `aqt` loaded; Tasks 2–5 each add their new pure module to it

### Task 2: Config and secret storage (`config.py`)

**Files:**
- Create: `anki_ai_improver/config.py`, `anki_ai_improver/config_test.py`
- Modify: `anki_ai_improver/import_test.py` (add the config module)

- [x] `Settings` dataclass + `from_dict(dict)`; missing `base_url`/`model` → `AiError("no_config")`
- [x] `load_api_key(user_files: Path)` reads `secret.json`; `save_api_key(...)` creates `user_files/` if missing and writes with mode 600
- [x] tests: defaults, missing fields, file round-trip + mode 600, absent or corrupt file → None, save into a missing `user_files/`
- [x] run tests — must pass before Task 3

### Task 3: Prompt resolution and message build (`prompts.py`)

**Files:**
- Create: `anki_ai_improver/prompts.py`, `anki_ai_improver/prompts_test.py`
- Modify: `anki_ai_improver/import_test.py` (add the prompts module)

- [x] `candidate_deck_ids(current_did, parent_ids_root_first)` → `[current, nearest parent, …, root]`
- [x] `resolve_prompt(candidate_deck_ids: list[int], settings) -> (name, text)`
- [x] `NoteSnapshot` (note id, mtime, card id, note type, deck name, tags, ordered fields) + `build_messages(prompt_text, snapshot)`
- [x] tests: `candidate_deck_ids` order (root, child, grandchild)
- [x] tests: exact deck, subdeck inherits parent, grandchild picks nearest mapped parent, unmapped → default, mapped prompt name missing from `prompts` → default
- [x] tests: messages contain all field names and the JSON contract
- [x] run tests — must pass before Task 4

### Task 4: OpenAI-compatible client and response parsing (`client.py`)

**Files:**
- Create: `anki_ai_improver/client.py`, `anki_ai_improver/client_test.py`
- Modify: `anki_ai_improver/import_test.py` (add the client module)

- [x] `complete(settings, api_key, messages, session=requests) -> dict` (response JSON); maps HTTP/timeout/network to `AiError`
- [x] `parse_proposal(response, current_fields) -> Proposal` per Technical Details
- [x] retry once without `response_format` on a 400 mentioning it
- [x] tests (fake session): success, 401, 429, 500, timeout, connection error, 400 `response_format` → retried without it, other 400 → no retry; request carries `Authorization: Bearer` and `model`, URL is `{base_url}/chat/completions` (trailing slash handled)
- [x] tests: plain JSON, fenced JSON, prose + JSON, garbage, empty choices, null content, `finish_reason=length`, non-string value → `bad_response` with raw; unknown/missing/unchanged fields
- [x] run tests — must pass before Task 5

### Task 5: Shared flow, minimal key dialog and diff dialog

**Files:**
- Create: `anki_ai_improver/logic.py`, `anki_ai_improver/logic_test.py`
- Modify: `anki_ai_improver/import_test.py` (add the logic module)
- Create: `anki_ai_improver/addon.py`, `anki_ai_improver/dialog.py`, `anki_ai_improver/settings.py`

- [ ] `logic.py` (pure): `merge_accepted(fields, proposal, accepted_names)`, `is_stale` per Technical Details
- [ ] `settings.py`: minimal dialog with masked API key (writes `secret.json`), base URL, model; registered via `mw.addonManager.setConfigAction` + Tools menu
- [ ] `addon.py` `improve(parent, snapshot, candidate_deck_ids, apply)`: no key/config → open the key dialog; else `QueryOp(op=network call).without_collection().failure(show AiError).with_progress().run_in_background()`; snapshot built on main thread before the op
- [ ] `dialog.py` `DiffDialog`: per changed field old/new as plain text in `QTextBrowser` (never `AnkiWebView`), checkbox each (default ticked), prompt dropdown + Retry, raw response view on `bad_response`
- [ ] on accept: `is_stale` → warn and stop; else `apply(merge_accepted(...))`
- [ ] tests for `merge_accepted` and `is_stale` (note deleted, mtime changed, target switched, fresh)
- [ ] run tests — must pass before Task 6

### Task 6: Reviewer trigger

**Files:**
- Modify: `anki_ai_improver/addon.py`, `anki_ai_improver/logic.py`, `anki_ai_improver/logic_test.py`

- [ ] context-menu entry via `gui_hooks.reviewer_will_show_context_menu`
- [ ] shortcut via `gui_hooks.state_shortcuts_will_change`, only when `state == "review"`; key from config via pure `review_shortcut(config) -> tuple[str, str] | None` (`None` = disabled)
- [ ] apply = fields onto the captured note → `update_note(parent=mw, note=note).run_in_background()` (undo + reviewer redraw)
- [ ] tests for `review_shortcut` (default, custom, empty → `None`)
- [ ] run tests — must pass before Task 7

### Task 7: Editor trigger (both editors)

**Files:**
- Modify: `anki_ai_improver/addon.py`, `anki_ai_improver/logic.py`, `anki_ai_improver/logic_test.py`

- [ ] `buttons.append(editor.addButton(...))` in `gui_hooks.editor_did_init_buttons` (callback already runs after save)
- [ ] detect the Svelte editor without importing it unguarded: `NewEditor = getattr(aqt.editor, "NewEditor", None)`; `is_new_editor = NewEditor is not None and isinstance(editor, NewEditor)`
- [ ] pure `editor_mode(is_new_editor, has_note_in_col, is_add_window) -> "update" | "fill_in_place" | "disabled"` + tests for every combination
- [ ] legacy `Editor` Edit/Browse: `update_note(parent=editor.parentWindow, note=captured)`; windows reload themselves
- [ ] legacy `Editor` Add: write fields onto `editor.note`, `editor.loadNote()`; no collection write
- [ ] `NewEditor` Edit: `update_note` then `editor.reload_note()`; `NewEditor` Add (`nid` None): button disabled with tooltip
- [ ] run tests — must pass before Task 8

### Task 8: Prompts tab and deck → prompt mapping UI

**Files:**
- Modify: `anki_ai_improver/settings.py`, `anki_ai_improver/config.py`, `anki_ai_improver/config_test.py`

- [ ] Prompts tab: list of prompts (add / rename / delete) + multi-line text box; default prompt marked and not deletable
- [ ] Decks tab: table deck (picker, stores deck id) → prompt name (dropdown from `prompts`)
- [ ] pure config helpers: `add_prompt`, `rename_prompt` (rewrites `decks` and `default_prompt` references), `delete_prompt` (refuses default; removes its deck mappings), `set_deck_prompt`, `remove_deck_prompt`
- [ ] tests: add duplicate name rejected, rename updates mappings + default, delete default refused, delete clears mappings, set/replace/remove mapping, unknown prompt rejected
- [ ] run tests — must pass before Task 9

### Task 9: [Final] Update documentation

**Files:**
- Modify: `README.md`
- Create: `CLAUDE.md`

- [ ] README: install (symlink/`.ankiaddon`), configuration, example English/Portuguese prompts, privacy note (card content is sent to the configured provider)
- [ ] add CLAUDE.md for the repo (layout, `make` targets, pure-core rule)

## Acceptance Criteria
- Run: `make package && ! python3 -m zipfile -l dist/anki_ai_improver.ankiaddon | grep -E '_test\.py|__pycache__|user_files'`
- Run: `uv run python -c "import json; m=json.load(open('anki_ai_improver/manifest.json')); assert m['min_point_version'] >= 260900"`
- Run: `uv run python -c "import json; c=json.load(open('anki_ai_improver/config.json')); assert c['decks'] == {} and c['shortcut'] == 'Ctrl+Alt+J' and 'api_key' not in json.dumps(c)"`
- Run: `! grep -rn 'ANKI_AI_API_KEY\|AnkiWebView' anki_ai_improver/`
- Run: `uv run python -c "import sys, anki_ai_improver.config, anki_ai_improver.prompts, anki_ai_improver.client, anki_ai_improver.logic; assert 'aqt' not in sys.modules"`
- `prompts_test.py` covers: exact deck, subdeck inherits nearest mapped parent, unmapped → default, missing prompt name → default
- `client_test.py` covers: 401, 429, 5xx, timeout, network error, fenced JSON, garbage, empty choices, null content, `finish_reason=length`, non-string value, unknown/missing/unchanged fields
- `logic_test.py` covers `merge_accepted` (only ticked fields written) and `is_stale` (deleted, mtime changed, target switched, fresh)
- `config_test.py` covers `secret.json` written with mode 600 and prompt rename rewriting deck mappings and `default_prompt`
- Run: `grep -q 'update_note' anki_ai_improver/addon.py && ! grep -nE 'col\.db|col\.update_note' anki_ai_improver/addon.py`
- Run: `! grep -niE 'openrouter|openai\.com|anthropic\.com|groq' anki_ai_improver/client.py`
- `addon.py` registers `reviewer_will_show_context_menu`, `state_shortcuts_will_change` (review state only), `editor_did_init_buttons`, and branches on `NewEditor` for the editor apply path

## Post-Completion
*Informational only*

**Manual verification** (on the Mac, Anki 26.09+, add-on linked with `make link`):
- reviewer: context menu + Ctrl+Alt+J open the diff; accept writes ticked fields only; Ctrl+Z undoes
- English deck card → English prompt; Portuguese subdeck card → Portuguese prompt; unmapped deck → default; filtered deck → home deck prompt
- 401 / timeout / garbage response → warning, no write; card advanced while request in flight → accept refused
- editor: Edit, Browse, Add in the legacy editor; Edit + Add (button disabled) with the Svelte editor experiment on
- settings: save, reopen; API key appears in neither `meta.json` nor `config.json`
- daily use on real English/Portuguese decks for a week; tune the default system contract
- check edited notes sync to AnkiMobile/AnkiDroid unchanged

**Housekeeping:**
- move this plan to `docs/plans/completed/`

**External:**
- optional: publish on AnkiWeb add-ons (needs repo made public → strip personal data first)
