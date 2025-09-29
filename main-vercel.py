import asyncio
import os
import sys
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from telegram import Update
from telegram.ext import Application

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))

from skel_telegram_bot.bot import build_application

app = FastAPI()
telegram_app: Application | None = None
startup_lock = asyncio.Lock()
favicon_dir = Path(__file__).resolve().parent / "favicon"
if favicon_dir.exists():
    app.mount("/favicon", StaticFiles(directory=str(favicon_dir)), name="favicon")
    favicon_path = favicon_dir / "favicon.ico"

    if favicon_path.exists():

        @app.get("/favicon.ico")
        async def favicon() -> FileResponse:  # type: ignore[override]
            return FileResponse(favicon_path)


async def _ensure_app() -> Application:
    global telegram_app
    if telegram_app:
        return telegram_app
    async with startup_lock:
        if telegram_app:
            return telegram_app
        telegram_app = build_application()
        await telegram_app.initialize()
        await telegram_app.start()
        webhook_url = os.getenv("WEBHOOK_URL")
        if webhook_url:
            await telegram_app.bot.set_webhook(webhook_url, drop_pending_updates=True)
        return telegram_app


@app.on_event("shutdown")
async def shutdown_event() -> None:
    global telegram_app
    if telegram_app:
        await telegram_app.stop()
        await telegram_app.shutdown()
        telegram_app = None


@app.post("/webhook")
async def handle_webhook(request: Request) -> Response:
    application = await _ensure_app()
    payload = await request.json()
    update = Update.de_json(payload, application.bot)
    await application.process_update(update)
    return Response(status_code=200)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
