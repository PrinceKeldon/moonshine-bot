"""Token analysis: filters, fake-volume heuristic, rug/pump detection."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def apply_filters(pair: dict, filters: dict) -> bool:
    """Return True if the pair passes basic filters."""
    if pair.get("liquidity_usd", 0) < filters.get("min_liquidity_usd", 0):
        return False
    if pair.get("volume_24h", 0) < filters.get("min_volume_24h_usd", 0):
        return False
    mc = pair.get("market_cap") or pair.get("fdv") or 0
    if mc < filters.get("min_market_cap_usd", 0):
        return False
    max_mc = filters.get("max_market_cap_usd")
    if max_mc and mc > max_mc:
        return False

    # Age check
    created = pair.get("pair_created_at")
    if created and filters.get("max_age_minutes"):
        try:
            # DexScreener uses ms timestamps
            ts = created / 1000 if created > 1e12 else created
            age_min = (datetime.now(timezone.utc).timestamp() - ts) / 60
            if age_min > filters["max_age_minutes"]:
                return False
        except Exception:
            pass
    return True


def detect_fake_volume(pair: dict, cfg: dict) -> bool:
    """
    Approximate Pocket-Universe-style fake volume detection.
    Real Pocket Universe is a wallet-security product; there is no public
    volume-authenticity API. We use common on-chain heuristics that
    correlate with wash trading / bot volume.
    """
    if not cfg.get("enabled", True):
        return False

    vol = pair.get("volume_24h") or pair.get("volume_1h") or 0
    if vol < cfg.get("min_volume_usd_for_check", 50000):
        return False

    buys = pair.get("txns_h1_buys") or pair.get("txns_m5_buys") or 0
    sells = pair.get("txns_h1_sells") or pair.get("txns_m5_sells") or 0
    total_tx = buys + sells
    if total_tx == 0:
        return False

    # Extreme imbalance
    ratio = max(buys, sells) / total_tx
    if ratio >= cfg.get("extreme_buy_sell_ratio", 0.95):
        return True

    # Very high volume relative to number of trades (large repeated sizes)
    # Simple proxy: if volume is huge but tx count is tiny
    if total_tx < 20 and vol > 200_000:
        return True

    return False


def classify_rug_or_pump(pair: dict, analysis_cfg: dict) -> dict[str, Any]:
    """Return classification flags + reasons."""
    change_1h = pair.get("price_change_1h") or 0
    liq = pair.get("liquidity_usd") or 0
    vol = pair.get("volume_24h") or 0

    is_rug = False
    is_pump = False
    reasons = []

    rug_thresh = analysis_cfg.get("rug_price_drop_1h_pct", -40)
    if change_1h <= rug_thresh and liq < 30_000:
        is_rug = True
        reasons.append(f"1h change {change_1h:.1f}% + low liquidity")

    pump_thresh = analysis_cfg.get("pump_price_rise_1h_pct", 80)
    if change_1h >= pump_thresh and vol > 20_000:
        is_pump = True
        reasons.append(f"1h change +{change_1h:.1f}% with volume")

    return {
        "is_rug": is_rug,
        "is_pump": is_pump,
        "reasons": reasons,
        "price_change_1h": change_1h,
        "liquidity_usd": liq,
        "volume_24h": vol,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
