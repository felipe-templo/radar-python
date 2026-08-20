import sqlite3
from contextlib import closing
import os

from radar.models import Product


class DedupRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, timeout=10)

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS posted_products (
                    product_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    url TEXT NOT NULL,
                    discount_percent INTEGER,
                    posted_at TIMESTAMP NOT NULL,
                    telegram_message_id INTEGER
                )"""
            )
            conn.commit()

    def is_posted(self, product_id: str) -> bool:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT 1 FROM posted_products WHERE product_id = ?", (product_id,)
            ).fetchone()
            return row is not None

    def mark_posted(self, product: Product, dedup_key: str, telegram_message_id: int | None) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO posted_products VALUES (?, ?, ?, ?, ?, ?)",
                (
                    dedup_key,
                    product.name,
                    product.product_url,
                    product.discount_percent,
                    product.collected_at.isoformat(),
                    telegram_message_id,
                ),
            )
            conn.commit()
