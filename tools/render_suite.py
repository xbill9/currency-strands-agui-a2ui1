"""Run the demo prompts N times each through Next.js and count clean renders.

usage: python3 render_suite.py RUNS MODEL_LABEL OUT.jsonl

A UI prompt passes when the reply rendered A2UI and no raw "<a2ui" text reached
the chat. A text prompt passes when it rendered no A2UI and no raw block. A
"ui or text" prompt passes when it showed either, with no raw block.
"""

import collections
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from demo_probe import run

UI = "ui"
TEXT = "text"
ANY = "ui or text"
PROMPTS = [
    (UI, "How much is 250 USD in EUR?"),
    (UI, "What's a thousand euros in dollars?"),
    (UI, "Show me the USD to JPY trend over the last 90 days"),
    (UI, "Show me EUR to USD for the past 6 months and the current rate"),
    (UI, "Compare the euro, pound and Swiss franc against the dollar in a bar chart"),
    (UI, "Show a bar chart of 1 USD in EUR, GBP, JPY, CHF and CAD"),
    (UI, "Compare 1 USD in EUR, GBP, JPY and CAD"),
    (
        UI,
        (
            "Write the A2UI block for a USD to EUR rate card directly in your reply"
            " text. Do not call any tool."
        ),
    ),
    (TEXT, "What's the weather in Paris?"),
    (ANY, "Convert 100 USD to XYZ"),
]


def verdict(kind: str, result: dict) -> str:
    rendered = bool(result.get("ui"))
    raw = "<a2ui" in result.get("text", "")
    if result.get("errors") and not rendered and kind == UI:
        return "fail: " + "; ".join(e[:80] for e in result["errors"])
    if raw:
        return "fail: raw <a2ui> text in the chat"
    if kind == UI:
        return "pass" if rendered else "fail: no UI"
    if kind == ANY:
        shown = rendered or bool(result.get("text", "").strip())
        return "pass" if shown else "fail: nothing shown"
    return "pass" if not rendered else "fail: unexpected UI"


def wait_ready(timeout: float = 120) -> None:
    """Send a warm-up question until one renders; not counted."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if run("How much is 1 USD in EUR?").get("ui"):
            return
        time.sleep(2)
    raise SystemExit("stack not answering")


if __name__ == "__main__":
    runs, label, out = int(sys.argv[1]), sys.argv[2], sys.argv[3]
    wait_ready()
    tally = collections.Counter()
    with open(out, "w") as fh:
        for kind, prompt in PROMPTS:
            for _ in range(runs):
                result = run(prompt)
                v = verdict(kind, result)
                comps = sorted(
                    {c for u in result.get("ui", []) for c in u["components"]}
                )
                fh.write(
                    json.dumps(
                        {"model": label, "verdict": v, "components": comps, **result}
                    )
                    + "\n"
                )
                fh.flush()
                tally[(prompt, v)] += 1
    total = sum(tally.values())
    passed = sum(n for (_, v), n in tally.items() if v == "pass")
    print(
        f"# {label}: {passed} of {total} replies rendered clean ({runs} runs per prompt)"
    )
    for (prompt, v), n in sorted(tally.items()):
        print(f"{n} of {runs}: {v} | {prompt}")
