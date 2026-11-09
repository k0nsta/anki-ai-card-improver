.PHONY: test lint

# pytest exit 5 = no tests collected yet
test:
	uv run pytest -q || [ $$? -eq 5 ]

lint:
	uv run ruff check .
	uv run ruff format --check .
	if [ -d anki_ai_improver ]; then uv run mypy anki_ai_improver; fi
