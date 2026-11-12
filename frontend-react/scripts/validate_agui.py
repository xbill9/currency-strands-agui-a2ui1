#!/usr/bin/env python3
"""AG-UI / CopilotKit Integration Validation Tool for Currency Agent.

This tool runs automated checks against the CopilotKit (AG-UI) endpoints to
verify capabilities, stream parsing, A2UI 1.0 tool results, and guardrails.
Supports testing the AG-UI bridge directly (port 8008) or the Next.js app (port 3000).
"""

import argparse
import json
import socket
import sys
from collections.abc import Generator
from typing import Any

import httpx
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


def is_port_open(port: int) -> bool:
    """Check if a port is open on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def parse_sse_stream(response: httpx.Response) -> Generator[dict[str, Any]]:
    """Parse SSE (Server-Sent Events) from a response stream."""
    for line in response.iter_lines():
        if not line.strip():
            continue
        if line.startswith("data:"):
            line = line[5:].strip()
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            # Skip non-JSON framing line
            continue


class AgUiValidator:
    def __init__(self, target: str):
        self.target = target
        if target == "direct":
            self.base_url = "http://localhost:8008"
            self.run_url = self.base_url
            self.capabilities_url = f"{self.base_url}/capabilities"
            self.state_url = f"{self.base_url}/agents/state"
        else:
            self.base_url = "http://localhost:3000/api/copilotkit"
            self.run_url = f"{self.base_url}/agent/currency_agent/run"
            self.capabilities_url = f"{self.base_url}/agent/currency_agent/capabilities"
            self.state_url = "http://localhost:3000/api/copilotkit/agent/currency_agent/state"  # Or equivalent

        self.client = httpx.Client(timeout=25.0)

    def test_health(self) -> bool:
        """Verify the endpoint is reachable."""
        print_header("Test Case 1: Health & Reachability")
        try:
            if self.target == "direct":
                # We hit capabilities as a quick ping
                r = self.client.get(self.capabilities_url)
                if r.status_code == 200:
                    print_success(
                        f"Endpoint reachable at {self.capabilities_url} (HTTP 200)"
                    )
                    return True
                else:
                    print_failure(
                        f"Endpoint returned HTTP {r.status_code} on capabilities request",
                        r.text,
                    )
                    return False
            else:
                # For Next.js, ping the base CopilotKit path
                r = self.client.get(self.base_url)
                # createCopilotEndpoint GET handler returns 200 or 405/404 depending on configuration,
                # we just need to ensure the dev server is active and responding
                if r.status_code in [200, 404, 405]:
                    print_success(
                        f"Next.js server is reachable at {self.base_url} (HTTP {r.status_code})"
                    )
                    return True
                else:
                    print_failure(
                        f"Next.js server returned unexpected status code {r.status_code}",
                        r.text,
                    )
                    return False
        except Exception as e:
            print_failure(f"Could not connect to target '{self.target}'", str(e))
            return False

    def test_capabilities(self) -> bool:
        """Verify endpoint reports capabilities correctly."""
        print_header("Test Case 2: Capabilities Discovery")
        if self.target != "direct":
            print_info(
                "Skipping capabilities GET check for Next.js (queried internally by CopilotKit runtime)"
            )
            return True

        try:
            r = self.client.get(self.capabilities_url)
            if r.status_code != 200:
                print_failure(f"Capabilities check failed: HTTP {r.status_code}")
                return False

            caps = r.json()
            print_success("Capabilities endpoint successfully queried.")
            print(f"  Returned capabilities payload: {json.dumps(caps)}")
            return True
        except Exception as e:
            print_failure("Error during capabilities request", str(e))
            return False

    def test_conversion_flow(self) -> bool:
        """Verify a conversion query calls a tool and returns an A2UI 1.0 surface."""
        print_header("Test Case 3: Streamed Currency Conversion & A2UI Output")
        payload = {
            "runId": f"validation-run-conv-{self.target}",
            "threadId": f"validation-thread-conv-{self.target}",
            "forwardedProps": {},
            "tools": [],
            "context": [],
            "state": {},
            "messages": [
                {
                    "id": f"msg-conv-1-{self.target}",
                    "role": "user",
                    "content": "Convert 100 USD to EUR please.",
                }
            ],
        }

        try:
            print_info("Sending conversion request and reading SSE stream...")
            has_started = False
            tool_called = False
            errors = []
            events = []

            with self.client.stream("POST", self.run_url, json=payload) as r:
                if r.status_code != 200:
                    print_failure(
                        f"Stream POST failed: HTTP {r.status_code}", r.read().decode()
                    )
                    return False

                for event in parse_sse_stream(r):
                    events.append(event)
                    ev_type = event.get("type")

                    if ev_type == "RUN_STARTED":
                        has_started = True
                    elif ev_type == "TOOL_CALL_START":
                        tool_called = True
                        print_info(
                            f"Tool execution started: {event.get('toolCallName')}"
                        )
                    elif ev_type == "RUN_ERROR":
                        errors.append(event.get("message"))

            if errors:
                print_failure(
                    "Agent reported stream execution error(s)", ", ".join(errors)
                )
                return False

            if not has_started:
                print_failure("Stream finished but RUN_STARTED event was missing")
                return False

            if not tool_called:
                print_failure(
                    "Stream completed but get_exchange_rate tool was never executed"
                )
                return False

            print_success("SSE Stream completed with valid flow transitions.")

            # A2UI 1.0 arrives as the send_a2ui_json_to_client tool result.
            try:
                components = check_a2ui_surface(events)
                texts = component_texts(components)
                assert any("USD" in t and "EUR" in t for t in texts), (
                    f"No Text component mentions USD and EUR: {texts}"
                )
            except AssertionError as a2ui_err:
                print_failure("A2UI 1.0 output check failed", str(a2ui_err))
                return False

            print_success(
                f"A2UI 1.0 createSurface received with {len(components)} components."
            )
            print(f"  Text components: {texts}")

            return True
        except Exception as e:
            print_failure("Error during conversion flow test", str(e))
            return False

    def test_guardrails(self) -> bool:
        """Verify the agent rejects unrelated prompts."""
        print_header("Test Case 4: Agent Guardrails & Domain Enforcement")
        payload = {
            "runId": f"validation-run-guard-{self.target}",
            "threadId": f"validation-thread-guard-{self.target}",
            "forwardedProps": {},
            "tools": [],
            "context": [],
            "state": {},
            "messages": [
                {
                    "id": f"msg-guard-1-{self.target}",
                    "role": "user",
                    "content": "Write a quick Python script to reverse a string.",
                }
            ],
        }

        try:
            print_info("Sending off-topic request and reading SSE stream...")
            tool_called = False
            final_text = ""

            with self.client.stream("POST", self.run_url, json=payload) as r:
                if r.status_code != 200:
                    print_failure(
                        f"Stream POST failed: HTTP {r.status_code}", r.read().decode()
                    )
                    return False

                for event in parse_sse_stream(r):
                    ev_type = event.get("type")
                    if ev_type == "TOOL_CALL_START":
                        tool_called = True
                    elif ev_type == "TEXT_MESSAGE_CONTENT":
                        final_text += event.get("delta", "")

            if tool_called:
                print_failure(
                    "Guardrail failed: Agent attempted to run a tool on an off-topic request."
                )
                return False

            # Verify response is polite refusal
            refusal_keywords = [
                "cannot help",
                "only assist",
                "currency",
                "conversion",
                "exchange rate",
                "unable to",
            ]
            matched_keywords = [k for k in refusal_keywords if k in final_text.lower()]

            if matched_keywords:
                print_success(
                    f"Agent correctly refused to answer off-topic prompt (Matched: {matched_keywords})"
                )
                print(f"  Response text: {final_text.strip()}")
                return True
            else:
                print_failure(
                    "Agent response did not clearly state refusal aligned with instructions",
                    f"Response text: {final_text.strip()}",
                )
                return False
        except Exception as e:
            print_failure("Error during guardrail flow test", str(e))
            return False

    def test_thread_state(self) -> bool:
        """Verify thread history can be loaded from /agents/state."""
        if self.target != "direct":
            # State endpoint matches direct port 10000 format, skip if Nextjs target doesn't map it
            print_header("Test Case 5: Thread State Retrieval")
            print_info(
                "Skipping thread state retrieval check for Next.js (not exposed on API route)"
            )
            return True

        print_header("Test Case 5: Thread State Retrieval")
        payload = {
            "threadId": f"validation-thread-conv-{self.target}",
            "appName": "currency_agent",
            "userId": "demo_user",
        }

        try:
            r = self.client.post(self.state_url, json=payload)
            if r.status_code != 200:
                print_failure(
                    f"Thread state retrieval failed: HTTP {r.status_code}", r.text
                )
                return False

            state_data = r.json()
            if not state_data.get("threadExists"):
                print_failure(
                    "Thread lookup reported threadExists = False for a thread we just converted on"
                )
                return False

            messages = state_data.get("messages", [])
            print_success("Thread state successfully loaded (Thread exists: True)")
            print_success(f"  Retrieved {len(messages)} messages from thread history.")
            return True
        except Exception as e:
            print_failure("Error during thread state retrieval test", str(e))
            return False


def main():
    parser = argparse.ArgumentParser(description="AG-UI / CopilotKit Validation Tool")
    parser.add_argument(
        "--target",
        choices=["direct", "nextjs"],
        default=None,
        help="Target server to validate. 'direct' uses the AG-UI bridge (8008), 'nextjs' uses dev server (3000). Autodetect if omitted.",
    )
    args = parser.parse_args()

    # Autodetect if target not specified
    target = args.target
    if not target:
        is_3000_open = is_port_open(3000)
        is_8008_open = is_port_open(8008)

        if is_3000_open and is_8008_open:
            target = "nextjs"
            print_info(
                "Both port 3000 (Next.js) and 8008 (React Agent) are open. Defaulting validation to 'nextjs'."
            )
        elif is_8008_open:
            target = "direct"
            print_info(
                "Port 8008 (React Agent) is open. Selecting validation target 'direct'."
            )
        elif is_3000_open:
            target = "nextjs"
            print_info(
                "Port 3000 (Next.js) is open. Selecting validation target 'nextjs'."
            )
        else:
            print_failure(
                "Neither port 3000 (Next.js) nor port 8008 (React Agent) are open.",
                "Ensure you run 'make start' and 'make frontend-react' before validating.",
            )
            sys.exit(1)

    print(f"\n{BOLD}==================================================")
    print(f"🚀 Running AG-UI CopilotKit Validator on target: {target.upper()}")
    print(f"=================================================={RESET}")

    validator = AgUiValidator(target)

    tests = [
        validator.test_health,
        validator.test_capabilities,
        validator.test_conversion_flow,
        validator.test_guardrails,
        validator.test_thread_state,
    ]

    all_passed = True
    for test in tests:
        if not test():
            all_passed = False

    print(f"\n{BOLD}==================================================")
    if all_passed:
        print(
            f"{GREEN}🎉 ALL INTEGRATION VALIDATION CHECKS PASSED SUCCESSFULLY!{RESET}"
        )
        sys.exit(0)
    else:
        print(f"{RED}❌ SOME INTEGRATION VALIDATION CHECKS FAILED.{RESET}")
        sys.exit(1)


if __name__ == "__main__":
    main()
