import asyncio
import os
import sys
from pathlib import Path
from typing import Dict
from weakref import WeakKeyDictionary

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from telegram import Update
from telegram.ext import Application

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))

from skel_telegram_bot.bot import build_application

app = FastAPI()

# Maintain an Application per running event loop so Vercel's request-scoped
# loops don't reuse clients tied to a closed loop.
_apps_by_loop: WeakKeyDictionary[asyncio.AbstractEventLoop, Application] = WeakKeyDictionary()
_locks_by_loop: WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = WeakKeyDictionary()
_webhook_registered: Dict[int, bool] = {}
favicon_dir = Path(__file__).resolve().parent / "favicon"
if favicon_dir.exists():
    app.mount("/favicon", StaticFiles(directory=str(favicon_dir)), name="favicon")
    favicon_path = favicon_dir / "favicon.ico"

    if favicon_path.exists():

        @app.get("/favicon.ico")
        async def favicon() -> FileResponse:  # type: ignore[override]
            return FileResponse(favicon_path)


async def _ensure_app() -> Application:
    loop = asyncio.get_running_loop()
    app = _apps_by_loop.get(loop)
    if app:
        return app

    lock = _locks_by_loop.get(loop)
    if lock is None:
        lock = asyncio.Lock()
        _locks_by_loop[loop] = lock

    async with lock:
        app = _apps_by_loop.get(loop)
        if app:
            return app

        app = build_application()
        await app.initialize()
        await app.start()

        webhook_url = os.getenv("WEBHOOK_URL")
        if webhook_url:
            key = id(app.bot)
            if not _webhook_registered.get(key):
                await app.bot.set_webhook(webhook_url, drop_pending_updates=True)
                _webhook_registered[key] = True

        _apps_by_loop[loop] = app
        return app


@app.on_event("shutdown")
async def shutdown_event() -> None:
    apps = list(_apps_by_loop.values())
    _apps_by_loop.clear()
    _locks_by_loop.clear()
    _webhook_registered.clear()

    for application in apps:
        try:
            await application.stop()
        finally:
            await application.shutdown()


@app.post("/webhook")
async def handle_webhook(request: Request) -> Response:
    application = await _ensure_app()
    payload = await request.json()
    update = Update.de_json(payload, application.bot)
    await application.process_update(update)
    return Response(status_code=200)


@app.get("/webhook")
async def webhook_ready() -> dict[str, str]:
    await _ensure_app()
    return {"status": "ready"}


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
