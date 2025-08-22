# Personal Productivity API (Alpha Scaffold)


![CI](https://github.com/thekitbag/ppapp-fastapi/actions/workflows/ci.yml/badge.svg)

## Quickstart
```bash
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000/docs

## Makefile shortcuts

With the included `Makefile` you can use:

```bash
# run the dev server with reload
make dev

# seed demo tasks (BASE_URL defaults to http://127.0.0.1:8000)
make seed
BASE_URL=http://127.0.0.1:8001 make seed

# run tests using the venv interpreter
make test

