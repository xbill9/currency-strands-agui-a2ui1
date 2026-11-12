import json
import sys

import httpx

COPILOT_ENDPOINT = "http://localhost:3000/api/copilotkit/agent/currency_agent/run"


def test_copilot_endpoint():
    import socket

    import pytest

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        if s.connect_ex(("localhost", 3000)) != 0:
            pytest.skip("Next.js dev server is not running on port 3000")

    print(f"--- 🪁 Testing CopilotKit (AG-UI) API Endpoint: {COPILOT_ENDPOINT} ---")

    # Standard CopilotKit request payload structure
    payload = {
        "runId": "test-run-id",
        "tools": [],
        "context": [],
        "threadId": "test-thread-id",
        "messages": [
            {
                "id": "test-msg-1",
                "role": "user",
                "content": "What is the exchange rate for USD to EUR today?",
            }
        ],
    }

    headers = {"Content-Type": "application/json"}

    try:
        # Send POST request to Next.js API router
        print("Sending message request...")
        with httpx.stream(
            "POST", COPILOT_ENDPOINT, json=payload, headers=headers, timeout=20.0
        ) as r:
            if r.status_code != 200:
                print(f"❌ Connection failed: Server returned HTTP {r.status_code}")
                # Try reading body for error details
                try:
                    error_text = r.read().decode("utf-8")
                    print(f"Details: {error_text}")
                except Exception:
                    pass
                sys.exit(1)

            print("✅ Connected! Reading response stream:\n")
            for line in r.iter_lines():
                if not line.strip():
                    continue

                # Check for SSE data
                if line.startswith("data:"):
                    line = line[5:].strip()

                try:
                    data = json.loads(line)
                    # Stream and print readable parts (agent content, tool calls)
                    if "choices" in data:
                        for choice in data["choices"]:
                            delta = choice.get("delta", {})
                            if delta.get("content"):
                                print(delta["content"], end="", flush=True)
                            elif "tool_calls" in delta:
                                print(
                                    f"\n[Tool Called: {delta['tool_calls']}]",
                                    flush=True,
                                )
                    else:
                        # Log any other events
                        print(f"\n[Event: {data}]", flush=True)
                except json.JSONDecodeError:
                    # Print raw stream chunk if not JSON
                    print(line)

            print("\n\n--- Stream Completed Successfully ---")

    except httpx.ConnectError:
        print("❌ Error: Next.js dev server is not running on http://localhost:3000.")
        print("Please run 'make frontend-react' in another terminal and try again.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    test_copilot_endpoint()
