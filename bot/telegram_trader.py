"""Telegram notifications + Bonkbot trading commands."""
from __future__ import annotations

from typing import Any

from loguru import logger

try:
    from telegram import Bot
    from telegram.constants import ParseMode
except ImportError:
    Bot = None  # type: ignore


class TelegramTrader:
    def __init__(self, cfg: dict[str, Any], dry_run: bool = True):
        self.cfg = cfg
        self.dry_run = dry_run
        self.enabled = cfg.get("enabled", False) and bool(cfg.get("bot_token"))
        self.bot: Any = None
        if self.enabled and Bot is not None:
            self.bot = Bot(token=cfg["bot_token"])
        elif self.enabled:
            logger.warning("python-telegram-bot not installed — Telegram disabled")

    async def send(self, text: str) -> None:
        if not self.enabled or not self.bot:
            logger.info(f"[TG dry] {text}")
            return
        try:
            await self.bot.send_message(
                chat_id=self.cfg["chat_id"],
                text=text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")

    async def notify(self, title: str, body: str) -> None:
        await self.send(f"<b>{title}</b>\n{body}")

    async def buy(self, mint: str, sol_amount: float | None = None) -> None:
        """Send buy instruction that Bonkbot (or similar) can act on."""
        amount = sol_amount or self.cfg.get("default_buy_sol", 0.05)
        template = self.cfg.get("buy_command_template", "{mint}")
        cmd = template.format(mint=mint, amount=amount)

        if self.dry_run:
            logger.info(f"[DRY-RUN] Would send buy: {cmd}")
            if self.cfg.get("notify_on_buy"):
                await self.notify("DRY-RUN BUY", f"Would buy {amount} SOL of <code>{mint}</code>\nCommand: <code>{cmd}</code>")
            return

        await self.send(cmd)
        if self.cfg.get("notify_on_buy"):
            await self.notify("BUY SENT", f"Bought ~{amount} SOL of <code>{mint}</code>")

    async def notify_rug(self, pair: dict, reasons: list[str]) -> None:
        if not self.cfg.get("notify_on_rug"):
            return
        await self.notify(
            "RUG SIGNAL",
            f"<b>{pair.get('symbol')}</b> (<code>{pair.get('mint')}</code>)\n"
            f"1h: {pair.get('price_change_1h')}% | Liq: ${pair.get('liquidity_usd'):,.0f}\n"
            f"Reasons: {', '.join(reasons)}",
        )

    async def notify_pump(self, pair: dict, reasons: list[str]) -> None:
        if not self.cfg.get("notify_on_pump"):
            return
        await self.notify(
            "PUMP SIGNAL",
            f"<b>{pair.get('symbol')}</b> (<code>{pair.get('mint')}</code>)\n"
            f"1h: +{pair.get('price_change_1h')}% | Vol: ${pair.get('volume_24h'):,.0f}\n"
            f"Reasons: {', '.join(reasons)}",
        )

    async def notify_blacklist(self, mint: str, reason: str) -> None:
        if not self.cfg.get("notify_on_blacklist"):
            return
        await self.notify("BLACKLISTED", f"<code>{mint}</code>\nReason: {reason}")
