"""DexScreener API client."""
from __future__ import annotations

import asyncio
from typing import Any

import aiohttp
from loguru import logger


class DexScreenerClient:
    def __init__(self, base_url: str = "https://api.dexscreener.com", delay: float = 0.25):
        self.base_url = base_url.rstrip("/")
        self.delay = delay
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=20),
                headers={"Accept": "application/json", "User-Agent": "DexScreenerBot/1.0"},
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _get(self, path: str, params: dict | None = None) -> Any:
        session = await self._get_session()
        url = f"{self.base_url}{path}"
        for attempt in range(3):
            try:
                async with session.get(url, params=params) as resp:
                    if resp.status == 429:
                        wait = 2 ** attempt
                        logger.warning(f"Rate limited, sleeping {wait}s")
                        await asyncio.sleep(wait)
                        continue
                    resp.raise_for_status()
                    data = await resp.json()
                    await asyncio.sleep(self.delay)
                    return data
            except Exception as e:
                logger.error(f"DexScreener GET {path} failed (attempt {attempt+1}): {e}")
                await asyncio.sleep(1)
        return None

    async def get_latest_token_profiles(self) -> list[dict]:
        """Recent token profiles (good proxy for newly promoted / listed tokens)."""
        data = await self._get("/token-profiles/latest/v1")
        if isinstance(data, list):
            return data
        return []

    async def get_token_pairs(self, token_address: str) -> list[dict]:
        """All pairs for a token mint."""
        data = await self._get(f"/latest/dex/tokens/{token_address}")
        if not data:
            return []
        return data.get("pairs") or []

    async def search(self, query: str) -> list[dict]:
        data = await self._get("/latest/dex/search", params={"q": query})
        if not data:
            return []
        return data.get("pairs") or []

    async def get_pair(self, chain_id: str, pair_address: str) -> dict | None:
        data = await self._get(f"/latest/dex/pairs/{chain_id}/{pair_address}")
        if not data:
            return None
        pairs = data.get("pairs") or []
        return pairs[0] if pairs else None

    @staticmethod
    def normalize_pair(pair: dict) -> dict:
        """Flatten useful fields for analysis."""
        base = pair.get("baseToken") or {}
        quote = pair.get("quoteToken") or {}
        liq = pair.get("liquidity") or {}
        vol = pair.get("volume") or {}
        price_change = pair.get("priceChange") or {}
        txns = pair.get("txns") or {}

        return {
            "chain_id": pair.get("chainId"),
            "dex_id": pair.get("dexId"),
            "pair_address": pair.get("pairAddress"),
            "url": pair.get("url"),
            "mint": base.get("address"),
            "symbol": base.get("symbol"),
            "name": base.get("name"),
            "quote_symbol": quote.get("symbol"),
            "price_usd": float(pair.get("priceUsd") or 0),
            "liquidity_usd": float(liq.get("usd") or 0),
            "volume_24h": float(vol.get("h24") or 0),
            "volume_1h": float(vol.get("h1") or 0),
            "volume_5m": float(vol.get("m5") or 0),
            "price_change_1h": float(price_change.get("h1") or 0),
            "price_change_24h": float(price_change.get("h24") or 0),
            "price_change_5m": float(price_change.get("m5") or 0),
            "fdv": float(pair.get("fdv") or 0),
            "market_cap": float(pair.get("marketCap") or 0),
            "pair_created_at": pair.get("pairCreatedAt"),
            "txns_m5_buys": (txns.get("m5") or {}).get("buys", 0),
            "txns_m5_sells": (txns.get("m5") or {}).get("sells", 0),
            "txns_h1_buys": (txns.get("h1") or {}).get("buys", 0),
            "txns_h1_sells": (txns.get("h1") or {}).get("sells", 0),
            "raw": pair,
        }
