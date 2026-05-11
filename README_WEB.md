# ZangerPro AI — Web

Web-first product on top of Legal Engine v2. Telegram is **not** part of the
main UX; the legacy bot in `app/bot/` stays available as a separate entry
point but is never imported by the web server.

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env
uvicorn app.web.main:app --reload
```

Open http://localhost:8000

The web server starts **without** `BOT_TOKEN`. `OPENAI_API_KEY` is
optional — without it the engine returns a structured skeleton/fallback.

## Env vars (essentials)

- `SECRET_KEY` — signs the session cookie. Required in production.
- `DATABASE_URL` or `ZANGERPRO_DB_PATH` — SQLite path (default `var/zangerpro.db`).
- `STORAGE_DIR` — where DOCX files are written (default `exports/`).
- `OPENAI_API_KEY` — enables LLM-augmented answers and voice STT.
- `ADMIN_EMAIL` / `ADMIN_PASSWORD` — bootstraps the admin user on first start.
- `PAYLINK_SHOP_ID` + `PAYLINK_SECRET_KEY` — Halyk PayLink (optional, live).
- `HALYK_EPAY_TERMINAL` + `HALYK_EPAY_SECRET` — Halyk ePay (optional, live).

## Smoke

```bash
# Health
curl http://localhost:8000/health

# Public
curl http://localhost:8000/
curl http://localhost:8000/pricing
```

## Deployment

- Railway / Render: use the included `Procfile`.
- Docker: build and run `Dockerfile` (port 8000).
- Production: set `APP_ENV=production`, configure HTTPS, set a strong
  `SECRET_KEY`, point `DATABASE_URL` to PostgreSQL or persistent SQLite.

## Tests

```bash
pytest tests/test_web_mvp_v2.py -q
pytest tests/test_web_auth_v2.py -q
pytest tests/test_web_documents_v2.py -q
pytest tests/test_web_payments_v2.py -q
pytest tests/test_web_voice_v2.py -q
pytest tests/test_web_i18n_v2.py -q
```

The legacy engine v2 tests stay green:

```bash
pytest tests/test_legal_engine_v2.py tests/test_document_factory_v2.py \
       tests/test_voice_bridge_v2.py tests/test_legal_hierarchy_v2.py \
       tests/test_legal_conflict_resolver_v2.py \
       tests/test_procedure_navigator_v2.py \
       tests/test_procedural_documents_v2.py \
       tests/test_docx_export_v2.py tests/test_slot_filler_v2.py -q
```
