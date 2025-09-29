import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(slots=True)
class Config:
    telegram_bot_token: str
    agent_base_url: str
    processor_id: str


def load_config() -> Config:
    load_dotenv()

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("Environment variable 'TELEGRAM_BOT_TOKEN' is required.")

    base_url = os.getenv("AGENT_BASE_URL", "http://127.0.0.1:8000")
    processor_id = os.getenv("AGENT_PROCESSOR_ID", "telegram-bot")
    return Config(
        telegram_bot_token=token,
        agent_base_url=base_url.rstrip("/"),
        processor_id=processor_id,
    )


config = load_config()
