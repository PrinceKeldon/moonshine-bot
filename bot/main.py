"""
DexScreener Bot — full pipeline

1. Discover candidate tokens (token profiles + recent pairs)
2. Apply filters + blacklists
3. Fake-volume heuristic → blacklist if suspicious
4. RugCheck → only "Good"; blacklist bundles
5. Classify rug / pump, save everything
6. Optionally trade via Bonkbot (Telegram) + notify
"""
from __future__ import annotations

import asyncio
import signal
import sys
from pathlib import Path

from loguru import logger

from bot.analysis import apply_filters, classify_rug_or_pump, detect_fake_volume
from bot.config import load_blacklist, load_config, save_blacklist
from bot.dexscreener import DexScreenerClient
from bot.rugcheck import RugCheckClient
from bot.storage import Storage
from bot.telegram_trader import TelegramTrader

ROOT = Path(__file__).resolve().parent.parent


async def process_pair(
    pair: dict,
    cfg: dict,
    coin_bl: set[str],
    dev_bl: set[str],
    ds: DexScreenerClient,
    rc: RugCheckClient,
    store: Storage,
    tg: TelegramTrader,
) -> None:
    mint = (pair.get("mint") or "").lower()
    if not mint:
        return

    if mint in coin_bl:
        logger.debug(f"Skip blacklisted coin {mint}")
        return

    filters = cfg.get("filters", {})
    if not apply_filters(pair, filters):
        return

    # Fake volume
    fv_cfg = cfg.get("fake_volume", {})
    if detect_fake_volume(pair, fv_cfg):
        logger.warning(f"Fake volume suspected → blacklist {mint}")
        coin_bl.add(mint)
        save_blacklist(cfg["blacklists"]["coins_file"], coin_bl)
        await store.log_event(mint, "fake_volume", pair)
        await tg.notify_blacklist(mint, "Suspected fake volume")
        return

    # RugCheck
    report = await rc.get_report(mint)
    if not report:
        logger.debug(f"No RugCheck data for {mint}")
        return

    if cfg.get("rugcheck", {}).get("only_good", True) and not rc.is_good(report):
        logger.info(f"RugCheck not Good → skip {mint} ({report.get('riskLevel')})")
        return

    if cfg.get("rugcheck", {}).get("reject_on_bundle", True) and rc.has_bundle_or_high_concentration(report):
        logger.warning(f"Bundle / concentration → blacklist {mint}")
        coin_bl.add(mint)
        save_blacklist(cfg["blacklists"]["coins_file"], coin_bl)
        await store.log_event(mint, "bundle", {"report": report.get("risks")})
        await tg.notify_blacklist(mint, "Bundle or high concentration detected")
        return

    # Classification
    analysis_cfg = cfg.get("analysis", {})
    classification = classify_rug_or_pump(pair, analysis_cfg)
    record = {
        **pair,
        **classification,
        "rugcheck_good": True,
        "rugcheck_score": report.get("score"),
        "risk_level": report.get("riskLevel"),
    }

    await store.upsert_token(mint, record)
    store.append_jsonl(record)

    if classification["is_rug"]:
        logger.warning(f"RUG: {pair.get('symbol')} {mint}")
        await tg.notify_rug(pair, classification["reasons"])
        if cfg["blacklists"].get("auto_add_rugs"):
            coin_bl.add(mint)
            save_blacklist(cfg["blacklists"]["coins_file"], coin_bl)
    elif classification["is_pump"]:
        logger.info(f"PUMP: {pair.get('symbol')} {mint}")
        await tg.notify_pump(pair, classification["reasons"])
    else:
        # Clean new / interesting pair that passed all checks → candidate for trade
        logger.success(f"CLEAN candidate: {pair.get('symbol')} | liq ${pair.get('liquidity_usd'):,.0f}")
        await tg.buy(mint)


async def discovery_cycle(
    cfg: dict,
    ds: DexScreenerClient,
    rc: RugCheckClient,
    store: Storage,
    tg: TelegramTrader,
    coin_bl: set[str],
    dev_bl: set[str],
) -> None:
    logger.info("Starting discovery cycle…")
    profiles = await ds.get_latest_token_profiles()
    logger.info(f"Fetched {len(profiles)} latest token profiles")

    seen: set[str] = set()
    max_pairs = cfg.get("runtime", {}).get("max_pairs_per_cycle", 30)
    count = 0

    for profile in profiles:
        if count >= max_pairs:
            break
        chain = profile.get("chainId")
        if chain and chain != cfg.get("dexscreener", {}).get("chain", "solana"):
            continue
        mint = profile.get("tokenAddress")
        if not mint or mint.lower() in seen:
            continue
        seen.add(mint.lower())

        pairs = await ds.get_token_pairs(mint)
        if not pairs:
            continue
        # Prefer the highest-liquidity Solana pair
        sol_pairs = [p for p in pairs if p.get("chainId") == "solana"]
        if not sol_pairs:
            continue
        best = max(sol_pairs, key=lambda p: (p.get("liquidity") or {}).get("usd") or 0)
        normalized = ds.normalize_pair(best)
        await process_pair(normalized, cfg, coin_bl, dev_bl, ds, rc, store, tg)
        count += 1

    logger.info(f"Cycle finished — processed {count} candidates")


async def main() -> None:
    cfg = load_config(ROOT / "config.yaml")
    log_level = cfg.get("runtime", {}).get("log_level", "INFO")
    logger.remove()
    logger.add(sys.stderr, level=log_level)
    logger.add(ROOT / "logs" / "bot.log", rotation="10 MB", level=log_level)

    coin_bl = load_blacklist(cfg["blacklists"]["coins_file"])
    dev_bl = load_blacklist(cfg["blacklists"]["devs_file"])
    logger.info(f"Loaded blacklists: {len(coin_bl)} coins, {len(dev_bl)} devs")

    ds = DexScreenerClient(
        base_url=cfg["dexscreener"]["base_url"],
        delay=cfg["dexscreener"].get("rate_limit_delay", 0.25),
    )
    rc = RugCheckClient(base_url=cfg["rugcheck"]["base_url"])
    store = Storage(cfg["storage"]["db_file"], cfg["storage"]["analysis_jsonl"])
    await store.init()

    tg = TelegramTrader(cfg.get("telegram", {}), dry_run=cfg.get("runtime", {}).get("dry_run", True))

    stop = asyncio.Event()

    def _signal(*_):
        logger.info("Shutdown signal received")
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            asyncio.get_event_loop().add_signal_handler(sig, _signal)
        except NotImplementedError:
            pass

    interval = cfg["dexscreener"].get("poll_interval_seconds", 60)
    logger.info(f"Bot started (dry_run={cfg.get('runtime', {}).get('dry_run')}). Poll every {interval}s")

    try:
        while not stop.is_set():
            try:
                await discovery_cycle(cfg, ds, rc, store, tg, coin_bl, dev_bl)
            except Exception as e:
                logger.exception(f"Cycle error: {e}")
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass
    finally:
        await ds.close()
        await rc.close()
        logger.info("Bot stopped cleanly")


if __name__ == "__main__":
    asyncio.run(main())
