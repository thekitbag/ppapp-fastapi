.PHONY: dev seed

dev:
	uvicorn app.main:app --reload

seed:
	bash scripts/seed.sh

.PHONY: test
test:
	PYTHONPATH=$(PWD) pytest --disable-warnings --maxfail=1

