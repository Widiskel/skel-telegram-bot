# Skel Helper Bot

Skel Helper Bot is a Telegram assistant that proxies user conversations to the Skel Crypto Agent over HTTP. The agent service lives alongside this project in `../skel-crypto-agent` and must be running for the bot to respond. You can invite the bot to groups or use it in private chats.

## Structure

```
skel-telegram-bot/
├── main.py
├── requirements.txt
├── src/
│   └── skel_telegram_bot/
│       ├── agent_client.py
│       ├── bot.py
│       ├── config/
│       │   └── settings.py
│       └── utils/
│           └── logger.py
└── logs/
    └── bot.log (created at runtime)
```

## Requirements

- Python 3.12+
- Telegram bot token (`TELEGRAM_BOT_TOKEN`)
- Running Skel Crypto Agent endpoint (default `http://127.0.0.1:8000`).

## Quick start

```bash
./setup.sh
cp .env.example .env
# populate TELEGRAM_BOT_TOKEN and AGENT_BASE_URL (use your agent URL)
./start.sh
```

### Optional: link the agent as a Git submodule

When hosting `skel-telegram-bot` as an independent repo, add the agent project as a submodule so you can pin its version:

```bash
git submodule add <agent-repo-url> submodules/skel-crypto-agent
```

After cloning, run `git submodule update --init --recursive` to sync the agent source used for deployment manifests and local testing.

### Available commands

- `/start` — Reset the session, show capabilities, and present an invite-to-group button.
- `/help` — Display a localized cheat sheet of commands and features.
- `/reset` — Clear the agent-side history for the current chat/user.
- `/lang EN|ID` — Switch the bot language (admins only in groups).
- `/project <query>` — Ask the agent for a rich project snapshot.
- `/gas [network] [currency]` — Fetch live gas fees (defaults to Ethereum/USD).
- `/rpc [network]` — List Chainlist RPC endpoints for a given network (default: ETH).

### Capabilities

- General crypto chat routed through Skel Crypto Agent.
- Instant price conversions, e.g. `1 BTC`, `1 BTC IDR`, `1 BTC to USD`.
- Deep project intelligence combining CryptoRank and Tavily data via `/project`.
- Live gas-fee quoting for Ethereum, Base, BNB Chain, Linea, and Polygon with optional fiat conversions via `/gas`.
- Automatic Tavily-backed web search when the agent deems it helpful.

All traffic and errors are logged to `logs/bot.log` (rotating file) in addition to stderr output.

> **Vercel note:** `vercel.json` targets `main-vercel.py`, which exposes `/webhook` and `/health`. Deploy with `WEBHOOK_URL` pointing to your public HTTPS endpoint and configure Telegram to POST updates there. If you prefer long polling (`application.run_polling()`), run `main.py` on persistent infrastructure instead of Vercel serverless.
