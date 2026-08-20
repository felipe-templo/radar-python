import re
from decimal import Decimal, InvalidOperation


def parse_price(raw: str) -> Decimal | None:
    """Converte 'R$ 1.234,56' -> Decimal('1234.56'). Retorna None se nao parsear."""
    if not raw:
        return None
    cleaned = re.sub(r"[^\d,.]", "", raw)
    cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def parse_discount(raw: str) -> int | None:
    """Extrai percentual de desconto de texto tipo '-23% OFF'."""
    if not raw:
        return None
    match = re.search(r"(\d+)\s*%", raw)
    return int(match.group(1)) if match else None


def compute_discount_percent(original_price: Decimal | None, discount_price: Decimal) -> int | None:
    if not original_price or original_price <= 0:
        return None
    return round((1 - discount_price / original_price) * 100)


def extract_product_id(url: str) -> str:
    match = re.search(r"(MLB-?\d+)", url, re.IGNORECASE)
    if not match:
        raise ValueError(f"Nao foi possivel extrair ID do produto de: {url}")
    return match.group(1).replace("-", "").upper()


def extract_shopee_item_id(url: str) -> str:
    """Extrai o item_id de uma URL de produto Shopee (padrao .../nome-i.{shopid}.{itemid})."""
    match = re.search(r"-i\.\d+\.(\d+)", url)
    if not match:
        raise ValueError(f"Nao foi possivel extrair item_id do produto Shopee de: {url}")
    return match.group(1)


def extract_amazon_asin(url: str) -> str:
    """Extrai o ASIN de uma URL de produto Amazon (padrao /dp/{ASIN} ou /gp/product/{ASIN})."""
    match = re.search(r"/(?:dp|gp/product)/([A-Za-z0-9]{10})", url)
    if not match:
        raise ValueError(f"Nao foi possivel extrair ASIN do produto Amazon de: {url}")
    return match.group(1).upper()
