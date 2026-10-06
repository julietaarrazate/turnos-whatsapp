"""PDF de la propuesta (P-03): el mismo snapshot público que el link, impreso con WeasyPrint.

Solo recibe el `PublicSnapshot` validado (lista blanca), así que no puede imprimir nada que el
link no muestre. Como el snapshot es inmutable, el PDF se cachea por `content_hash`.
"""

from collections import OrderedDict
from datetime import date
from decimal import Decimal
from pathlib import Path
from threading import Lock
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.modules.proposals.public_schemas import PublicSnapshot

_TEMPLATES = Path(__file__).parent / "templates"
_CACHE_SIZE = 32
_cache: OrderedDict[str, bytes] = OrderedDict()
_lock = Lock()


def format_money(value: str | None, currency: str) -> str:
    """'1337050.00' → '$ 1.337.050,00' (igual que el frontend, es-AR)."""
    if value is None:
        return ""
    amount = Decimal(value).quantize(Decimal("0.01"))
    symbol = {"ARS": "$", "USD": "US$"}.get(currency, currency)
    integer, _, cents = f"{abs(amount):.2f}".partition(".")
    grouped = f"{int(integer):,}".replace(",", ".")
    sign = "-" if amount < 0 else ""
    return f"{sign}{symbol} {grouped},{cents}"


def format_day(value: str | None) -> str:
    return date.fromisoformat(value).strftime("%d/%m/%Y") if value else ""


def format_quantity(value: str) -> str:
    """'2.5000' → '2,5'; '3.0000' → '3'."""
    text = f"{Decimal(value).normalize():f}"
    return text.replace(".", ",")


_env = Environment(
    loader=FileSystemLoader(_TEMPLATES),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)
_env.filters["day"] = format_day
_env.filters["qty"] = format_quantity


def render_html(snapshot: PublicSnapshot) -> str:
    def money(value: str | None) -> str:
        return format_money(value, snapshot.currency)

    data: dict[str, Any] = snapshot.model_dump(mode="json")
    return _env.get_template("proposal.html").render(p=data, money=money)


def render_pdf(content_hash: str, snapshot: PublicSnapshot) -> bytes:
    with _lock:
        cached = _cache.get(content_hash)
        if cached is not None:
            _cache.move_to_end(content_hash)
            return cached
    # Import diferido: WeasyPrint necesita Pango (está en la imagen Docker); el resto de la
    # app, el export del OpenAPI y los tests que no generan PDF no lo cargan.
    from weasyprint import HTML  # noqa: PLC0415

    pdf = HTML(string=render_html(snapshot), base_url=str(_TEMPLATES)).write_pdf()
    if not isinstance(pdf, bytes):  # sin `target`, write_pdf siempre devuelve los bytes
        raise TypeError("WeasyPrint no devolvió el PDF")
    with _lock:
        _cache[content_hash] = pdf
        while len(_cache) > _CACHE_SIZE:
            _cache.popitem(last=False)
    return pdf
