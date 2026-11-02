from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Explicit MVP allowlist; unsupported currencies are rejected, never guessed.
CURRENCIES = {"INR": 2, "IDR": 2, "MYR": 2, "USD": 2, "EUR": 2, "GBP": 2, "JPY": 0}
FIELDS = ("merchant", "date", "total", "currency", "tax")
CATEGORIES = ("uncategorized", "food", "groceries", "travel", "transport", "shopping", "health", "utilities", "other")


class LineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(default="", max_length=300)
    quantity: str | None = Field(default=None, max_length=32)
    unit_price: str | None = Field(default=None, max_length=32)
    line_total: str | None = Field(default=None, max_length=32)

    @field_validator("name", "quantity", "unit_price", "line_total", mode="before")
    @classmethod
    def clean(cls, value, info):
        if value is None and info.field_name != 'name':
            return None
        if not isinstance(value, str):
            raise ValueError('Use strings for item fields')
        value = ' '.join(value.split())
        return value if info.field_name == 'name' else value or None


class Draft(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    merchant: str | None = Field(default=None, max_length=200)
    date: str | None = Field(default=None, max_length=32)
    total: str | None = Field(default=None, max_length=32)
    currency: str | None = Field(default=None, max_length=3)
    tax: str | None = Field(default=None, max_length=32)
    category: Literal["uncategorized", "food", "groceries", "travel", "transport", "shopping", "health", "utilities", "other"] = "uncategorized"
    items: list[LineItem] = Field(default_factory=list, max_length=200)
    notes: str = Field(default="", max_length=1000)

    @field_validator("merchant", "date", "total", "currency", "tax", mode="before")
    @classmethod
    def clean(cls, value):
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("Use strings for extracted fields")
        return " ".join(value.split()) or None


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    fields: Draft
    confirm_warnings: bool = False


class RevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)


def minor_units(value: str, currency: str) -> int:
    if not re.fullmatch(r"\d+(?:\.\d+)?", value):
        raise ValueError("Use a plain nonnegative decimal amount without symbols or exponents")
    try:
        amount = Decimal(value)
        scaled = amount * (10 ** CURRENCIES[currency])
        if not amount.is_finite() or amount < 0 or scaled != scaled.to_integral_value():
            raise ValueError("Amount must be nonnegative with valid currency precision")
        if scaled > 10**12:
            raise ValueError("Amount exceeds the supported range")
        return int(scaled)
    except (InvalidOperation, KeyError) as exc:
        raise ValueError("Invalid amount or unsupported currency") from exc


def approved_values(fields: Draft, confirm_warnings: bool = False) -> dict:
    if not fields.merchant or not fields.date or not fields.total or not fields.currency:
        raise ValueError("Merchant, date, total, and currency are required for approval")
    currency = fields.currency.upper()
    if currency not in CURRENCIES:
        raise ValueError("Choose a supported currency")
    parsed_date = date.fromisoformat(fields.date)
    if parsed_date.isoformat() != fields.date:
        raise ValueError("Date must use YYYY-MM-DD")
    total = minor_units(fields.total, currency)
    tax = minor_units(fields.tax, currency) if fields.tax is not None else None
    if tax is not None and tax > total and not confirm_warnings:
        raise ValueError("Tax exceeds total; confirm this warning before approval")
    items = []
    for index, item in enumerate(fields.items, start=1):
        if not item.name:
            raise ValueError(f'Item {index} needs a name; remove empty rows')
        quantity = None
        if item.quantity is not None:
            if not re.fullmatch(r'\d+(?:\.\d{1,6})?', item.quantity) or not 0 < Decimal(item.quantity) <= 10**6:
                raise ValueError(f'Item {index} quantity must be positive, with at most six decimal places')
            quantity = Decimal(item.quantity)
        unit = minor_units(item.unit_price, currency) if item.unit_price is not None else None
        line = minor_units(item.line_total, currency) if item.line_total is not None else None
        if quantity is not None and unit is not None and line is not None:
            calculated = int((quantity * unit).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
            if abs(calculated - line) > 1 and not confirm_warnings:
                raise ValueError(f'Item {index}: quantity × unit price differs from line total; confirm the discount/adjustment before approval')
        items.append({'name': item.name, 'quantity': format(quantity, 'f') if quantity is not None else None,
                      'unitPriceMinor': unit, 'lineTotalMinor': line})
    result = {
        "merchant": fields.merchant, "merchantSearch": fields.merchant.casefold(),
        "expenseDate": parsed_date.isoformat(), "totalMinor": total, "taxMinor": tax,
        "currency": currency, "currencyExponent": CURRENCIES[currency],
        "category": fields.category, "notes": fields.notes,
    }
    # Preserve idempotent approval of legacy receipts that have no items key.
    if items:
        result['items'] = items
    return result
