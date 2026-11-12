"""Every macro through the agent's own compile, expand and validate path.

The Frankfurter API is replaced with fixed data, so these run offline.
"""

import pytest
from currency_agent import agent, macros

LATEST = {"date": "2026-11-11", "rates": {"EUR": 0.9, "GBP": 0.75, "JPY": 159.0}}
HISTORY = {
    "start_date": "2026-10-12",
    "end_date": "2026-11-11",
    "rates": {
        "2026-10-12": {"EUR": 0.85, "GBP": 0.80, "JPY": 150.0},
        "2026-11-11": {"EUR": 0.90, "GBP": 0.75, "JPY": 159.0},
    },
}


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def fake_get(path, **params):
        wanted = params["to"].split(",")
        data = LATEST if path == "latest" else HISTORY
        pick = {c: v for c, v in data["rates"].items() if c in wanted}
        if path == "latest":
            return {**data, "rates": pick}
        return {
            **data,
            "rates": {
                d: {c: v for c, v in r.items() if c in wanted}
                for d, r in data["rates"].items()
            },
        }

    monkeypatch.setattr(macros, "_get", fake_get)


def send(expr: str) -> list[dict]:
    """What the browser receives for a model call of the UI tool."""
    return agent.compile_a2ui(f"<a2ui>\nroot = {expr}\n</a2ui>")


def components(messages: list[dict]) -> list[dict]:
    assert len(messages) == 1 and messages[0]["version"] == "1.0"
    return messages[0]["createSurface"]["components"]


def texts(comps: list[dict]) -> list[str]:
    return [c["text"] for c in comps if c["component"] == "Text"]


def test_rate_card():
    comps = components(
        send(
            'RateCard("USD", "EUR", 250, catalogId="https://a2ui.org/catalogs/macros")'
        )
    )
    assert "### 250.00 USD = 225.00 EUR" in texts(comps)


def test_rate_history_chart():
    comps = components(
        send(
            'RateHistoryChart("USD", "JPY", 30, catalogId="https://a2ui.org/catalogs/macros")'
        )
    )
    chart = next(c for c in comps if c["component"] == "LineChart")
    assert chart["values"] == [150.0, 159.0]


def test_rate_comparison():
    expr = 'RateComparison("USD", ["EUR", "GBP", "JPY"], catalogId="https://a2ui.org/catalogs/macros")'
    comps = components(send(expr))
    chart = next(c for c in comps if c["component"] == "BarChart")
    assert chart["labels"] == ["EUR", "GBP", "JPY"]
    assert chart["values"] == [5.88, -6.25, 6.0]
    assert chart["decimals"] == 2
    assert "1 USD = 0.90000 EUR" in texts(comps)
    assert chart["catalogId"] == macros.CHARTS_CATALOG_ID


MACRO_CATALOG = 'catalogId="https://a2ui.org/catalogs/macros"'


@pytest.mark.parametrize(
    "expr",
    [
        f'RateCard("USD", "XYZ1", {MACRO_CATALOG})',
        f'RateComparison("USD", ["EUR"], {MACRO_CATALOG})',
        f'RateComparison("USD", ["USD", "EUR"], {MACRO_CATALOG})',
    ],
)
def test_bad_arguments_are_rejected(expr):
    with pytest.raises(Exception, match="currency|compare"):
        send(expr)


class _Agent:
    def __init__(self):
        self.cancelled = None

    def cancel(self, *, after_current_tools=False):
        self.cancelled = after_current_tools


def _call(payload):
    import json
    from types import SimpleNamespace

    a = _Agent()
    out = agent.send_a2ui_json_to_client(
        a2ui_payload=payload, tool_context=SimpleNamespace(agent=a)
    )
    return json.loads(out), a.cancelled


def test_tool_sends_the_wire_messages_and_ends_the_turn():
    out, cancelled = _call(
        f'<a2ui>\nroot = RateCard("USD", "EUR", 100, {MACRO_CATALOG})\n</a2ui>'
    )
    assert out[agent.VALIDATED_KEY][0]["version"] == "1.0"
    assert cancelled is True


def test_tool_reports_errors_to_the_model_and_keeps_the_turn():
    out, cancelled = _call("root = Nope()")
    assert agent.ERROR_KEY in out
    assert cancelled is None
