import sqlite3
from contextlib import closing
from datetime import datetime, UTC
import os


VALID_STATUSES = {
    "extracted",
    "resolved",
    "no_telegram",
    "approved",
    "added",
    "failed",
    "skipped",
}


class BridgeRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS contacts (
                    id INTEGER PRIMARY KEY,
                    phone_e164 TEXT UNIQUE,
                    display_name TEXT,
                    source_group TEXT NOT NULL,
                    status TEXT NOT NULL,
                    extracted_at TIMESTAMP NOT NULL
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS telegram_resolutions (
                    id INTEGER PRIMARY KEY,
                    contact_id INTEGER NOT NULL REFERENCES contacts(id),
                    telegram_user_id INTEGER,
                    telegram_username TEXT,
                    resolved INTEGER NOT NULL,
                    resolved_at TIMESTAMP NOT NULL
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS add_attempts (
                    id INTEGER PRIMARY KEY,
                    contact_id INTEGER NOT NULL REFERENCES contacts(id),
                    target_group_id TEXT NOT NULL,
                    attempted_at TIMESTAMP NOT NULL,
                    success INTEGER NOT NULL,
                    error_reason TEXT,
                    wait_seconds INTEGER
                )"""
            )
            conn.commit()

    # --- contacts ---

    def upsert_contact(
        self, phone_e164: str | None, display_name: str, source_group: str
    ) -> int:
        now = datetime.now(UTC).isoformat()
        with closing(self._connect()) as conn:
            if phone_e164 is not None:
                row = conn.execute(
                    "SELECT id FROM contacts WHERE phone_e164 = ?", (phone_e164,)
                ).fetchone()
                if row is not None:
                    return row[0]
            cur = conn.execute(
                """INSERT INTO contacts (phone_e164, display_name, source_group, status, extracted_at)
                   VALUES (?, ?, ?, 'extracted', ?)""",
                (phone_e164, display_name, source_group, now),
            )
            conn.commit()
            return cur.lastrowid

    def contact_status(self, contact_id: int) -> str | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT status FROM contacts WHERE id = ?", (contact_id,)
            ).fetchone()
            return row[0] if row is not None else None

    def set_contact_status(self, contact_id: int, status: str) -> None:
        if status not in VALID_STATUSES:
            raise ValueError(f"Status invalido: {status}")
        with closing(self._connect()) as conn:
            conn.execute(
                "UPDATE contacts SET status = ? WHERE id = ?", (status, contact_id)
            )
            conn.commit()

    def contacts_by_status(self, status: str) -> list[sqlite3.Row]:
        with closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute(
                "SELECT * FROM contacts WHERE status = ?", (status,)
            ).fetchall()

    # --- telegram_resolutions ---

    def record_resolution(
        self,
        contact_id: int,
        resolved: bool,
        telegram_user_id: int | None = None,
        telegram_username: str | None = None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with closing(self._connect()) as conn:
            conn.execute(
                """INSERT INTO telegram_resolutions
                   (contact_id, telegram_user_id, telegram_username, resolved, resolved_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (contact_id, telegram_user_id, telegram_username, int(resolved), now),
            )
            conn.commit()
        self.set_contact_status(contact_id, "resolved" if resolved else "no_telegram")

    # --- add_attempts ---

    def total_successful_adds(self) -> int:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM add_attempts WHERE success = 1"
            ).fetchone()
            return row[0]

    def record_add_attempt(
        self,
        contact_id: int,
        target_group_id: str,
        success: bool,
        error_reason: str | None = None,
        wait_seconds: int | None = None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with closing(self._connect()) as conn:
            conn.execute(
                """INSERT INTO add_attempts
                   (contact_id, target_group_id, attempted_at, success, error_reason, wait_seconds)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (contact_id, target_group_id, now, int(success), error_reason, wait_seconds),
            )
            conn.commit()
        self.set_contact_status(contact_id, "added" if success else "failed")

    # --- relatorio ---

    def report_rows(self) -> list[sqlite3.Row]:
        with closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute(
                """SELECT
                       c.phone_e164, c.display_name, c.source_group, c.status,
                       tr.telegram_username, tr.resolved,
                       aa.success AS added, aa.error_reason, aa.attempted_at
                   FROM contacts c
                   LEFT JOIN telegram_resolutions tr ON tr.contact_id = c.id
                   LEFT JOIN add_attempts aa ON aa.contact_id = c.id
                   ORDER BY c.extracted_at"""
            ).fetchall()
