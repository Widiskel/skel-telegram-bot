from __future__ import annotations

import html
import json

import re
from typing import Dict, Optional

from loguru import logger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, Message
from telegram.constants import ChatType, ParseMode
from telegram.ext import (Application, ApplicationBuilder, CommandHandler,
                          ContextTypes, MessageHandler, filters)

from .agent_client import AgentClient, AgentClientError
from .config.settings import config
from .utils.logger import setup_logger

SUPPORTED_LANGS = {"EN", "ID"}
DEFAULT_LANG = "EN"
LANG_DISPLAY = {"EN": "English", "ID": "Bahasa Indonesia"}
LANGUAGE_PREFS_KEY = "language_prefs"

LANG_TEXT: Dict[str, Dict[str, str]] = {
    "EN": {
        "start_greeting": (
            "Hello! I'm the Skel Helper Bot linked to the Skel Crypto Agent.\n\n"
            "What I can do for you:\n"
            "- Chat about crypto and offer lightweight analysis.\n"
            "- Provide instant price conversions, e.g. `1 BTC`, `1 BTC IDR`, `1 BTC to USD`.\n"
            "- Deliver deep project snapshots via /project <name>.\n"
            "- Surface gas tiers via /gas and Chainlist endpoints via /rpc.\n\n"
            "Need a refresher? Use /help."
        ),
        "invite_button": "Invite to Discussion Group",
        "help_text": (
            "Available commands:\n"
            "- /start — Reset the conversation and show the introduction.\n"
            "- /reset — Clear the conversation history kept by the agent.\n"
            "- /help — Display this help message.\n"
            "- /lang EN or /lang ID — Switch the bot language.\n"
            "- /project <name> — Request an in-depth project analysis.\n\n"
            "- /gas [network] [currency] — Check live gas fees (defaults to Ethereum/USD).\n"
            "- /rpc [network] — Fetch Chainlist RPC endpoints (default network: ETH).\n\n"
            "Capabilities:\n"
            "- General crypto chat and analysis with up-to-date context.\n"
            "- Instant price conversions, e.g. `1 BTC`, `1 BTC IDR`, `1 BTC to USD`.\n"
            "- Detailed project analysis via /project <name>.\n\n"
            "Send any text message to forward it to the Skel Crypto Agent."
        ),
        "reset_done": "Conversation history cleared.",
        "non_text_warning": "Sorry, I can only process text messages.",
        "agent_error": "The agent ran into a problem. Please try again shortly.",
        "lang_usage": "Usage: /lang EN or /lang ID.",
        "lang_invalid": "Unsupported language. Choose EN or ID.",
        "lang_no_permission": "You are not allowed to change the language here.",
        "lang_set": "Language set to {language}.",
        "project_usage": "Usage: /project <project name or symbol>.",
        "gas_usage": "Usage: /gas [network] [currency].",
        "gas_error": "Sorry, I couldn't fetch gas fees right now.",
        "rpc_usage": "Usage: /rpc [network]. (default: ETH)",
    },
    "ID": {
        "start_greeting": (
            "Halo! Aku Skel Helper Bot yang terhubung ke Skel Crypto Agent.\n\n"
            "Kemampuanku:\n"
            "- Mengobrol seputar crypto dengan analisis yang relevan.\n"
            "- Memberikan konversi harga instan, mis. `1 BTC`, `1 BTC IDR`, `1 BTC to USD`.\n"
            "- Menyajikan ringkasan proyek mendalam lewat /project <nama>.\n"
            "- Memberikan biaya gas via /gas serta daftar RPC melalui /rpc.\n\n"
            "Butuh pengingat? Gunakan /help."
        ),
        "invite_button": "Undang ke Grup Diskusi",
        "help_text": (
            "Perintah yang tersedia:\n"
            "- /start — Mulai ulang percakapan dan tampilkan pengantar.\n"
            "- /reset — Hapus riwayat percakapan yang disimpan agent.\n"
            "- /help — Tampilkan pesan bantuan ini.\n"
            "- /lang EN atau /lang ID — Ubah bahasa bot.\n"
            "- /project <nama> — Minta analisis proyek crypto secara mendalam.\n\n"
            "- /gas [jaringan] [mata uang] — Lihat biaya gas terkini (default Ethereum/USD).\n"
            "- /rpc [jaringan] — Ambil daftar RPC dari Chainlist (default ETH).\n\n"
            "Kemampuan:\n"
            "- Chat dan analisis crypto dengan konteks terbaru.\n"
            "- Konversi harga instan, mis. `1 BTC`, `1 BTC IDR`, `1 BTC to USD`.\n"
            "- Analisis proyek terperinci melalui /project <nama>.\n\n"
            "Kirim pesan teks apa pun untuk meneruskannya ke Skel Crypto Agent."
        ),
        "reset_done": "Riwayat percakapan dihapus.",
        "non_text_warning": "Maaf, aku hanya bisa memproses pesan teks.",
        "agent_error": "Agent sedang bermasalah. Coba lagi sebentar lagi.",
        "lang_usage": "Gunakan: /lang EN atau /lang ID.",
        "lang_invalid": "Bahasa tidak didukung. Pilih EN atau ID.",
        "lang_no_permission": "Kamu tidak memiliki izin untuk mengubah bahasa di sini.",
        "lang_set": "Bahasa diatur ke {language}.",
        "project_usage": "Gunakan: /project <nama atau simbol proyek>.",
        "gas_usage": "Gunakan: /gas [jaringan] [mata uang].",
        "gas_error": "Maaf, aku belum bisa mengambil data gas saat ini.",
        "rpc_usage": "Gunakan: /rpc [jaringan]. (default: ETH)",
    },
}

_GAS_NETWORK_PHRASES = {
    "ethereum": "ethereum",
    "ethereum mainnet": "ethereum",
    "mainnet": "ethereum",
    "eth": "ethereum",
    "base": "base",
    "base mainnet": "base",
    "binance smart chain": "bsc",
    "binance chain": "bsc",
    "bnb chain": "bsc",
    "binance": "bsc",
    "bsc": "bsc",
    "bnb": "bsc",
    "linea": "linea",
    "plasma": "plasma",
    "polygon": "plasma",
    "polygon plasma": "plasma",
    "polygon pos": "plasma",
    "matic": "plasma",
}

_GAS_NETWORK_KEYWORDS = {word for phrase in _GAS_NETWORK_PHRASES for word in phrase.split()}
_GAS_CURRENCY_STOPWORDS = {"chain", "smart", "network", "mainnet"}

_CONVERSION_PATTERN = re.compile(
    r"^\s*(?P<amount>\d+(?:[.,]\d+)?)\s*(?P<base>[A-Za-z0-9]{2,10})(?:\s*(?:to)?\s*(?P<quote>[A-Za-z]{2,10}))?\s*$",
    re.IGNORECASE,
)


def _language_prefs(context: ContextTypes.DEFAULT_TYPE) -> Dict[int, str]:
    return context.application.bot_data.setdefault(LANGUAGE_PREFS_KEY, {})


def _get_language(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> str:
    return _language_prefs(context).get(chat_id, DEFAULT_LANG)


def _set_language(context: ContextTypes.DEFAULT_TYPE, chat_id: int, lang: str) -> None:
    _language_prefs(context)[chat_id] = lang


def _msg(lang: str, key: str, **kwargs) -> str:
    bundle = LANG_TEXT.get(lang, LANG_TEXT[DEFAULT_LANG])
    template = bundle.get(key, LANG_TEXT[DEFAULT_LANG][key])
    return template.format(**kwargs)


def _build_invite_keyboard(text: str, invite_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(text, url=invite_url)]])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    agent: AgentClient = context.application.bot_data["agent_client"]
    chat = update.effective_chat
    chat_id = chat.id
    await agent.reset(str(chat_id))

    lang = _get_language(context, chat_id)
    _set_language(context, chat_id, lang)
    logger.info("Chat %s invoked /start (lang=%s)", chat_id, lang)

    bot_username = context.bot.username or "skel_crypto_bot"
    invite_url = f"https://t.me/{bot_username}?startgroup=true"

    greeting = _msg(lang, "start_greeting")
    keyboard = _build_invite_keyboard(_msg(lang, "invite_button"), invite_url)

    await update.effective_message.reply_text(
        greeting,
        disable_web_page_preview=True,
        reply_markup=keyboard,
    )

def _session_id(chat, user) -> str:
    if chat.type in {ChatType.GROUP, ChatType.SUPERGROUP} and user:
        return f"{chat.id}:{user.id}"
    return str(chat.id)


def _is_bot_addressed(message: Message, entities, bot_username: str, bot_id: int) -> bool:
    if message.reply_to_message and message.reply_to_message.from_user and message.reply_to_message.from_user.id == bot_id:
        return True

    if not entities:
        return False

    bot_tag = f"@{bot_username}" if bot_username else None
    for entity in entities:
        etype = getattr(entity, "type", None)
        if etype == "mention" and bot_tag:
            mention = message.text or message.caption or ""
            segment = mention[entity.offset: entity.offset + entity.length]
            if segment.lower() == bot_tag:
                return True
        elif etype == "text_mention" and getattr(entity, "user", None) and entity.user.id == bot_id:
            return True
    return False


def _strip_bot_reference(text: str, entities, bot_username: str, bot_id: int) -> str:
    if not text or not entities:
        return text

    bot_tag = f"@{bot_username}" if bot_username else None
    pieces = []
    cursor = 0
    for entity in entities:
        start = entity.offset
        end = entity.offset + entity.length
        etype = getattr(entity, "type", None)
        remove = False
        if etype == "mention" and bot_tag:
            segment = text[start:end]
            remove = segment.lower() == bot_tag
        elif etype == "text_mention" and getattr(entity, "user", None) and entity.user.id == bot_id:
            remove = True

        if remove:
            pieces.append(text[cursor:start])
            cursor = end
    pieces.append(text[cursor:])
    cleaned = ''.join(pieces)
    return cleaned


def _is_currency_candidate(token: str) -> bool:
    if not token:
        return False
    lowered = token.lower()
    if lowered in _GAS_NETWORK_KEYWORDS or lowered in _GAS_CURRENCY_STOPWORDS:
        return False
    if not lowered.isalpha():
        return False
    if len(lowered) < 2 or len(lowered) > 5:
        return False
    return True


def _normalize_gas_network(tokens: list[str]) -> str:
    if not tokens:
        return "ethereum"

    normalized = " ".join(tokens).lower().strip()
    if normalized in _GAS_NETWORK_PHRASES:
        return _GAS_NETWORK_PHRASES[normalized]

    parts = normalized.split()
    for size in range(len(parts), 0, -1):
        phrase = " ".join(parts[:size])
        if phrase in _GAS_NETWORK_PHRASES:
            return _GAS_NETWORK_PHRASES[phrase]

    for word in reversed(parts):
        if word in _GAS_NETWORK_PHRASES:
            return _GAS_NETWORK_PHRASES[word]

    return "ethereum"


def _parse_gas_args(args: list[str]) -> tuple[str, str]:
    if not args:
        return "ethereum", "USD"

    tokens = [arg for arg in args if arg]
    if not tokens:
        return "ethereum", "USD"

    potential_currency = tokens[-1]
    currency = None
    if _is_currency_candidate(potential_currency):
        currency = potential_currency.upper()
        tokens = tokens[:-1]

    network = _normalize_gas_network(tokens) if tokens else "ethereum"
    return network, (currency or "USD")


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    agent: AgentClient = context.application.bot_data["agent_client"]
    chat = update.effective_chat
    user = update.effective_user
    chat_id = chat.id
    lang = _get_language(context, chat_id)
    logger.info("Chat %s invoked /reset (lang=%s)", chat_id, lang)
    session_key = _session_id(chat, user)
    await agent.reset(session_key)
    await update.effective_message.reply_text(_msg(lang, "reset_done"))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    lang = _get_language(context, chat_id)
    logger.info("Chat %s invoked /help (lang=%s)", chat_id, lang)
    await update.effective_message.reply_text(
        _msg(lang, "help_text"),
        disable_web_page_preview=True,
    )


async def lang_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    user = update.effective_user
    current_lang = _get_language(context, chat.id)

    if not context.args:
        logger.info("Chat %s invoked /lang without args", chat.id)
        await update.effective_message.reply_text(_msg(current_lang, "lang_usage"))
        return

    requested = context.args[0].upper()
    if requested not in SUPPORTED_LANGS:
        logger.info("Chat %s provided unsupported /lang arg: %s", chat.id, requested)
        await update.effective_message.reply_text(_msg(current_lang, "lang_invalid"))
        return

    allowed = False
    if chat.type == ChatType.PRIVATE:
        allowed = True
    else:
        member = await context.bot.get_chat_member(chat.id, user.id)
        allowed = member.status in {"administrator", "creator", "owner"}

    if not allowed:
        logger.info("User %s attempted /lang without permission in chat %s", user.id, chat.id)
        await update.effective_message.reply_text(_msg(current_lang, "lang_no_permission"))
        return

    _set_language(context, chat.id, requested)
    logger.info("Chat %s language set to %s", chat.id, requested)
    await update.effective_message.reply_text(
        _msg(requested, "lang_set", language=LANG_DISPLAY[requested])
    )


async def project_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    agent: AgentClient = context.application.bot_data["agent_client"]
    chat = update.effective_chat
    user = update.effective_user
    message = update.effective_message
    lang = _get_language(context, chat.id)

    if not context.args:
        await message.reply_text(
            _msg(lang, "project_usage"),
            disable_web_page_preview=True,
        )
        return

    query = " ".join(context.args).strip()
    if not query:
        await message.reply_text(
            _msg(lang, "project_usage"),
            disable_web_page_preview=True,
        )
        return

    session_key = _session_id(chat, user)
    prompt = f"[LANG={lang}][PROJECT] {query}"
    logger.info("Chat %s requested /project: %s", session_key, query)

    try:
        reply = await agent.send(session_key, prompt)
    except AgentClientError as exc:
        logger.warning("Project analysis failed for %s: %s", session_key, exc)
        await message.reply_text(
            html.escape(_msg(lang, "agent_error")),
            parse_mode=ParseMode.HTML,
        )
        return

    await message.reply_text(
        reply,
        disable_web_page_preview=True,
        parse_mode=ParseMode.HTML,
    )


async def gas_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    agent: AgentClient = context.application.bot_data["agent_client"]
    chat = update.effective_chat
    user = update.effective_user
    message = update.effective_message
    lang = _get_language(context, chat.id)

    network, currency = _parse_gas_args(context.args or [])
    session_key = _session_id(chat, user)

    payload = json.dumps({"network": network, "currency": currency}, separators=(",", ":"))
    prompt = f"[LANG={lang}][GAS]{payload}"
    logger.info("Chat %s invoked /gas network=%s currency=%s", session_key, network, currency)

    try:
        reply = await agent.send(session_key, prompt)
    except AgentClientError as exc:
        logger.warning("Gas command failed for %s: %s", session_key, exc)
        await message.reply_text(_msg(lang, "gas_error"))
        return

    await message.reply_text(
        reply,
        disable_web_page_preview=True,
        parse_mode=ParseMode.HTML,
    )


async def rpc_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    agent: AgentClient = context.application.bot_data["agent_client"]
    chat = update.effective_chat
    user = update.effective_user
    message = update.effective_message
    lang = _get_language(context, chat.id)

    query = " ".join(context.args).strip() if context.args else ""
    if query == "":
        payload = json.dumps({"network": None}, separators=(",", ":"))
    else:
        payload = json.dumps({"network": query}, separators=(",", ":"))

    session_key = _session_id(chat, user)
    prompt = f"[LANG={lang}][RPC]{payload}"
    logger.info("Chat %s invoked /rpc network=%s", session_key, query or "default")

    try:
        reply = await agent.send(session_key, prompt)
    except AgentClientError as exc:
        logger.warning("RPC command failed for %s: %s", session_key, exc)
        await message.reply_text(html.escape(_msg(lang, "agent_error")), parse_mode=ParseMode.HTML)
        return

    await message.reply_text(
        reply,
        disable_web_page_preview=True,
        parse_mode=ParseMode.HTML,
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    agent: AgentClient = context.application.bot_data["agent_client"]
    message = update.effective_message
    if not message:
        return

    chat = update.effective_chat
    user = update.effective_user
    raw_text = (message.text or message.caption or "")
    entities = (message.entities if message.text else message.caption_entities) or []
    text = raw_text.strip()
    chat_id = chat.id
    lang = _get_language(context, chat_id)

    if not text:
        logger.info("Chat %s sent non-text content", chat_id)
        await message.reply_text(_msg(lang, "non_text_warning"))
        return

    is_group = chat.type in {ChatType.GROUP, ChatType.SUPERGROUP}
    allow_unaddressed_conversion = bool(_CONVERSION_PATTERN.match(text))

    if is_group:
        bot_username = (context.bot.username or "").lower()
        bot_id = context.bot.id
        bot_tag = f"@{bot_username}" if bot_username else None

        addressed = _is_bot_addressed(message, entities, bot_username, bot_id)
        if not addressed and bot_tag and bot_tag in text.lower():
            addressed = True
            pattern = re.compile(re.escape(bot_tag), re.IGNORECASE)
            text = pattern.sub(" ", text, count=1)

        if not addressed and not allow_unaddressed_conversion:
            return
        if addressed:
            cleaned = _strip_bot_reference(raw_text, entities, bot_username, bot_id)
            if cleaned == raw_text and bot_tag and bot_tag in cleaned:
                pattern = re.compile(re.escape(bot_tag), re.IGNORECASE)
                cleaned = pattern.sub(" ", cleaned)
            text = " ".join(cleaned.split()).strip()
            if not text:
                return

    logger.info("Chat %s (lang=%s) user -> bot: %s", chat_id, lang, text)
    prompt = f"[LANG={lang}] {text}"

    session_key = _session_id(chat, user)

    try:
        reply = await agent.send(session_key, prompt)
    except AgentClientError as exc:
        logger.warning("Agent error for chat {}: {}", session_key, exc)
        await message.reply_text(html.escape(_msg(lang, "agent_error")), parse_mode=ParseMode.HTML)
        return

    logger.info("Chat %s (lang=%s) bot -> user: %s", session_key, lang, reply)
    await message.reply_text(reply, disable_web_page_preview=True, parse_mode=ParseMode.HTML)



async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled Telegram error: {}", context.error)


async def on_shutdown(application: Application) -> None:
    client: AgentClient | None = application.bot_data.get("agent_client")
    if client:
        await client.close()


def build_application() -> Application:
    agent_client = AgentClient(
        config.agent_base_url,
        processor_id=config.processor_id,
    )

    builder = ApplicationBuilder().token(config.telegram_bot_token)
    builder.post_shutdown(on_shutdown)
    application = builder.build()
    application.bot_data["agent_client"] = agent_client
    application.bot_data[LANGUAGE_PREFS_KEY] = {}

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("lang", lang_command))
    application.add_handler(CommandHandler("project", project_command))
    application.add_handler(CommandHandler("gas", gas_command))
    application.add_handler(CommandHandler("rpc", rpc_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)
    return application


def main() -> None:
    setup_logger()
    logger.info("Starting Skel Helper Bot…")
    application = build_application()
    application.run_polling()


if __name__ == "__main__":
    main()
