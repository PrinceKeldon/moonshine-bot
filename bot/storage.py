"""Persist analysis results and blacklists."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiosqlite
from loguru import logger


class Storage:
    def __init__(self, db_path: str | Path, jsonl_path: str | Path):
        self.db_path = Path(db_path)
        self.jsonl_path = Path(jsonl_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)

    async def init(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS tokens (
                    mint TEXT PRIMARY KEY,
                    symbol TEXT,
                    name TEXT,
                    pair_address TEXT,
                    first_seen TEXT,
                    last_seen TEXT,
                    is_rug INTEGER DEFAULT 0,
                    is_pump INTEGER DEFAULT 0,
                    is_blacklisted INTEGER DEFAULT 0,
                    rugcheck_good INTEGER,
                    notes TEXT,
                    data_json TEXT
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mint TEXT,
                    event_type TEXT,
                    details TEXT,
                    created_at TEXT
                )
                """
            )
            await db.commit()
        logger.info(f"Storage ready → {self.db_path}")

    async def upsert_token(self, mint: str, data: dict[str, Any]) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO tokens (mint, symbol, name, pair_address, first_seen, last_seen,
                                   is_rug, is_pump, rugcheck_good, notes, data_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(mint) DO UPDATE SET
                    last_seen=excluded.last_seen,
                    is_rug=excluded.is_rug,
                    is_pump=excluded.is_pump,
                    rugcheck_good=excluded.rugcheck_good,
                    notes=excluded.notes,
                    data_json=excluded.data_json
                """,
                (
                    mint,
                    data.get("symbol"),
                    data.get("name"),
                    data.get("pair_address"),
                    data.get("timestamp"),
                    data.get("timestamp"),
                    1 if data.get("is_rug") else 0,
                    1 if data.get("is_pump") else 0,
                    1 if data.get("rugcheck_good") else 0,
                    json.dumps(data.get("reasons") or []),
                    json.dumps(data, default=str),
                ),
            )
            await db.commit()

    async def log_event(self, mint: str, event_type: str, details: dict) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO events (mint, event_type, details, created_at) VALUES (?, ?, ?, datetime('now'))",
                (mint, event_type, json.dumps(details, default=str)),
            )
            await db.commit()

    def append_jsonl(self, record: dict) -> None:
        with open(self.jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
