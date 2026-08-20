import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from radar.models import RawOfferCard

MAX_ATTEMPTS = 5


@dataclass
class QueuedOffer:
    id: int
    site_key: str
    product_id: str
    product_url: str
    name: str
    image_url: str | None
    original_price: Decimal | None
    discount_price: Decimal
    discount_percent: int
    attempts: int


class OfferQueue:
    """Fila persistente (SQLite) de ofertas descobertas, pendentes de resolver
    link de afiliado e postar.

    Separa "descobrir ofertas" (list_offers, rapido) de "resolver afiliado +
    postar" (lento, 1 navegacao por produto). next_batch() intercala sites
    round-robin (1 item de cada site por vez) - assim, se o processamento de
    um item de um site falhar, o proximo item do lote ja e de outro site,
    sem esperar o site que falhou terminar ou tentar de novo antes de dar
    chance aos demais.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, timeout=10)

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS offer_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site_key TEXT NOT NULL,
                    product_id TEXT NOT NULL,
                    product_url TEXT NOT NULL,
                    name TEXT NOT NULL,
                    image_url TEXT,
                    original_price TEXT,
                    discount_price TEXT NOT NULL,
                    discount_percent INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    enqueued_at TIMESTAMP NOT NULL,
                    UNIQUE(site_key, product_id)
                )"""
            )
            conn.commit()

    def enqueue(self, site_key: str, product_id: str, raw: RawOfferCard) -> None:
        """Adiciona um item pendente. Silenciosamente ignorado se ja
        estiver na fila (pending/failed/done) - INSERT OR IGNORE via
        UNIQUE(site_key, product_id)."""
        with closing(self._connect()) as conn:
            conn.execute(
                """INSERT OR IGNORE INTO offer_queue
                (site_key, product_id, product_url, name, image_url, original_price,
                 discount_price, discount_percent, status, attempts, enqueued_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?)""",
                (
                    site_key,
                    product_id,
                    raw.product_url,
                    raw.name,
                    raw.image_url,
                    str(raw.original_price) if raw.original_price is not None else None,
                    str(raw.discount_price),
                    raw.discount_percent or 0,
                    datetime.now().isoformat(),
                ),
            )
            conn.commit()

    def next_batch(self, limit: int) -> list[QueuedOffer]:
        """Proximos N itens pendentes, intercalados round-robin entre sites
        (1 item de cada site por vez, na ordem em que foram enfileirados)."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """SELECT id, site_key, product_id, product_url, name, image_url,
                          original_price, discount_price, discount_percent, attempts
                   FROM (
                       SELECT *, ROW_NUMBER() OVER (
                           PARTITION BY site_key ORDER BY enqueued_at
                       ) AS rn
                       FROM offer_queue WHERE status = 'pending'
                   )
                   ORDER BY rn, site_key
                   LIMIT ?""",
                (limit,),
            ).fetchall()
        return [
            QueuedOffer(
                id=row[0],
                site_key=row[1],
                product_id=row[2],
                product_url=row[3],
                name=row[4],
                image_url=row[5],
                original_price=Decimal(row[6]) if row[6] is not None else None,
                discount_price=Decimal(row[7]),
                discount_percent=row[8],
                attempts=row[9],
            )
            for row in rows
        ]

    def mark_done(self, item_id: int) -> None:
        with closing(self._connect()) as conn:
            conn.execute("UPDATE offer_queue SET status = 'done' WHERE id = ?", (item_id,))
            conn.commit()

    def mark_failed(self, item_id: int, error: str) -> None:
        """Volta pra 'pending' (tenta de novo em ciclos futuros) ate
        MAX_ATTEMPTS; depois disso marca 'failed' (terminal, sai da fila
        de pendentes) pra nao ficar tentando pra sempre um item quebrado."""
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT attempts FROM offer_queue WHERE id = ?", (item_id,)).fetchone()
            attempts = (row[0] if row else 0) + 1
            status = "pending" if attempts < MAX_ATTEMPTS else "failed"
            conn.execute(
                "UPDATE offer_queue SET status = ?, attempts = ?, last_error = ? WHERE id = ?",
                (status, attempts, error, item_id),
            )
            conn.commit()
