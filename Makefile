.PHONY: test lint link package

PKG := anki_ai_improver

# pytest exit 5 = no tests collected yet
test:
	uv run pytest -q || [ $$? -eq 5 ]

lint:
	uv run ruff check .
	uv run ruff format --check .
	if [ -d $(PKG) ]; then uv run mypy $(PKG); fi

# make link ADDONS=<Anki2>/addons21
link:
	@test -n "$(ADDONS)" || { echo "usage: make link ADDONS=<addons21 dir>"; exit 1; }
	ln -sfn "$(CURDIR)/$(PKG)" "$(ADDONS)/$(PKG)"

package:
	mkdir -p dist
	uv run python -c "import pathlib, zipfile; src = pathlib.Path('$(PKG)'); skip = lambda f: f.name.endswith('_test.py') or '__pycache__' in f.parts or 'user_files' in f.parts or f.name == 'meta.json'; z = zipfile.ZipFile('dist/$(PKG).ankiaddon', 'w', zipfile.ZIP_DEFLATED); [z.write(f, f.relative_to(src)) for f in sorted(src.rglob('*')) if f.is_file() and not skip(f)]; z.close()"
