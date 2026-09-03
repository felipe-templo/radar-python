import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from radar.bridge.normalize import RawContact, dedupe_contacts, normalize_phone


def test_normalize_phone_local_br_format():
    assert normalize_phone("(11) 99999-0000") == "+5511999990000"


def test_normalize_phone_already_e164():
    assert normalize_phone("+5511999990000") == "+5511999990000"


def test_normalize_phone_invalid_returns_none():
    assert normalize_phone("123") is None


def test_normalize_phone_none_returns_none():
    assert normalize_phone(None) is None


def test_normalize_phone_empty_string_returns_none():
    assert normalize_phone("") is None


def test_dedupe_contacts_collapses_same_phone_different_format():
    raw = [
        RawContact("Fulano", "(11) 99999-0000", "Grupo A"),
        RawContact("Fulano B", "+5511999990000", "Grupo A"),
    ]
    result = dedupe_contacts(raw)
    assert len(result) == 1
    assert result[0].phone_e164 == "+5511999990000"


def test_dedupe_contacts_keeps_all_without_phone():
    raw = [
        RawContact("Sem Numero 1", None, "Grupo A"),
        RawContact("Sem Numero 2", None, "Grupo A"),
    ]
    result = dedupe_contacts(raw)
    assert len(result) == 2


def test_dedupe_contacts_keeps_different_phones():
    raw = [
        RawContact("Fulano", "+5511999990000", "Grupo A"),
        RawContact("Beltrano", "+5511999990001", "Grupo A"),
    ]
    result = dedupe_contacts(raw)
    assert len(result) == 2
