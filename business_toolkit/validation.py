"""Normalize and validate order lines without emitting raw rejected values."""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .ingest import FIELDS

CURRENCIES = {"INR", "USD", "EUR"}
STATUSES = {"PAID", "PENDING", "CANCELLED"}
ISSUES = {
    "CSV_WIDTH": "Column count differs from the header.",
    "RECORD_TYPE": "Expected an object.",
    "EXTRA_FIELDS": "Unexpected fields are present.",
    "ORDER_ID": "Use ORD- followed by 1 to 24 ASCII letters or digits.",
    "ORDER_DATE": "Use a real calendar date in YYYY-MM-DD format.",
    "CURRENCY": "Use INR, USD, or EUR.",
    "STATUS": "Use PAID, PENDING, or CANCELLED.",
    "QUANTITY": "Use a whole number from 1 through 10000.",
    "UNIT_PRICE": "Use 0 through 1000000.00 with at most two decimal places.",
    "DUPLICATE_ID": "An earlier valid record already claimed this order ID.",
    **{f"MISSING_{field.upper()}": f"Supply {field}." for field in FIELDS},
}


@dataclass(frozen=True)
class OrderLine:
    order_id: str
    order_date: str
    currency: str
    status: str
    quantity: int
    unit_price_cents: int

    @property
    def total_cents(self):
        return self.quantity * self.unit_price_cents


def money(cents):
    return f"{cents // 100}.{cents % 100:02d}"


def _enum_token(value):
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isascii():
            return stripped.upper()
    return ""


def _order_id(value):
    token = _enum_token(value)
    return token if re.fullmatch(r"ORD-[A-Z0-9]{1,24}", token) else None


def _currency(value):
    token = _enum_token(value)
    return token if token in CURRENCIES else None


def _status(value):
    token = _enum_token(value)
    return token if token in STATUSES else None


def _order_date(value):
    if isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            pass
    return None


def _quantity(value):
    if isinstance(value, str) and re.fullmatch(r"[0-9]{1,5}", value):
        value = int(value)
    if type(value) is int and 1 <= value <= 10_000:
        return value
    return None


def _price_cents(value):
    if isinstance(value, str) and re.fullmatch(r"[0-9]{1,7}(\.[0-9]{1,2})?", value):
        value = Decimal(value)
    elif type(value) is int:
        value = Decimal(value)
    if isinstance(value, Decimal) and value.as_tuple().exponent >= -2:
        if not value.is_signed() and value <= 1_000_000:
            if value.is_zero():
                return 0
            numerator, denominator = value.as_integer_ratio()
            return numerator * 100 // denominator
    return None


PARSERS = {
    "order_id": _order_id,
    "order_date": _order_date,
    "currency": _currency,
    "status": _status,
    "quantity": _quantity,
    "unit_price": _price_cents,
}


def validate(record):
    if not isinstance(record, dict):
        return None, ["RECORD_TYPE"]
    issues = ["EXTRA_FIELDS"] if record.keys() - PARSERS.keys() else []
    values = []
    for field, parser in PARSERS.items():
        value = record.get(field)
        if isinstance(value, str):
            value = value.strip()
        if value is None or value == "":
            issues.append(f"MISSING_{field.upper()}")
            continue
        normalized = parser(value)
        if normalized is None:
            issues.append(field.upper())
        values.append(normalized)
    if issues:
        return None, issues
    return OrderLine(*values), []
