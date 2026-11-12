#!/usr/bin/env python3
"""React UI (port 3000) and React Agent (port 8008) End-to-End Test.

This script checks health and connectivity for both servers, sends a message
to the Currency Agent via the Next.js CopilotKit API route, and validates
the streamed SSE response.
"""

import json
import socket
import sys
import time

import httpx
import pytest
from a2ui_check import check_a2ui_surface, component_texts

# Terminal colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_header(title: str):
    print(f"\n{BOLD}{CYAN}=== {title} ===={RESET}")


def print_success(message: str):
    print(f"{GREEN}✓ {message}{RESET}")


def print_failure(message: str, details: str = ""):
    print(f"{RED}✗ {message}{RESET}")
    if details:
        print(f"  {RED}Details: {details}{RESET}")


def print_info(message: str):
    print(f"{YELLOW}i {message}{RESET}")


def wait_for_port(port: int, timeout: float = 15.0) -> bool:
    """Wait for a port to open on localhost."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.5)
    return False


def test_servers_health():
    """Verify that both ports are open and responding to HTTP requests."""
    print_header("Test Case 1: Checking Servers Health")

    # Check port 8008 (Agent)
    if not wait_for_port(8008, 5.0):
        print_failure("React Agent (port 8008) is not running.")
        pytest.skip("React Agent (port 8008) is not running.")

    try:
        r = httpx.get("http://localhost:8008/health", timeout=5.0)
        assert r.status_code == 200, (
            f"React Agent returned unexpected response: {r.status_code}"
        )
        assert r.json().get("status") == "ok", (
            f"React Agent returned unexpected status: {r.json()}"
        )
        print_success("React Agent on port 8008 is healthy.")
    except Exception as e:
        print_failure("Failed to connect to React Agent on port 8008", str(e))
        raise

    # Check port 3000 (UI)
    if not wait_for_port(3000, 5.0):
        print_failure("React UI Server (port 3000) is not running.")
        pytest.skip("React UI Server (port 3000) is not running.")

    try:
        # Next.js API route is compiled faster and is more lightweight to check than full React HTML bundle
        r = httpx.get("http://localhost:3000/api/copilotkit", timeout=15.0)
        assert r.status_code in [200, 304, 404, 405], (
            f"React UI Server returned unexpected HTTP status {r.status_code}"
        )
        print_success("React UI Server on port 3000 is healthy and reachable.")
    except Exception as e:
        print_failure("Failed to connect to React UI Server on port 3000", str(e))
        raise


def test_copilot_endpoint_flow():
    """Send a query to the Currency Agent via the Next.js API endpoint and parse SSE."""
    print_header("Test Case 2: Streaming Query to Currency Agent via Next.js")

    if not wait_for_port(3000, 2.0):
        pytest.skip("Next.js server not running")

    copilot_url = "http://localhost:3000/api/copilotkit/agent/currency_agent/run"

    # Send a prompt related to currency conversion so the Currency Agent will trigger get_exchange_rate
    payload = {
        "runId": "e2e-test-run-currency",
        "threadId": "e2e-test-thread-currency",
        "tools": [],
        "context": [],
        "state": {},
        "messages": [
            {
                "id": "msg-currency-1",
                "role": "user",
                "content": "Convert 100 USD to EUR please.",
            }
        ],
    }

    headers = {"Content-Type": "application/json"}

    try:
        print_info(f"Sending POST request to Next.js API route: {copilot_url}")

        has_started = False
        tool_called = False
        errors = []
        events = []

        client = httpx.Client(timeout=30.0)
        with client.stream("POST", copilot_url, json=payload, headers=headers) as r:
            assert r.status_code == 200, f"Stream POST failed: HTTP {r.status_code}"

            print_success("Connected to SSE stream. Parsing events...")
            for line in r.iter_lines():
                if not line.strip():
                    continue

                if line.startswith("data:"):
                    line = line[5:].strip()

                try:
                    event = json.loads(line)
                    events.append(event)
                    ev_type = event.get("type")

                    if ev_type == "RUN_STARTED":
                        has_started = True
                        print_info("Event: RUN_STARTED")
                    elif ev_type == "TOOL_CALL_START":
                        tool_called = True
                        print_info(
                            f"Event: TOOL_CALL_START -> {event.get('toolCallName')}"
                        )
                    elif ev_type == "RUN_ERROR":
                        errors.append(event.get("message"))
                        print_failure(f"Event: RUN_ERROR -> {event.get('message')}")
                except json.JSONDecodeError:
                    continue

        assert not errors, (
            f"Agent reported stream execution error(s): {', '.join(errors)}"
        )
        assert has_started, "Stream completed but RUN_STARTED event was missing"
        print_success("SSE Stream completed successfully.")

        assert tool_called, (
            "Stream completed but get_exchange_rate tool was never executed"
        )
        print_success("The agent successfully invoked a tool during execution.")

        # A2UI 1.0 arrives as the send_a2ui_json_to_client tool result.
        components = check_a2ui_surface(events)
        texts = component_texts(components)
        assert any("USD" in t and "EUR" in t for t in texts), (
            f"No Text component mentions USD and EUR: {texts}"
        )
        print_info(f"A2UI text components: {texts}")
        print_success(
            f"Agent streamed an A2UI 1.0 surface with {len(components)} components."
        )

    except Exception as e:
        print_failure("Error occurred during end-to-end streaming test", str(e))
        raise


def main():
    print(f"\n{BOLD}==================================================")
    print("🚀 Running React UI & Agent End-to-End Test")
    print(f"=================================================={RESET}")

    try:
        test_servers_health()
    except (pytest.skip.Exception, Exception) as e:
        if isinstance(e, pytest.skip.Exception):
            print(f"\n{BOLD}{YELLOW}i Test Skipped: {e}{RESET}")
            sys.exit(0)
        print(f"\n{BOLD}{RED}❌ Servers health check failed: {e}{RESET}")
        sys.exit(1)

    try:
        test_copilot_endpoint_flow()
    except (pytest.skip.Exception, Exception) as e:
        if isinstance(e, pytest.skip.Exception):
            print(f"\n{BOLD}{YELLOW}i Test Skipped: {e}{RESET}")
            sys.exit(0)
        print(f"\n{BOLD}{RED}❌ End-to-end streaming flow check failed: {e}{RESET}")
        sys.exit(1)

    print(f"\n{BOLD}==================================================")
    print(f"{GREEN}🎉 ALL REACT E2E TEST CHECKS PASSED SUCCESSFULLY!{RESET}")
    sys.exit(0)


if __name__ == "__main__":
    main()
