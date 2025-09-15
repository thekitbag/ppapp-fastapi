# ---------- Phony ----------
.PHONY: dev seed test test-all deps venv lint openapi collect review-backend clean

# ---------- Simple, fast local targets ----------
dev:
	uvicorn app.main:app --reload

seed:
	bash scripts/seed.sh

# Your old speedy test (no deps). Keeps local runs snappy.
# PYTHONPATH so tests can import 'app' without installing the package.
test:
	PYTHONPATH=$(PWD) pytest --disable-warnings --maxfail=1

# ---------- Env & deps (explicit) ----------
PY ?= python3
VENVBIN ?= .venv/bin
RUN ?= $(VENVBIN)/

venv:
	@if [ ! -d ".venv" ]; then $(PY) -m venv .venv; fi
	@$(RUN)pip -q install --upgrade pip >/dev/null

# Only install when you ask for it (or via test-all/review-backend)
deps: venv
	@$(RUN)pip install -r requirements.txt

# ---------- Linters (optional) ----------
lint: deps
	@mkdir -p review_bundle/backend
	@echo "== Ruff ==" && ($(RUN)ruff check || true) | tee review_bundle/backend/ruff.txt
	@echo "== Black ==" && ($(RUN)black --check . || true) | tee review_bundle/backend/black.txt
	@echo "== Mypy ==" && ($(RUN)mypy || true) | tee review_bundle/backend/mypy.txt

# ---------- OpenAPI snapshot ----------
openapi: deps
	@mkdir -p review_bundle/backend
	@echo "== OpenAPI =="
	@curl -fsS http://127.0.0.1:8000/openapi.json > review_bundle/backend/openapi.json || \
	$(RUN)python - <<'PY' > review_bundle/backend/openapi.json
	from app.main import app
	import json
	print(json.dumps(app.openapi(), indent=2))
	PY
	@echo "Wrote review_bundle/backend/openapi.json"

# ---------- Collect review bundle ----------
collect:
	@mkdir -p review_bundle/backend
	@cp -f pyproject.toml review_bundle/backend 2>/dev/null || true
	@cp -f requirements.txt review_bundle/backend 2>/dev/null || true
	@cp -f Dockerfile review_bundle/backend 2>/dev/null || true
	@cp -f fly.toml review_bundle/backend 2>/dev/null || true
	@cp -rf alembic review_bundle/backend/ 2>/dev/null || true
	@cp -rf app review_bundle/backend/ 2>/dev/null || true
	@echo "commit: $$(git rev-parse --short HEAD)" > review_bundle/backend/SUMMARY.md
	@git diff --stat origin/main...HEAD >> review_bundle/backend/SUMMARY.md || true
	@alembic heads -v 2>/dev/null >> review_bundle/backend/SUMMARY.md || true

# ---------- Full runs (explicit) ----------
# CI-style tests: installs deps once, then runs tests
test-all: deps
	@mkdir -p review_bundle/backend
	@echo "== Pytest =="
	@$(RUN)pytest -q --maxfail=1 --disable-warnings | tee review_bundle/backend/pytest.txt
	@$(RUN)pip freeze > review_bundle/backend/requirements.lock

# One-click bundle you’ve been using
review-backend: lint test-all openapi collect
	@echo "Backend review artifacts in review_bundle/backend"

# ---------- Utilities ----------
clean:
	@rm -rf .venv .pytest_cache .mypy_cache review_bundle/backend