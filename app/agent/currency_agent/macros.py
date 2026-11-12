"""A2UI 1.0 server-side macros for the currency agent.

The model writes one call, such as ``RateCard("USD", "EUR", 250)``. The
``MacroExpander`` runs these functions on the server, where they fetch the
rates themselves, and sends the expanded Basic and chart catalog components to
the renderer. The rate figures never pass through the model's context.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
from typing import Literal

import httpx
from a2ui.builder.v1_0 import Card, Column, ComponentBuilderNode, Divider, Text
from a2ui.core import Catalog
from a2ui.transformers.macros import macro

FRANKFURTER_URL = os.getenv("FRANKFURTER_URL", "https://api.frankfurter.dev/v1")
_CURRENCY = re.compile(r"^[A-Z]{3}$")

CHARTS_CATALOG_PATH = os.path.join(os.path.dirname(__file__), "custom_catalog.json")
with open(CHARTS_CATALOG_PATH) as f:
    CHARTS_CATALOG = Catalog.from_json(json.load(f))
CHARTS_CATALOG_ID = CHARTS_CATALOG.catalog_id


class LineChart(ComponentBuilderNode):
    """Builder for the custom ``LineChart`` component (custom_catalog.json)."""

    component: Literal["LineChart"] = "LineChart"
    title: str | None = None
    labels: list[str]
    values: list[float]
    color: str | None = None


class BarChart(ComponentBuilderNode):
    """Builder for the custom ``BarChart`` component (custom_catalog.json)."""

    component: Literal["BarChart"] = "BarChart"
    title: str | None = None
    labels: list[str]
    values: list[float]
    color: str | None = None
    decimals: int | None = None


def _code(value: str) -> str:
    """Model output is untrusted: accept only a three-letter ISO code."""
    code = value.strip().upper()
    if not _CURRENCY.match(code):
        raise ValueError(f"not an ISO 4217 currency code: {value!r}")
    return code


def _get(path: str, **params: str) -> dict:
    response = httpx.get(f"{FRANKFURTER_URL}/{path}", params=params, timeout=10)
    response.raise_for_status()
    return response.json()


@macro
def RateCard(currency_from: str, currency_to: str, amount: float = 1.0) -> Card:
    """Card with the live exchange rate and a converted amount. The server looks
    up the rate, so do not pass rate figures.

    Args:
        currency_from: ISO 4217 code to convert from, such as "USD".
        currency_to: ISO 4217 code to convert to, such as "EUR".
        amount: Amount of currency_from to convert. Defaults to 1.
    """
    src, dst = _code(currency_from), _code(currency_to)
    data = _get("latest", **{"from": src, "to": dst})
    rate = data["rates"][dst]
    return Card(
        child=Column(
            children=[
                Text(text=f"### {amount:,.2f} {src} = {amount * rate:,.2f} {dst}"),
                Text(text=f"1 {src} = {rate:.5f} {dst}"),
                Divider(),
                Text(
                    text=f"ECB reference rate for {data['date']} (Frankfurter API)",
                    variant="caption",
                ),
            ]
        )
    )


@macro
def RateHistoryChart(currency_from: str, currency_to: str, days: int = 30) -> Card:
    """Card with a line chart of the exchange rate history. The server fetches
    the history, so do not pass dates or rate values.

    Args:
        currency_from: ISO 4217 code of the base currency, such as "USD".
        currency_to: ISO 4217 code of the quote currency, such as "EUR".
        days: Number of calendar days of history, from 7 to 365. Defaults to 30.
    """
    src, dst = _code(currency_from), _code(currency_to)
    days = max(7, min(int(days), 365))
    start = (dt.datetime.now(dt.UTC).date() - dt.timedelta(days=days)).isoformat()
    data = _get(f"{start}..", **{"from": src, "to": dst})
    series = sorted(data["rates"].items())
    labels = [day[5:] for day, _ in series]  # MM-DD
    values = [rates[dst] for _, rates in series]
    lo, hi = min(values), max(values)
    return Card(
        child=Column(
            children=[
                Text(text=f"### {src} → {dst}, last {days} days"),
                LineChart(
                    title=f"{src}/{dst} ({data['start_date']} to {data['end_date']})",
                    labels=labels,
                    values=values,
                ),
                Text(
                    text=f"Low {lo:.5f} · High {hi:.5f} · Latest {values[-1]:.5f}",
                    variant="caption",
                ),
            ]
        )
    )


@macro
def RateComparison(currency_from: str, currencies: list[str], days: int = 30) -> Card:
    """Card comparing several currencies against one base currency: today's rate
    for each, and a bar chart of how much each rate moved over the period, in
    percent. The server looks up every rate, so do not pass rate figures.

    Args:
        currency_from: ISO 4217 code of the base currency, such as "USD".
        currencies: Two to ten ISO 4217 codes to compare, such as ["EUR", "GBP"].
        days: Number of calendar days for the change, from 7 to 365. Defaults to 30.
    """
    src = _code(currency_from)
    codes: list[str] = []
    for value in currencies:
        code = _code(value)
        if code != src and code not in codes:
            codes.append(code)
    if not 2 <= len(codes) <= 10:
        raise ValueError(f"compare 2 to 10 currencies other than {src}, got {codes}")
    days = max(7, min(int(days), 365))
    to = ",".join(codes)
    latest = _get("latest", **{"from": src, "to": to})
    start = (dt.datetime.now(dt.UTC).date() - dt.timedelta(days=days)).isoformat()
    history = _get(f"{start}..", **{"from": src, "to": to})
    series = sorted(history["rates"].items())
    first, last = series[0][1], series[-1][1]
    change = [round((last[c] / first[c] - 1) * 100, 2) for c in codes]
    rows = [Text(text=f"1 {src} = {latest['rates'][c]:.5f} {c}") for c in codes]
    return Card(
        child=Column(
            children=[
                Text(text=f"### 1 {src} against {len(codes)} currencies"),
                *rows,
                BarChart(
                    title=(
                        f"Change in the {src} rate, {history['start_date']}"
                        f" to {history['end_date']} (%)"
                    ),
                    labels=codes,
                    values=change,
                    decimals=2,
                ),
                Text(
                    text=f"ECB reference rates for {latest['date']} (Frankfurter API)",
                    variant="caption",
                ),
            ]
        )
    )


MACROS = [RateCard, RateHistoryChart, RateComparison]
