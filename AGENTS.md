# Repository Guidelines

## Project Structure & Modules
- Root: `requirements.txt`, `README.md`, `.envrc` (env vars for local dev).
- `src/django_ragamuffin/`: installable Django app (models, views, `static/`, `templates/`, `tests/`).
- `backend/`: runnable Django project (`manage.py`, `backend/settings.py`, `pytest.ini`, app integration).
- Packaging: run builds from `src/` (see below).

## Build, Test, and Development
- Install deps: `python3.11 -m venv env && source env/bin/activate && pip install -r requirements.txt` (run from repo root).
- Run server (dev): `cd backend && python manage.py migrate && python manage.py runserver`.
- Run tests: `cd backend && pytest -s` (uses `DJANGO_SETTINGS_MODULE=backend.settings` from `pytest.ini`).
- Build package: `cd src && python -m build` (produces wheels/sdist in `src/dist/`).

## Coding Style & Naming
- Python 3.11+, PEP 8, 4‑space indentation; add type hints where reasonable.
- Modules/files: `snake_case`; classes: `CamelCase`; constants: `UPPER_SNAKE`.
- Django: keep app code under `django_ragamuffin/`; templates in `templates/`; static assets in `static/django_ragamuffin/`.
- HTML templates: `djhtml` is available; format as needed (e.g., `djhtml -i path/to/template.html`).

## Testing Guidelines
- Framework: `pytest` with Django; tests live in `backend/tests.py` and `src/django_ragamuffin/tests/`.
- Naming: `tests.py`, `test_*.py`, `*_tests.py` (per `pytest.ini`).
- Run focused tests: `cd backend && pytest -k name -q`.
- Prefer `django.test.TestCase` for DB use; stub external services and avoid real API calls.

## Commit & Pull Request Guidelines
- History shows short, imperative subjects (e.g., “Fix path for questions”). Keep subjects ≤ 50 chars.
- Prefer prefixes when helpful: `feat:`, `fix:`, `chore:`, `docs:`, `test:`; reference issues (e.g., `#123`).
- PRs: include what/why, screenshots for UI/admin changes, migration notes, and how to test. Ensure `pytest` passes and app runs.

## Security & Configuration Tips
- Do not commit secrets. Use environment variables (`OPENAI_API_KEY`, Postgres `PG*`, `DJANGO_SETTINGS_MODULE`).
- `OPENAI_UPLOAD_STORAGE` controls media path; ensure directory exists and is writable.
- For local dev, `direnv`/`.envrc` can export vars; keep sensitive values out of commits.

