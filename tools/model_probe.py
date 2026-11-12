"""Ask each model one prompt through the agent and report what it did.

usage: python3 tools/model_probe.py MODEL_ID [MODEL_ID ...]
"""

import json
import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "app" / "agent"))

PROMPTS = [
    "How much is 250 USD in EUR?",
    "Show me the USD to JPY trend over the last 90 days",
    "Compare 1 USD in EUR, GBP, JPY and CAD",
    "What's the weather in Paris?",
]


def tool_results(messages):
    calls, results = {}, []
    for m in messages:
        for c in m["content"]:
            if "toolUse" in c:
                calls[c["toolUse"]["toolUseId"]] = c["toolUse"]["name"]
            if "toolResult" in c:
                tr = c["toolResult"]
                text = "".join(x.get("text", "") for x in tr["content"])
                results.append((calls.get(tr["toolUseId"]), text))
    return results


for model_id in sys.argv[1:]:
    os.environ["BEDROCK_MODEL_ID"] = model_id
    from currency_agent import agent as mod

    for prompt in PROMPTS:
        a = mod.build_agent([mod.mcp_client()])
        t = time.time()
        try:
            out = a(prompt)
            text = str(out).strip()
        except Exception as e:  # noqa: BLE001 - report any model failure
            print(f"{model_id} | {prompt} | ERROR {type(e).__name__}: {str(e)[:150]}")
            continue
        res = tool_results(a.messages)
        ui = sum(
            1
            for n, r in res
            if n == mod.TOOL_NAME and mod.VALIDATED_KEY in json.loads(r)
        )
        bad = sum(
            1 for n, r in res if n == mod.TOOL_NAME and mod.ERROR_KEY in json.loads(r)
        )
        other = [n for n, _ in res if n != mod.TOOL_NAME]
        raw = "<a2ui" in text
        print(
            f"{model_id} | {prompt} | ui={ui} rejected={bad} other_tools={other} "
            f"raw_a2ui_text={raw} {time.time() - t:.1f}s | {text[:80]!r}"
        )
