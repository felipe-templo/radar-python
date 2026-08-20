from decimal import Decimal

from radar.models import Product

SOURCE_LABELS = {
    "ml": ("\U0001F6D2", "Mercado Livre"),
    "shopee": ("\U0001F6CD", "Shopee"),
    "amazon": ("\U0001F4E6", "Amazon"),
}


def format_brl(value: Decimal) -> str:
    s = f"{value:,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def build_message(product: Product) -> str:
    emoji, label = SOURCE_LABELS.get(product.source, ("", ""))
    header_text = f"OFERTA {label}".strip()
    lines = [
        f"\U0001F525 <b>{header_text}</b> {emoji}".strip(),
        "",
        f"\U0001F4E6 <b>{product.name}</b>",
        "",
    ]
    if product.original_price:
        lines.append(f"De: <s>{format_brl(product.original_price)}</s>")
    lines.append(f"\U0001F4B0 <b>Por: {format_brl(product.discount_price)}</b>")
    lines.append(f"\U0001F3F7️ <b>{product.discount_percent}% OFF</b>")
    lines.append("")
    lines.append(f'\U0001F517 <a href="{product.affiliate_link}">Aproveitar oferta</a>')
    return "\n".join(lines)
