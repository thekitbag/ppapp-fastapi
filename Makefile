.PHONY: dev seed

dev:
	uvicorn app.main:app --reload

seed:
	bash scripts/seed.sh
