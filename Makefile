.PHONY: dev seed test

# Use binaries from the virtual environment
VENV = .venv
BIN = $(VENV)/bin

# If .venv doesn't exist, we might be in a container or system environment, 
# so we fall back to PATH (optional, but good for flexibility)
ifneq ($(wildcard $(BIN)/uvicorn),)
    UVICORN = $(BIN)/uvicorn
    PYTEST = $(BIN)/pytest
else
    UVICORN = uvicorn
    PYTEST = pytest
endif

dev:
	$(UVICORN) app.main:app --reload

seed:
	bash scripts/seed.sh

test:
	PYTHONPATH=$(PWD) $(PYTEST) --disable-warnings --maxfail=1

