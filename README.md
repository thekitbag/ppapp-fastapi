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


## Testing

The test suite configures the app in a dedicated test mode to support the recent multi‑tenant refactor:

- Test database: During `pytest`, `app/main.py` overrides the default DB to `sqlite:///./test.db`, recreating schema fresh per run. This avoids schema drift with the development database and ensures deterministic tests.
- Auth override: API routes are auto‑authenticated as a seeded test user (`id: user_test`) via a dependency override, so tests do not need to manage cookies.
- Service tests: Service methods are multi‑tenant and typically require a `user_id`. Tests should pass a user ID explicitly and can seed a user using the provided in‑memory session (see examples in `tests/services/*`).

Writing new tests:
- API tests: Import `app.main.app` and use `TestClient(app)`. No auth headers/cookies are required due to the test override.
- Service tests: Use the `test_db` fixture from `tests/repositories/conftest.py`, create a user (or reuse the seeded one), and pass `user_id` to service methods.

Notes:
- If you prefer an in‑memory DB across requests, we can switch the override to `sqlite:///:memory:` using `StaticPool`. The current on‑disk `test.db` keeps things simple and persistent during a test session.
- The overrides only apply when running under `pytest` and do not affect dev or production.

### Microsoft OAuth in development
- Azure permits HTTP redirect URIs only for `localhost` (not `127.0.0.1`). Set `MS_REDIRECT_URI=http://localhost:8000/auth/ms/callback` in `.env.local` and add the same value to your Azure app registration.
- The dev server is accessible via both `localhost` and `127.0.0.1`, but the OAuth redirect must exactly match the Azure configuration.

### Google OAuth in development
- Google permits HTTP redirect URIs only for `localhost` (not `127.0.0.1`). Set `GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback` in `.env.local` and add the same value to your Google Cloud Console OAuth client.
- Ensure the OAuth client type is “Web application” and the redirect URI matches exactly; JavaScript origins are not required for this server-side flow.
