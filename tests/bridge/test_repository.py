import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from radar.bridge.repository import BridgeRepository


def make_repo(tmp_path) -> BridgeRepository:
    return BridgeRepository(str(tmp_path / "bridge.db"))


def test_upsert_contact_dedupes_by_phone(tmp_path):
    repo = make_repo(tmp_path)
    id1 = repo.upsert_contact("+5511999990000", "Fulano", "Grupo A")
    id2 = repo.upsert_contact("+5511999990000", "Fulano", "Grupo A")
    assert id1 == id2


def test_upsert_contact_without_phone_creates_new_row_each_time(tmp_path):
    repo = make_repo(tmp_path)
    id1 = repo.upsert_contact(None, "Sem Telefone", "Grupo A")
    id2 = repo.upsert_contact(None, "Sem Telefone", "Grupo A")
    assert id1 != id2


def test_new_contact_starts_extracted(tmp_path):
    repo = make_repo(tmp_path)
    contact_id = repo.upsert_contact("+5511999990001", "Fulano", "Grupo A")
    rows = repo.contacts_by_status("extracted")
    assert any(r["id"] == contact_id for r in rows)


def test_record_resolution_updates_status_to_resolved(tmp_path):
    repo = make_repo(tmp_path)
    contact_id = repo.upsert_contact("+5511999990002", "Fulano", "Grupo A")
    repo.record_resolution(contact_id, resolved=True, telegram_user_id=123, telegram_username="fulano")
    rows = repo.contacts_by_status("resolved")
    assert any(r["id"] == contact_id for r in rows)


def test_record_resolution_not_found_sets_no_telegram(tmp_path):
    repo = make_repo(tmp_path)
    contact_id = repo.upsert_contact("+5511999990003", "Fulano", "Grupo A")
    repo.record_resolution(contact_id, resolved=False)
    rows = repo.contacts_by_status("no_telegram")
    assert any(r["id"] == contact_id for r in rows)


def test_contact_status_returns_current_status(tmp_path):
    repo = make_repo(tmp_path)
    contact_id = repo.upsert_contact("+5511999990007", "Fulano", "Grupo A")
    assert repo.contact_status(contact_id) == "extracted"
    repo.record_resolution(contact_id, resolved=True, telegram_user_id=1, telegram_username="fulano")
    assert repo.contact_status(contact_id) == "resolved"


def test_contact_status_unknown_id_returns_none(tmp_path):
    repo = make_repo(tmp_path)
    assert repo.contact_status(999) is None


def test_record_add_attempt_success_updates_status_and_counter(tmp_path):
    repo = make_repo(tmp_path)
    contact_id = repo.upsert_contact("+5511999990004", "Fulano", "Grupo A")
    assert repo.total_successful_adds() == 0
    repo.record_add_attempt(contact_id, "-100123", success=True)
    assert repo.total_successful_adds() == 1
    rows = repo.contacts_by_status("added")
    assert any(r["id"] == contact_id for r in rows)


def test_record_add_attempt_failure_updates_status_and_reason(tmp_path):
    repo = make_repo(tmp_path)
    contact_id = repo.upsert_contact("+5511999990005", "Fulano", "Grupo A")
    repo.record_add_attempt(contact_id, "-100123", success=False, error_reason="PeerFlood")
    assert repo.total_successful_adds() == 0
    rows = repo.contacts_by_status("failed")
    assert any(r["id"] == contact_id for r in rows)


def test_report_rows_joins_all_tables(tmp_path):
    repo = make_repo(tmp_path)
    contact_id = repo.upsert_contact("+5511999990006", "Fulano", "Grupo A")
    repo.record_resolution(contact_id, resolved=True, telegram_user_id=1, telegram_username="fulano")
    repo.record_add_attempt(contact_id, "-100123", success=True)
    rows = repo.report_rows()
    assert len(rows) == 1
    assert rows[0]["telegram_username"] == "fulano"
    assert rows[0]["added"] == 1
