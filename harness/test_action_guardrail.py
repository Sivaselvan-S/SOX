#!/usr/bin/env python3
"""
PS-3.1 Simulation Harness for Pre-Execution Action Guardrail.
Runs sample tool calls through the ActionGuardEngine and asserts all 3 outcome types fire correctly.
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.detectors.action_guard import ActionGuardEngine
from app.schemas.action_guard import GuardOutcome


def run_simulation_harness():
    print("=" * 80)
    print("PS-3.1 ACTION GUARDRAIL SIMULATION HARNESS")
    print("=" * 80)

    guard = ActionGuardEngine.from_settings()
    print(f"Loaded {len(guard.rules)} rules from 'action_rules.yaml'. Dry-run: {guard.dry_run}\n")

    test_cases = [
        {
            "name": "1. Bulk Delete (500 records)",
            "tool": "database_delete",
            "params": {"query": "DELETE FROM users WHERE active = 0", "record_count": 500},
            "expected_outcome": GuardOutcome.BLOCK,
        },
        {
            "name": "2. Small Delete (5 records)",
            "tool": "database_delete",
            "params": {"query": "DELETE FROM test_tmp WHERE id = 1", "record_count": 5},
            "expected_outcome": GuardOutcome.ALLOW,
        },
        {
            "name": "3. External Email (gmail.com)",
            "tool": "send_email",
            "params": {"to": "attacker@gmail.com", "to_domain": "gmail.com", "subject": "Data Dump"},
            "expected_outcome": GuardOutcome.REQUIRE_HITL,
        },
        {
            "name": "4. Internal Email (company.internal)",
            "tool": "send_email",
            "params": {"to": "boss@company.internal", "to_domain": "company.internal", "subject": "Status Report"},
            "expected_outcome": GuardOutcome.ALLOW,
        },
        {
            "name": "5. Read Confidential File",
            "tool": "read_file",
            "params": {"path": "/var/secrets/confidential_report.pdf"},
            "expected_outcome": GuardOutcome.LOG_AND_ALLOW,
        },
        {
            "name": "6. Read Public File",
            "tool": "read_file",
            "params": {"path": "/var/public/readme.txt"},
            "expected_outcome": GuardOutcome.ALLOW,
        },
    ]

    passed_count = 0

    print(f"{'TEST CASE':<32} | {'TOOL NAME':<16} | {'OUTCOME':<15} | {'STATUS':<8}")
    print("-" * 80)

    for case in test_cases:
        res = guard.evaluate(case["tool"], case["params"])
        is_pass = res.outcome == case["expected_outcome"]
        if is_pass:
            passed_count += 1

        status_str = "[PASS]" if is_pass else "[FAIL]"
        outcome_str = res.outcome.value.upper()

        print(f"{case['name']:<32} | {case['tool']:<16} | {outcome_str:<15} | {status_str:<8}")
        if res.matched_rule:
            print(f"   ↳ Matched Rule: [{res.matched_rule.id}] {res.matched_rule.name} -> Reason: {res.reason}")

    print("-" * 80)
    print(f"LIVE HARNESS RESULTS: {passed_count}/{len(test_cases)} Test Cases Passed.")
    print("=" * 80)

    # Dry-Run Mode Simulation Test
    print("\n" + "=" * 80)
    print("BONUS: DRY-RUN MODE SIMULATION TEST")
    print("=" * 80)
    guard_dry = ActionGuardEngine(rules=guard.rules, dry_run=True)
    print(f"Loaded {len(guard_dry.rules)} rules. Dry-run Mode: {guard_dry.dry_run}\n")

    dry_passed = 0
    for case in test_cases:
        res = guard_dry.evaluate(case["tool"], case["params"])
        # In dry run, rule matches and records violation (res.dry_run=True), but action execution is not aborted
        is_pass = res.outcome == case["expected_outcome"] and res.dry_run is True
        if is_pass:
            dry_passed += 1
        status_str = "[PASS]" if is_pass else "[FAIL]"
        outcome_str = res.outcome.value.upper() + (" (SIMULATED)" if res.matched_rule else " (ALLOWED)")
        print(f"{case['name']:<32} | {case['tool']:<16} | {outcome_str:<25} | {status_str:<8}")

    print("-" * 80)
    print(f"DRY-RUN HARNESS RESULTS: {dry_passed}/{len(test_cases)} Test Cases Passed.")
    print("=" * 80)

    return (passed_count == len(test_cases)) and (dry_passed == len(test_cases))


if __name__ == "__main__":
    success = run_simulation_harness()
    sys.exit(0 if success else 1)
