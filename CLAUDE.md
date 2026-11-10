# Repository guide

## Layout

- `anki_ai_improver/` contains the add-on. `addon.py`, `settings.py`, and `dialog.py` connect its behavior to Anki; `client.py` handles the OpenAI-compatible request and response parsing.
- `config.py`, `prompts.py`, `logic.py`, and `errors.py` hold configuration, prompt selection/message construction, small decision rules, and domain errors.
- Output rules live in `prompts.py` and stay deck-agnostic; the optional quality gate lives in `gate.py`.
- `*_test.py` files sit beside the code they cover. `manifest.json` and `config.json` are Anki add-on metadata and defaults.

## Make targets

- `make test` runs pytest.
- `make lint` runs Ruff checks and formatting verification, then mypy on the add-on package.
- `make link ADDONS=<Anki2>/addons21` links the package into Anki's add-ons folder for local development.
- `make package` builds `dist/anki_ai_improver.ankiaddon`, excluding tests and local user files.

## Pure-core rule

Keep decision-making and data transformation in modules that can run without Anki UI objects. Anki integration belongs at the edges: capture note data, call core functions, and apply reviewed changes. Keep Qt and Anki imports out of the pure core so its behavior can be tested with ordinary Python tests.
