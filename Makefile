.PHONY: test lint link package

PKG := anki_ai_improver

# pytest exit 5 = no tests collected yet
test:
	uv run pytest -q || [ $$? -eq 5 ]

lint:
	uv run ruff check .
	uv run ruff format --check .
	if [ -d $(PKG) ]; then uv run mypy $(PKG); fi

# make link ADDONS=<profile>/addons21
link:
	@test -n "$(ADDONS)" || { echo "usage: make link ADDONS=<addons21 dir>"; exit 1; }
	ln -sfn "$(CURDIR)/$(PKG)" "$(ADDONS)/$(PKG)"

package:
	mkdir -p dist
	rm -f dist/$(PKG).ankiaddon
	cd $(PKG) && zip -r ../dist/$(PKG).ankiaddon . -x '*_test.py' '*__pycache__*' 'user_files/*' 'meta.json'
