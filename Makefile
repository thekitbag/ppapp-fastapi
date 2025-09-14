# Use bash so we can set pipefail, etc.
SHELL := /bin/bash

.PHONY: dev seed venv deps lint test test-verbose test-sqlite openapi collect review-backend clean

# -------- Config --------
PY ?= python3
VENVBIN ?= .venv/bin
RUN ?= $(VENVBIN)/
BUNDLE_DIR ?= review_bundle/backend

# Helpful: fail fast if any step in a pipeline fails
PIPEFAIL = set -o pipefail

# -------- App convenience --------
dev:
	$(RUN)uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

seed:
	bash scripts/seed.sh

# -------- Tooling setup --------
venv:
	@if [ ! -d ".venv" ]; then $(PY) -m venv .venv; fi
	@$(RUN)pip install --upgrade pip

deps: venv
	# remove -q so we can see resolver/progress + failures
	@$(RUN)pip install -r requirements.txt

# -------- Lint --------
lint: deps
	@mkdir -p $(BUNDLE_DIR)
	@{ $(PIPEFAIL); echo "== Ruff ==";        $(RUN)ruff check            2>&1 | tee $(BUNDLE_DIR)/ruff.txt; }
	@{ $(PIPEFAIL); echo "== Black ==";       $(RUN)black --check .       2>&1 | tee $(BUNDLE_DIR)/black.txt; }
	@{ $(PIPEFAIL); echo "== Mypy ==";        $(RUN)mypy                  2>&1 | tee $(BUNDLE_DIR)/mypy.txt; }

# -------- Tests --------
# Fast, chatty default: no output suppression; show where it hangs; fail if anything in the pipe fails
test: deps
	@mkdir -p $(BUNDLE_DIR)
	@{ $(PIPEFAIL); echo "== Pytest =="; \
	  PYTHONPATH=. \
	  FAULTHANDLER_TIMEOUT=60 \
	  $(RUN)pytest -vv -s --maxfail=1 --durations=10 2>&1 | tee $(BUNDLE_DIR)/pytest.txt; }
	@$(RUN)pip freeze > $(BUNDLE_DIR)/requirements.lock

# Run tests with an ephemeral local SQLite DB (avoids hanging on Postgres)
test-sqlite: deps
	@mkdir -p $(BUNDLE_DIR) tmp
	@{ $(PIPEFAIL); echo "== Pytest (SQLite) =="; \
	  PYTHONPATH=. \
	  DATABASE_URL=sqlite+aiosqlite:///./tmp/test.db \
	  AUTH_PROVIDER=dev \
	  DISABLE_EXTERNAL_CALLS=1 \
	  FAULTHANDLER_TIMEOUT=60 \
	  $(RUN)pytest -vv -s -k "not e2e and not integration" --maxfail=1 --durations=10 2>&1 | tee $(BUNDLE_DIR)/pytest_sqlite.txt; }

# Super-verbose: no tee, no pipe – ideal for live debugging
test-verbose: deps
	@PYTHONPATH=. FAULTHANDLER_TIMEOUT=60 $(RUN)pytest -vv -s --maxfail=1

# -------- OpenAPI --------
openapi: deps
	@mkdir -p $(BUNDLE_DIR)
	@echo "== OpenAPI =="
	# Try a live server first; if not running, generate from the app object
	@curl -fsS http://127.0.0.1:8000/openapi.json > $(BUNDLE_DIR)/openapi.json || \
	$(RUN)python - <<'PY' > $(BUNDLE_DIR)/openapi.json
	from app.main import app
	import json
	print(json.dumps(app.openapi(), indent=2))
	PY
		@echo "Wrote $(BUNDLE_DIR)/openapi.json"

# -------- Collect artifacts for review --------
collect:
	@mkdir -p $(BUNDLE_DIR)
	@cp -f pyproject.toml $(BUNDLE_DIR) 2>/dev/null || true
	@cp -f requirements.txt $(BUNDLE_DIR) 2>/dev/null || true
	@cp -f Dockerfile $(BUNDLE_DIR) 2>/dev/null || true
	@cp -f fly.toml $(BUNDLE_DIR) 2>/dev/null || true
	@cp -rf alembic $(BUNDLE_DIR)/ 2>/dev/null || true
	@cp -rf app $(BUNDLE_DIR)/ 2>/dev/null || true
	@echo "commit: $$(git rev-parse --short HEAD)" > $(BUNDLE_DIR)/SUMMARY.md
	@git diff --stat origin/main...HEAD >> $(BUNDLE_DIR)/SUMMARY.md || true
	@alembic heads -v 2>/dev/null >> $(BUNDLE_DIR)/SUMMARY.md || true

review-backend: lint test-sqlite openapi collect
	@echo "Backend review artifacts in $(BUNDLE_DIR)"

clean:
	@rm -rf $(BUNDLE_DIR) .pytest_cache .mypy_cache .ruff_cache tmp