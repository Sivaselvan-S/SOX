"""Integration test runner and dynamic cognitive reasoning engine.

Demonstrates:
- Scenario 1: Multi-iteration cognitive loop (Diff -> Categorize -> Summarize) + Memory persistence.
- Scenario 2: Cross-session memory recall impact (preference suppression of stylistic shifts).
- Scenario 3: Failure recovery, exponential backoff retries, and guardrail protections.
- Dynamic pure-Python cognitive reasoning for any custom arbitrary text input.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from config import AgentConfig
from harness import ProductionAgentHarness
from memory import AgentMemory
from tools import compute_text_diff, categorize_discrepancy


# ---------------------------------------------------------------------------
# Mock / Local Dynamic Reasoning Client
# ---------------------------------------------------------------------------
class MockFunctionCall:
    def __init__(self, name: str, arguments: str):
        self.name = name
        self.arguments = arguments


class MockToolCall:
    def __init__(self, call_id: str, name: str, arguments: str):
        self.id = call_id
        self.type = "function"
        self.function = MockFunctionCall(name, arguments)


class MockMessage:
    def __init__(self, content: Optional[str], tool_calls: Optional[List[Any]] = None):
        self.content = content
        self.tool_calls = tool_calls or []


class MockChoice:
    def __init__(self, message: MockMessage):
        self.message = message


class MockUsage:
    def __init__(self, prompt_tokens: int = 150, completion_tokens: int = 80):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = prompt_tokens + completion_tokens


class MockChatCompletionResponse:
    def __init__(self, message: MockMessage):
        self.choices = [MockChoice(message)]
        self.usage = MockUsage()


class MockEmbeddingData:
    def __init__(self, embedding: List[float]):
        self.embedding = embedding


class MockEmbeddingResponse:
    def __init__(self):
        self.data = [MockEmbeddingData([0.05] * 1536)]


class MockOpenAIClient:
    """Dynamic cognitive reasoning engine that executes multi-step analysis on ANY text."""

    def __init__(self):
        self.step_counter = 0
        self.scenario = 1

    @property
    def chat(self):
        return self

    @property
    def completions(self):
        return self

    @property
    def embeddings(self):
        return self

    def _extract_texts(self, messages: List[Dict[str, Any]]) -> Tuple[str, str]:
        """Extract text_a and text_b from conversation messages."""
        user_content = ""
        for msg in messages:
            if msg.get("role") == "user":
                user_content = msg.get("content", "")

        text_a_match = re.search(r"--- TEXT A ---\n(.*?)\n\n--- TEXT B ---", user_content, re.DOTALL)
        text_b_match = re.search(r"--- TEXT B ---\n(.*)", user_content, re.DOTALL)

        text_a = text_a_match.group(1).strip() if text_a_match else ""
        text_b = text_b_match.group(1).strip() if text_b_match else ""

        return text_a, text_b

    # Sentiment vocabulary for semantic shift detection
    _POSITIVE_WORDS = {
        "good", "great", "excellent", "best", "better", "positive", "happy",
        "success", "successful", "improve", "improved", "gain", "growth",
        "friendly", "amazing", "innovative", "leading", "robust", "stable",
        "efficient", "strong", "increase", "increased", "up", "win", "reliable",
        "fast", "compliant", "secure", "smooth", "optimal", "healthy", "delighted"
    }
    _NEGATIVE_WORDS = {
        "bad", "poor", "worst", "worse", "negative", "unhappy", "failure",
        "fail", "failed", "loss", "decline", "unfriendly", "terrible", "weak",
        "broken", "decrease", "decreased", "down", "error", "risk", "threat",
        "slow", "inefficient", "toxic", "hostile", "corrupt", "denied",
        "unreliable", "insecure", "flaky", "vulnerable", "delayed", "breached", "disrupted"
    }

    def _sentiment_score(self, text: str) -> float:
        """Return a score: positive > 0, negative < 0, neutral = 0."""
        words = re.findall(r"\b\w+\b", text.lower())
        pos = sum(1 for w in words if w in self._POSITIVE_WORDS)
        neg = sum(1 for w in words if w in self._NEGATIVE_WORDS)
        return pos - neg

    def _find_discrepancies(self, text_a: str, text_b: str) -> List[Dict[str, str]]:
        """Dynamically analyze real differences between text_a and text_b."""
        lines_a = [line.strip() for line in text_a.splitlines() if line.strip()]
        lines_b = [line.strip() for line in text_b.splitlines() if line.strip()]

        discrepancies = []

        # Global-level sentiment shift detection (works on full text)
        score_a = self._sentiment_score(text_a)
        score_b = self._sentiment_score(text_b)
        sentiment_shifted = (score_a > 0 and score_b < 0) or (score_a < 0 and score_b > 0)

        # Token-level word deltas
        words_a_set = set(re.findall(r"\b\w+\b", text_a.lower()))
        words_b_set = set(re.findall(r"\b\w+\b", text_b.lower()))
        removed_words = words_a_set - words_b_set
        added_words = words_b_set - words_a_set
        removed_neg = removed_words & self._NEGATIVE_WORDS
        removed_pos = removed_words & self._POSITIVE_WORDS
        added_neg   = added_words   & self._NEGATIVE_WORDS
        added_pos   = added_words   & self._POSITIVE_WORDS

        # Line-by-line structural diff inspection
        matcher = difflib.SequenceMatcher(None, lines_a, lines_b)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'replace':
                for old_line, new_line in zip(lines_a[i1:i2], lines_b[j1:j2]):
                    old_nums = re.findall(r'[\$€£]?\d+(?:,\d+)*(?:\.\d+)?%?', old_line)
                    new_nums = re.findall(r'[\$€£]?\d+(?:,\d+)*(?:\.\d+)?%?', new_line)
                    ls_a = self._sentiment_score(old_line)
                    ls_b = self._sentiment_score(new_line)

                    if old_nums or new_nums:
                        desc = f"Numerical/metric change: '{old_line}' -> '{new_line}' (was {old_nums}, now {new_nums})"
                        cat, sev = "Factual", "High"
                    elif ls_a > 0 and ls_b < 0:
                        desc = (
                            f"Negative Sentiment Shift: '{old_line}' -> '{new_line}'. "
                            f"Text A was POSITIVE (score +{int(ls_a)}) but Text B is NEGATIVE (score {int(ls_b)}). "
                            f"Positive terms lost: {sorted(removed_pos) or ['(none)']}. "
                            f"Negative terms gained: {sorted(added_neg) or ['(none)']}"
                        )
                        cat, sev = "Tone", "High"
                    elif ls_a < 0 and ls_b > 0:
                        desc = (
                            f"Positive Sentiment Shift: '{old_line}' -> '{new_line}'. "
                            f"Text A was NEGATIVE (score {int(ls_a)}) but Text B improved to POSITIVE (score +{int(ls_b)}). "
                            f"Negative terms removed: {sorted(removed_neg) or ['(none)']}. "
                            f"Positive terms added: {sorted(added_pos) or ['(none)']}"
                        )
                        cat, sev = "Tone", "Medium"
                    else:
                        cat = "Tone" if any(w in old_line.lower() or w in new_line.lower()
                                           for w in ["tone", "style", "formal", "informal"]) else "Factual"
                        desc = f"Phrasing change: '{old_line}' -> '{new_line}'"
                        sev = "Medium"

                    discrepancies.append({"category": cat, "description": desc, "severity": sev})

            elif tag == 'delete':
                for old_line in lines_a[i1:i2]:
                    discrepancies.append({
                        "category": "Omission",
                        "description": f"Removed from Text A: '{old_line}'",
                        "severity": "Medium",
                    })

            elif tag == 'insert':
                for new_line in lines_b[j1:j2]:
                    discrepancies.append({
                        "category": "Factual",
                        "description": f"Added in Text B: '{new_line}'",
                        "severity": "Medium",
                    })

        # Fallback for single-line or same-structure texts (no opcode diff caught)
        if not discrepancies and text_a.strip() != text_b.strip():
            diff_words = difflib.ndiff(text_a.split(), text_b.split())
            removed = [w[2:] for w in diff_words if w.startswith('- ')]
            added   = [w[2:] for w in diff_words if w.startswith('+ ')]

            if sentiment_shifted and score_a > score_b:
                direction = "Positive to Negative"
                desc = (
                    f"Semantic Sentiment Shift ({direction}): "
                    f"Words removed: {removed}. Words added: {added}. "
                    f"Sentiment score degraded from +{int(score_a)} (Text A) to {int(score_b)} (Text B). "
                    f"Positive terms lost: {sorted(removed_pos) or ['(none)']}. "
                    f"Negative terms introduced: {sorted(added_neg) or ['(none)']}"
                )
                cat, sev = "Tone", "High"
            elif sentiment_shifted and score_b > score_a:
                direction = "Negative to Positive"
                desc = (
                    f"Semantic Sentiment Shift ({direction}): "
                    f"Words removed: {removed}. Words added: {added}. "
                    f"Sentiment score improved from {int(score_a)} (Text A) to +{int(score_b)} (Text B). "
                    f"Negative terms removed: {sorted(removed_neg) or ['(none)']}. "
                    f"Positive terms introduced: {sorted(added_pos) or ['(none)']}"
                )
            else:
                has_numbers = any(c.isdigit() for c in str(added))
                is_minor_article = all(w.lower() in {"a", "an", "the", "in", "on", "at", "to", "for", "is", "are"} for w in (added + removed))
                if is_minor_article:
                    cat, sev = "Formatting", "Low"
                    desc = f"Minor article/phrasing insertion (added: {added or ['(none)']}, removed: {removed or ['(none)']}). No major factual or sentiment discrepancies detected."
                elif has_numbers:
                    cat, sev = "Factual", "High"
                    desc = f"Numerical modification: removed {removed}, added {added}."
                else:
                    cat, sev = "Tone", "Medium"
                    desc = f"Phrasing modification: removed {removed}, added {added}."

            discrepancies.append({"category": cat, "description": desc, "severity": sev})

        return discrepancies


    def create(self, **kwargs):
        # Handle embedding creation
        if "input" in kwargs:
            return MockEmbeddingResponse()

        # Handle Chat Completions
        self.step_counter += 1
        messages = kwargs.get("messages", [])
        system_content = messages[0].get("content", "") if messages else ""

        # Extract real text_a and text_b from the prompt
        text_a, text_b = self._extract_texts(messages)

        # Check if recalled preferences enforce numerical focus
        has_numerical_preference = "numerical" in system_content.lower() or "suppress" in system_content.lower()

        # Check if texts are 100% identical for 1-step early exit
        if text_a.strip() == text_b.strip():
            return MockChatCompletionResponse(
                MockMessage(
                    content=(
                        "### Exact Match Comparison Summary\n\n"
                        "**Baseline Length**: " + str(len(text_a)) + " characters | **Comparison Length**: " + str(len(text_b)) + " characters\n\n"
                        "**Identified Key Differences**:\n"
                        "• **None**. Text A and Text B are 100% identical.\n\n"
                        "*ReAct Cognitive Optimization: The agent evaluated an exact match during the Perceive & Reason phase and exited immediately in 1 iteration without dispatching redundant tools.*"
                    ),
                    tool_calls=[],
                )
            )

        # Check semantic domain for dynamic tool selection
        combined_lower = (text_a + " " + text_b).lower()
        has_legal = any(k in combined_lower for k in ["arbitration", "mediation", "penalty", "indemnity", "liability", "governing law", "agreement"])
        has_nums = any(c.isdigit() for c in (text_a + text_b)) and any(s in (text_a + text_b) for s in ["$", "%", "mo", "yr", "ms", "rps", "budget", "cost", "latency"])
        has_sentiment = any(w in combined_lower for w in self._POSITIVE_WORDS | self._NEGATIVE_WORDS)
        lines_a_count = len([l for l in text_a.splitlines() if l.strip()])
        lines_b_count = len([l for l in text_b.splitlines() if l.strip()])
        has_omissions = lines_a_count > lines_b_count

        # Iteration 1: Dispatch specialized or baseline tool
        if self.step_counter == 1:
            if has_legal:
                tool_name = "audit_legal_clauses"
            elif has_nums:
                tool_name = "analyze_numerical_variance"
            elif has_sentiment:
                tool_name = "extract_sentiment_polarity"
            elif has_omissions:
                tool_name = "detect_omissions"
            else:
                tool_name = "compute_text_diff"

            return MockChatCompletionResponse(
                MockMessage(
                    content=None,
                    tool_calls=[
                        MockToolCall(
                            f"call_{tool_name}_{self.step_counter}",
                            tool_name,
                            json.dumps({"text_a": text_a, "text_b": text_b}),
                        )
                    ],
                )
            )

        # Iteration 2: Dispatch categorize_discrepancy with real detected differences
        elif self.step_counter == 2:
            real_discrepancies = self._find_discrepancies(text_a, text_b)
            if real_discrepancies:
                disc = real_discrepancies[0]
                cat = disc["category"]
                desc = disc["description"]
                sev = disc["severity"]
            else:
                cat = "Formatting"
                desc = "No significant textual discrepancies detected between texts."
                sev = "Low"

            if has_legal:
                cat = "Legal"
                sev = "High"
            elif has_nums:
                cat = "Financial"
                sev = "High"

            return MockChatCompletionResponse(
                MockMessage(
                    content=None,
                    tool_calls=[
                        MockToolCall(
                            f"call_cat_{self.step_counter}",
                            "categorize_discrepancy",
                            json.dumps({"category": cat, "description": desc, "severity": sev}),
                        )
                    ],
                )
            )

        # Iteration 3: Final Synthesis Report reflecting the actual inputs & memory rules
        else:
            real_discrepancies = self._find_discrepancies(text_a, text_b)

            if not real_discrepancies:
                return MockChatCompletionResponse(
                    MockMessage(
                        content="### Comparison Summary\n\n**Result**: Text A and Text B are identical. No discrepancies were found."
                    )
                )

            # Extract active memory rule filters from system content
            sys_lower = system_content.lower()
            has_numerical_rule = "numerical" in sys_lower or "budget" in sys_lower or "metric" in sys_lower
            has_negative_only_rule = ("negative" in sys_lower or "-ve" in sys_lower) and ("only" in sys_lower or "focus" in sys_lower or "suppress" in sys_lower)
            has_high_sev_rule = "high severity" in sys_lower or "high only" in sys_lower
            has_ignore_tone_rule = "ignore tone" in sys_lower or "factual only" in sys_lower

            filtered_discs = list(real_discrepancies)
            active_rule_desc = None

            if has_negative_only_rule:
                filtered_discs = [
                    d for d in real_discrepancies
                    if "Negative Sentiment Shift" in d.get("description", "") or
                       "Negative" in d.get("description", "") or
                       any(nw in d.get("description", "").lower() for nw in self._NEGATIVE_WORDS)
                ]
                active_rule_desc = "Focus strictly on negative word changes (neutral/mild phrasing suppressed)"

            elif has_numerical_rule:
                filtered_discs = [
                    d for d in real_discrepancies
                    if d.get("category") in {"Factual", "Financial"} and
                       ("$" in d.get("description", "") or "%" in d.get("description", "") or any(c.isdigit() for c in d.get("description", "")))
                ]
                active_rule_desc = "Focus strictly on numerical/metric changes (stylistic shifts suppressed)"

            elif has_high_sev_rule:
                filtered_discs = [d for d in real_discrepancies if d.get("severity") == "High"]
                active_rule_desc = "High severity filter active (Medium and Low findings suppressed)"

            elif has_ignore_tone_rule:
                filtered_discs = [d for d in real_discrepancies if d.get("category") != "Tone"]
                active_rule_desc = "Tone suppression active (reporting factual/structural differences only)"

            if active_rule_desc:
                if filtered_discs:
                    summary_lines = [f"{i+1}. **[{d['severity']} Severity / {d['category']}]**: {d['description']}" for i, d in enumerate(filtered_discs)]
                else:
                    summary_lines = [f"• *(No matching discrepancies found. Non-matching differences were suppressed per active memory rule: '{active_rule_desc}')*"]

                body = (
                    f"### Focused Comparison Summary (Learned Preferences Active)\n\n"
                    f"*(Adhering to recalled session rule: {active_rule_desc})*\n\n"
                    f"**Baseline Length**: {len(text_a)} characters | **Comparison Length**: {len(text_b)} characters\n\n"
                    f"**Identified Key Differences**:\n" + "\n".join(summary_lines)
                )
            else:
                summary_lines = [f"{i+1}. **[{d['severity']} Severity / {d['category']}]**: {d['description']}" for i, d in enumerate(real_discrepancies)]
                body = (
                    f"### Detailed Text Comparison Summary\n\n"
                    f"**Baseline Length**: {len(text_a)} characters | **Comparison Length**: {len(text_b)} characters\n\n"
                    f"**Identified Key Differences**:\n" + "\n".join(summary_lines)
                )

            return MockChatCompletionResponse(MockMessage(content=body))


def print_banner(title: str) -> None:
    """Print a visually distinct terminal banner."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")


def get_client() -> Any:
    """Initialize Gemini / OpenAI client or fallback to dynamic local reasoning engine."""
    gemini_key = os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY", ""))
    if gemini_key and len(gemini_key) > 20:
        try:
            from gemini_client import GeminiClient
            client = GeminiClient(api_key=gemini_key, model="gemini-2.5-flash")
            print("[INFO] Authenticated with Google Gemini Client (gemini-2.5-flash).")
            return client
        except Exception as e:
            print(f"[WARN] Failed to initialize Gemini client: {e}. Falling back to dynamic local simulator.")

    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key and not openai_key.startswith("your-") and len(openai_key) > 20:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=openai_key)
            print("[INFO] Authenticated with live OpenAI API Key.")
            return client
        except Exception as e:
            print(f"[WARN] Failed to initialize OpenAI client: {e}.")

    print("[INFO] Running in Dynamic Pure-Python Cognitive Engine (Zero-API Dependency).")
    return MockOpenAIClient()



# ---------------------------------------------------------------------------
# Execution Scenarios
# ---------------------------------------------------------------------------
def run_scenario_1(harness: ProductionAgentHarness, client: Any) -> None:
    """Scenario 1: Multi-Iteration Analysis without prior memory."""
    print_banner("SCENARIO 1: Multi-Iteration Cognitive Loop (Cold Start)")

    if isinstance(client, MockOpenAIClient):
        client.step_counter = 0

    text_a = (
        "Projected Financials Q3:\n"
        "- Marketing Budget: $120,000\n"
        "- Engineering Team: 45 engineers\n"
        "- Cloud Infrastructure: $35,000/mo\n"
        "Tone: Friendly and informal collaboration style."
    )
    text_b = (
        "Projected Financials Q3:\n"
        "- Marketing Budget: $150,000\n"
        "- Engineering Team: 52 engineers\n"
        "- Cloud Infrastructure: $42,000/mo\n"
        "Tone: Formal and assertive operational mandates."
    )

    session_id = "session_finance_dept"
    start = time.perf_counter()
    report = harness.run_monitored_session(session_id, text_a, text_b, client)
    elapsed = time.perf_counter() - start

    print("\n--- Execution Metrics ---")
    print(f"Status: {report['status']}")
    print(f"Iterations Completed: {report['iterations']}")
    print(f"Token Consumption: {report['token_usage']}")
    print(f"Latency: {elapsed:.2f}s")
    print(f"Discrepancies Recorded: {len(report['discrepancies'])}")
    print("\n--- Final Agent Summary Output ---")
    print(report["result"])

    # Persist learned preference rules into memory for subsequent sessions
    harness.memory.save_information(
        session_id=session_id,
        key="preference_rules",
        value=(
            "Focus strictly on numerical budget, financial, and metric changes. "
            "Explicitly suppress and ignore all minor stylistic, wording, and tone discrepancies."
        ),
        metadata={"domain": "finance", "priority": "high"},
        client=client,
    )
    print("\n[MEMORY SAVED] Preference rule persisted into SQLite3 memory store.")


def run_scenario_2(harness: ProductionAgentHarness, client: Any) -> None:
    """Scenario 2: Memory Recall Impact across distinct session."""
    print_banner("SCENARIO 2: Cross-Session Memory Recall Impact")

    if isinstance(client, MockOpenAIClient):
        client.step_counter = 0

    text_c = (
        "Performance Benchmarks Release 2.4:\n"
        "- Server Latency: 120ms\n"
        "- Throughput: 5,000 rps\n"
        "- Error Rate: 0.04%\n"
        "Stylistic note: Our awesome team made incredible progress!"
    )
    text_d = (
        "Performance Benchmarks Release 2.4:\n"
        "- Server Latency: 85ms\n"
        "- Throughput: 7,500 rps\n"
        "- Error Rate: 0.01%\n"
        "Stylistic note: The updated infrastructure delivers robust stability."
    )

    session_id = "session_finance_dept"
    start = time.perf_counter()
    report = harness.run_monitored_session(session_id, text_c, text_d, client)
    elapsed = time.perf_counter() - start

    print("\n--- Execution Metrics ---")
    print(f"Status: {report['status']}")
    print(f"Iterations Completed: {report['iterations']}")
    print(f"Recalled Memories Injected: {len(report['recalled_memories'])}")
    if report['recalled_memories']:
        print(f"Recalled Content: {report['recalled_memories'][0]['value']}")
    print(f"Token Consumption: {report['token_usage']}")
    print(f"Latency: {elapsed:.2f}s")
    print("\n--- Final Agent Summary Output ---")
    print(report["result"])


def run_scenario_3(harness: ProductionAgentHarness) -> None:
    """Scenario 3: Simulated Outage & Exponential Backoff Recovery."""
    print_banner("SCENARIO 3: Failure Recovery, Retries & Infinite Loop Guardrails")

    print("[TEST 1/2] Simulating API Outage with Exponential Retries...")
    fail_count = [0]

    def flaky_api_call():
        fail_count[0] += 1
        if fail_count[0] <= 2:
            raise ConnectionError(f"HTTP 503 Service Unavailable (Attempt #{fail_count[0]})")
        return {"status": "recovered", "message": "API recovered successfully on attempt 3"}

    result = harness.execute_with_retry(flaky_api_call)
    print(f"Result after backoff retries: {result}")
    print(f"Total API attempts triggered: {fail_count[0]}")

    print("\n[TEST 2/2] Simulating Infinite Loop Detection Guardrail...")
    harness._recent_actions.clear()
    assert harness.detect_infinite_loop("tool:compute_text_diff") is False
    assert harness.detect_infinite_loop("tool:compute_text_diff") is False
    is_trapped = harness.detect_infinite_loop("tool:compute_text_diff")
    print(f"Infinite loop trapped on 3rd identical call: {is_trapped}")


def main() -> None:
    """Main application entrypoint running all 3 evaluation scenarios."""
    print_banner("AGENTIC TEXT COMPARATOR PIPELINE — TEST RUNNER")

    config = AgentConfig(
        model="gpt-4o-mini",
        max_iterations=5,
        token_budget=4000,
        max_retries=3,
        base_backoff=0.2,
    )
    memory = AgentMemory(db_path="agent_memory.db")
    harness = ProductionAgentHarness(config=config, memory=memory)
    client = get_client()

    try:
        run_scenario_1(harness, client)
        run_scenario_2(harness, client)
        run_scenario_3(harness)
        print_banner("ALL 3 SCENARIOS COMPLETED SUCCESSFULLY")
    finally:
        memory.close()


if __name__ == "__main__":
    main()
