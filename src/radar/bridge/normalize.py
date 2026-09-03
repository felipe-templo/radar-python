from dataclasses import dataclass

import phonenumbers


@dataclass
class RawContact:
    display_name: str
    phone_raw: str | None
    source_group: str


@dataclass
class NormalizedContact:
    display_name: str
    phone_e164: str | None
    source_group: str


def normalize_phone(raw: str | None, default_region: str = "BR") -> str | None:
    if not raw:
        return None
    try:
        parsed = phonenumbers.parse(raw, default_region)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def normalize_contact(raw: RawContact, default_region: str = "BR") -> NormalizedContact:
    return NormalizedContact(
        display_name=raw.display_name,
        phone_e164=normalize_phone(raw.phone_raw, default_region),
        source_group=raw.source_group,
    )


def dedupe_contacts(raw_contacts: list[RawContact], default_region: str = "BR") -> list[NormalizedContact]:
    """Normaliza e remove duplicatas por telefone E.164.

    Contatos sem telefone (nome nao resolveu numero) nao podem ser deduplicados
    com seguranca e sao sempre mantidos.
    """
    seen_phones: set[str] = set()
    result: list[NormalizedContact] = []
    for raw in raw_contacts:
        normalized = normalize_contact(raw, default_region)
        if normalized.phone_e164 is not None:
            if normalized.phone_e164 in seen_phones:
                continue
            seen_phones.add(normalized.phone_e164)
        result.append(normalized)
    return result
