"""Lightweight zero-dependency HTTP server providing REST API for the Agentic Frontend.

Exposes REST endpoints to trigger agent comparison sessions, retrieve step-by-step
trajectories, query and manage SQLite3 memories, and run evaluation scenarios.
"""

from __future__ import annotations

import json
import mimetypes
import os
import sys
import time
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Dict, List

# Ensure local imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import AgentConfig
from harness import ProductionAgentHarness
from memory import AgentMemory
from main import get_client, MockOpenAIClient


class AgentApiHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler dispatching static assets and agent REST endpoints."""

    memory = AgentMemory(db_path="agent_memory.db")
    config = AgentConfig(model="gemini-2.5-flash", max_iterations=5, token_budget=4000, max_retries=3, base_backoff=0.2)
    harness = ProductionAgentHarness(config=config, memory=memory)
    client = get_client()

    def _reset_client(self) -> None:
        """Reset internal step counters across any client implementation."""
        if hasattr(self.client, "reset"):
            self.client.reset()
        elif hasattr(self.client, "step_counter"):
            self.client.step_counter = 0
        if hasattr(self.client, "chat") and hasattr(self.client.chat, "completions"):
            comps = self.client.chat.completions
            if hasattr(comps, "step_counter"):
                comps.step_counter = 0

    def _send_json(self, status_code: int, data: Dict[str, Any]) -> None:
        """Send a JSON HTTP response."""
        response_bytes = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(response_bytes)

    def do_OPTIONS(self) -> None:
        """Handle CORS pre-flight requests."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        """Handle GET requests for static UI assets and memory data."""
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path == "/api/memories":
            query_params = urllib.parse.parse_qs(parsed_url.query)
            session_id = query_params.get("session_id", ["session_finance_dept"])[0]
            memories = self.memory.recall_relevant_context(
                session_id=session_id,
                query="all preferences rules context",
                top_k=20,
                client=self.client,
                similarity_threshold=0.0,
            )
            all_sessions = self.memory.list_all_sessions()
            self._send_json(200, {"session_id": session_id, "memories": memories, "sessions": all_sessions})
            return

        if path == "/api/config":
            self._send_json(200, {
                "model": self.config.model,
                "max_iterations": self.config.max_iterations,
                "token_budget": self.config.token_budget,
                "max_retries": self.config.max_retries,
                "is_mock": isinstance(self.client, MockOpenAIClient),
            })
            return

        # Serve static files from ./static directory
        if path == "/" or path == "":
            path = "/index.html"

        static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
        file_path = os.path.abspath(os.path.join(static_dir, path.lstrip("/")))

        if not file_path.startswith(static_dir) or not os.path.isfile(file_path):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")
            return

        content_type, _ = mimetypes.guess_type(file_path)
        content_type = content_type or "application/octet-stream"

        try:
            with open(file_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception as exc:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(exc).encode("utf-8"))

    def do_POST(self) -> None:
        """Handle POST requests for text comparison, scenarios, and memory operations."""
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            payload = json.loads(body)
        except Exception:
            payload = {}

        if path == "/api/compare":
            text_a = payload.get("text_a", "").strip()
            text_b = payload.get("text_b", "").strip()
            session_id = payload.get("session_id", "web_session").strip() or "web_session"
            rule_to_save = payload.get("save_rule", "").strip()

            if not text_a or not text_b:
                self._send_json(400, {"error": "Both text_a and text_b are required."})
                return

            self._reset_client()

            start_time = time.perf_counter()
            report = self.harness.run_monitored_session(
                session_id=session_id,
                text_a=text_a,
                text_b=text_b,
                client=self.client,
            )
            elapsed_sec = time.perf_counter() - start_time

            if rule_to_save:
                self.memory.save_information(
                    session_id=session_id,
                    key="preference_rules",
                    value=rule_to_save,
                    client=self.client,
                )

            report["latency_sec"] = round(elapsed_sec, 3)
            self._send_json(200, report)
            return

        if path == "/api/memory/save" or path == "/api/save_memory":
            session_id = payload.get("session_id", "web_session")
            key = payload.get("key", "preference")
            value = payload.get("value", "")
            if not value:
                self._send_json(400, {"error": "Value cannot be empty."})
                return
            self.memory.save_information(session_id, key, value, client=self.client)
            self._send_json(200, {"status": "saved", "session_id": session_id, "key": key})
            return

        if path == "/api/memory/clear":
            session_id = payload.get("session_id", "web_session")
            self.memory.clear_session(session_id)
            self._send_json(200, {"status": "cleared", "session_id": session_id})
            return

        if path == "/api/scenario":
            scenario_id = int(payload.get("scenario_id", 1))
            if scenario_id == 1:
                # Scenario 1: Cold start Multi-iteration
                text_a = "Projected Financials Q3:\n- Marketing Budget: $120,000\n- Engineering Team: 45 engineers\n- Cloud Hosting: $35,000/mo\nTone: Friendly and informal."
                text_b = "Projected Financials Q3:\n- Marketing Budget: $150,000\n- Engineering Team: 52 engineers\n- Cloud Hosting: $42,000/mo\nTone: Formal and assertive."
                session_id = "session_finance_dept"
                self._reset_client()

                report = self.harness.run_monitored_session(session_id, text_a, text_b, self.client)
                self.memory.save_information(
                    session_id=session_id,
                    key="preference_rules",
                    value="Focus strictly on numerical budget and financial changes. Explicitly suppress and ignore all minor stylistic, wording, and tone discrepancies.",
                    client=self.client,
                )
                self._send_json(200, report)
                return

            elif scenario_id == 2:
                # Scenario 2: Memory Recall Active
                text_c = "Performance Benchmarks Release 2.4:\n- Server Latency: 120ms\n- Throughput: 5,000 rps\n- Error Rate: 0.04%\nStylistic note: Our awesome team made incredible progress!"
                text_d = "Performance Benchmarks Release 2.4:\n- Server Latency: 85ms\n- Throughput: 7,500 rps\n- Error Rate: 0.01%\nStylistic note: The updated infrastructure delivers robust stability."
                session_id = "session_finance_dept"
                self._reset_client()

                report = self.harness.run_monitored_session(session_id, text_c, text_d, self.client)
                self._send_json(200, report)
                return

            elif scenario_id == 3:
                # Scenario 3: Simulated Outage & Recovery
                fail_count = [0]
                def flaky():
                    fail_count[0] += 1
                    if fail_count[0] <= 2:
                        raise ConnectionError(f"HTTP 503 Service Unavailable (Attempt #{fail_count[0]})")
                    return {"status": "recovered", "message": "API recovered successfully on attempt 3"}

                harness_res = self.harness.execute_with_retry(flaky)
                self.harness._recent_actions.clear()
                loop_check = [
                    self.harness.detect_infinite_loop("tool:compute_text_diff"),
                    self.harness.detect_infinite_loop("tool:compute_text_diff"),
                    self.harness.detect_infinite_loop("tool:compute_text_diff"),
                ]
                self._send_json(200, {
                    "scenario": 3,
                    "retry_recovery": harness_res,
                    "total_attempts": fail_count[0],
                    "loop_guardrail_triggered": loop_check[-1],
                    "status": "SUCCESS",
                })
                return

        self._send_json(404, {"error": "Endpoint not found"})


def run_server(port: int = 8000) -> None:
    """Start the HTTP server on specified port."""
    server_address = ("", port)
    httpd = HTTPServer(server_address, AgentApiHandler)
    print(f"\n========================================================")
    print(f"  Agentic Text Comparator UI Server Running")
    print(f"  Local URL: http://localhost:{port}")
    print(f"========================================================\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        httpd.server_close()


if __name__ == "__main__":
    port_arg = 8000
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port_arg = int(sys.argv[1])
    run_server(port=port_arg)
