# DexScreener Analysis & Trading Bot

Professional-grade Solana memecoin scanner that:

1. Discovers new / promoted tokens via DexScreener token profiles
2. Applies configurable liquidity / volume / age / market-cap filters
3. Detects suspected **fake volume** (heuristic approximating wash-trading patterns)
4. Checks every token on **RugCheck.xyz** — only proceeds with `riskLevel == "Good"`
5. Detects **bundles / high concentration** and auto-blacklists them
6. Classifies **rugs** and **pumps**, persists everything to SQLite + JSONL
7. Sends Telegram notifications and (optionally) buy commands for **Bonkbot** / similar TG trading bots
8. Maintains persistent **coin blacklist** and **dev blacklist**

## Quick start

```bash
cd moonshine-bot
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Edit config
# Fill telegram.bot_token, telegram.chat_id
# Set runtime.dry_run: false when you are ready to send real buys

python -m bot.main
```

## Configuration (`config.yaml`)

| Section | Purpose |
|---------|--------|
| `dexscreener` | Base URL, poll interval, rate-limit delay |
| `rugcheck` | Only-Good filter, bundle rejection |
| `fake_volume` | Heuristic thresholds (no public Pocket Universe volume API exists) |
| `filters` | Min liquidity / volume, max age, market-cap bounds |
| `blacklists` | Paths + auto-add rules |
| `analysis` | Rug / pump price-change thresholds |
| `telegram` | Bot token, chat ID, buy command template, notification toggles |
| `runtime` | `dry_run` (recommended true at first), max pairs per cycle |

### Telegram + Bonkbot

1. Create a bot with @BotFather → copy the token into `telegram.bot_token`
2. Start a chat with your bot (or add it to a group) and get the `chat_id`
3. In the same chat (or a group where both bots are present) you can also talk to @bonkbot_bot
4. The default `buy_command_template: "{mint}"` simply pastes the contract address — Bonkbot usually auto-detects it and offers buy buttons.
5. Change the template if you prefer explicit commands, e.g. `"/buy {mint} 0.1"`

**Always keep `runtime.dry_run: true` until you have verified notifications and blacklisting.**

## Data outputs

- `data/tokens.db` — SQLite (tokens + events)
- `data/analysis.jsonl` — one JSON object per analysed token
- `data/coin_blacklist.json` / `data/dev_blacklist.json` — persistent blacklists
- `logs/bot.log` — rotating log

## Important notes

- DexScreener has **no official “new pairs” firehose**. This bot uses the latest token-profiles feed + pair enrichment, which is the practical public approach. For true on-chain sniping you would add a Helius / Yellowstone gRPC listener.
- “Pocket Universe API for fake volume” is not a public endpoint. The bot implements transparent heuristics that catch common wash-trading signatures. You can tighten/loosen them in config.
- RugCheck free tier has rate limits; the client already backs off on 429.
- Trading is **at your own risk**. This software is for research and automation assistance only.

## Project layout

```
moonshine-bot/
├── bot/
│   ├── main.py              # orchestrator
│   ├── dexscreener.py       # API client
│   ├── rugcheck.py          # safety checks
│   ├── analysis.py          # filters + classification
│   ├── storage.py           # SQLite + JSONL
│   ├── telegram_trader.py   # notifications + buy commands
│   └── config.py
├── data/                    # blacklists, db, jsonl
├── logs/
├── config.yaml
├── requirements.txt
└── README.md
```

## Extending

- Add a real on-chain new-pair listener (Helius webhooks / Geyser)
- Enrich with Birdeye / Bubblemaps holder data
- Implement sell logic / trailing stops via Bonkbot limit-order commands
- Multi-chain support (change `dexscreener.chain` and filters)

---

Built as a complete, production-oriented single codebase matching the original requirements.
