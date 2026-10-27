"""RugCheck.xyz client."""
from __future__ import annotations

import asyncio
from typing import Any

import aiohttp
from loguru import logger


class RugCheckClient:
    def __init__(self, base_url: str = "https://api.rugcheck.xyz"):
        self.base_url = base_url.rstrip("/")
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=25),
                headers={"Accept": "application/json"},
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_report(self, mint: str) -> dict[str, Any] | None:
        session = await self._get_session()
        url = f"{self.base_url}/v1/tokens/{mint}/report"
        for attempt in range(3):
            try:
                async with session.get(url) as resp:
                    if resp.status == 404:
                        return None
                    if resp.status == 429:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    if resp.status >= 400:
                        logger.warning(f"RugCheck {resp.status} for {mint}")
                        return None
                    return await resp.json()
            except Exception as e:
                logger.error(f"RugCheck error for {mint}: {e}")
                await asyncio.sleep(1)
        return None

    async def get_summary(self, mint: str) -> dict[str, Any] | None:
        session = await self._get_session()
        url = f"{self.base_url}/v1/tokens/{mint}/report/summary"
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None
                return await resp.json()
        except Exception as e:
            logger.error(f"RugCheck summary error: {e}")
            return None

    @staticmethod
    def is_good(report: dict) -> bool:
        level = (report.get("riskLevel") or report.get("score") or "").lower()
        if isinstance(level, str):
            return level == "good"
        # Some responses use numeric score; treat high score as good if present
        score = report.get("score")
        if isinstance(score, (int, float)) and score >= 100:
            return True
        return False

    @staticmethod
    def has_bundle_or_high_concentration(report: dict) -> bool:
        """Detect bundle / insider concentration from risks + top holders."""
        risks = report.get("risks") or []
        for r in risks:
            name = (r.get("name") or "").lower()
            level = (r.get("level") or "").lower()
            if any(k in name for k in ("bundle", "insider", "concentration", "top holders", "creator")):
                if level in ("danger", "warn", "warning", "critical"):
                    return True

        # Top holders percentage heuristic
        top = report.get("topHolders") or []
        if top:
            # Sum first few holders
            pct = 0.0
            for h in top[:5]:
                pct += float(h.get("pct") or h.get("percentage") or 0)
            if pct > 40:  # >40% in top 5 is suspicious for most memecoins
                return True

        # LP locked / freeze / mint authority signals are already in risks usually
        return False
