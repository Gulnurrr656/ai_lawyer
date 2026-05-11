"""ZangerPro AI web application package.

The web app is **Kazakh-first** and intentionally separated from the legacy
Telegram bot in :mod:`app.bot`. Importing :mod:`app.web` MUST NOT import
``aiogram`` or ``app.bot``; the web server starts independently of the
``BOT_TOKEN`` env variable.
"""
