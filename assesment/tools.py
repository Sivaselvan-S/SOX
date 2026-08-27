"""Deterministic text-comparison tools and OpenAI/Gemini-compatible tool registry.

This module provides a comprehensive suite of 6 specialized comparison tools:
1. compute_text_diff: Exact line- & character-level diff calculation.
2. categorize_discrepancy: Structured categorization and severity assessment.
3. analyze_numerical_variance: Quantitative financial and metric delta analysis.
4. extract_sentiment_polarity: Qualitative tone and emotional shift analysis.
5. audit_legal_clauses: Compliance and contract clause change detector.
6. detect_omissions: Missing requirement and deleted checklist auditor.
"""

from __future__ import annotations

import difflib
import json
import re
from typing import Any, Callable, Dict, List, Final

# Valid categories and severity levels for discrepancies
VALID_CATEGORIES: Final[set[str]] = {"Factual", "Omission", "Tone", "Formatting", "Legal", "Financial"}
VALID_SEVERITIES: Final[set[str]] = {"Low", "Medium", "High"}

_POSITIVE_LEXICON = {
    "good", "great", "excellent", "positive", "happy", "reliable", "awesome",
    "stable", "robust", "healthy", "efficient", "optimal", "strong", "best", "compliant"
}
_NEGATIVE_LEXICON = {
    "bad", "terrible", "poor", "negative", "unhappy", "toxic", "unstable",
    "flaky", "broken", "critical", "severe", "degraded", "worst", "slow", "failed", "breached"
}


def compute_text_diff(text_a: str, text_b: str) -> str:
    """Compute line- and character-level differences between two texts using standard ndiff."""
    if not isinstance(text_a, str) or not isinstance(text_b, str):
        raise TypeError("Both text_a and text_b must be strings.")

    lines_a = text_a.splitlines(keepends=True)
    lines_b = text_b.splitlines(keepends=True)
    diff_generator = difflib.ndiff(lines_a, lines_b)
    return "".join(diff_generator)


def categorize_discrepancy(category: str, description: str, severity: str) -> str:
    """Validate and record a categorized discrepancy between compared texts."""
    cat_norm = category.strip().capitalize()
    sev_norm = severity.strip().capitalize()

    if cat_norm not in VALID_CATEGORIES:
        cat_norm = "Factual"
    if sev_norm not in VALID_SEVERITIES:
        sev_norm = "Medium"

    return json.dumps({
        "status": "recorded",
        "category": cat_norm,
        "severity": sev_norm,
        "description": description.strip(),
        "summary": f"[{sev_norm}/{cat_norm}] {description.strip()}"
    })


def analyze_numerical_variance(text_a: str, text_b: str) -> str:
    """Extract and calculate numerical, financial, budget, and SLA percentage deltas."""
    pattern = r"[\$€£]?(\d+(?:,\d+)*(?:\.\d+)?)(%|\/mo|\/yr|ms|rps|k|m)?"
    matches_a = re.findall(pattern, text_a)
    matches_b = re.findall(pattern, text_b)

    deltas = []
    # Extract plain numeric values
    num_a_list = [float(m[0].replace(",", "")) for m in matches_a if m[0]]
    num_b_list = [float(m[0].replace(",", "")) for m in matches_b if m[0]]

    for i, (va, vb) in enumerate(zip(num_a_list, num_b_list)):
        diff = vb - va
        pct_change = ((diff / va) * 100.0) if va != 0 else 0.0
        risk = "High" if abs(pct_change) >= 20.0 or diff != 0 else "Medium"
        deltas.append({
            "index": i + 1,
            "baseline_value": va,
            "comparison_value": vb,
            "absolute_delta": round(diff, 2),
            "percentage_change": f"{pct_change:+.2f}%",
            "variance_severity": risk
        })

    if not deltas:
        # Fallback raw number search
        nums_a = re.findall(r"\b\d+\b", text_a)
        nums_b = re.findall(r"\b\d+\b", text_b)
        deltas.append({
            "baseline_numbers": nums_a,
            "comparison_numbers": nums_b,
            "variance_detected": nums_a != nums_b
        })

    return json.dumps({
        "tool": "analyze_numerical_variance",
        "status": "completed",
        "total_numeric_points_analyzed": len(deltas),
        "variances": deltas
    })


def extract_sentiment_polarity(text_a: str, text_b: str) -> str:
    """Analyze emotional tone, formality shifts, and net polarity scores between texts."""
    words_a = re.findall(r"\b\w+\b", text_a.lower())
    words_b = re.findall(r"\b\w+\b", text_b.lower())

    pos_a = sum(1 for w in words_a if w in _POSITIVE_LEXICON)
    neg_a = sum(1 for w in words_a if w in _NEGATIVE_LEXICON)
    score_a = pos_a - neg_a

    pos_b = sum(1 for w in words_b if w in _POSITIVE_LEXICON)
    neg_b = sum(1 for w in words_b if w in _NEGATIVE_LEXICON)
    score_b = pos_b - neg_b

    polarity_inverted = (score_a > 0 and score_b < 0) or (score_a < 0 and score_b > 0)
    lost_pos = sorted(set(words_a) & _POSITIVE_LEXICON - set(words_b))
    gained_neg = sorted(set(words_b) & _NEGATIVE_LEXICON - set(words_a))

    return json.dumps({
        "tool": "extract_sentiment_polarity",
        "status": "completed",
        "baseline_polarity_score": score_a,
        "comparison_polarity_score": score_b,
        "net_polarity_shift": score_b - score_a,
        "polarity_inversion_detected": polarity_inverted,
        "positive_terms_lost": lost_pos,
        "negative_terms_gained": gained_neg,
        "severity_rating": "High" if polarity_inverted else ("Medium" if score_a != score_b else "Low")
    })


def audit_legal_clauses(text_a: str, text_b: str) -> str:
    """Inspect legal agreements for changes in arbitration, indemnity, deadlines, and liabilities."""
    legal_keywords = [
        "arbitration", "mediation", "dispute", "indemnity", "liability",
        "warranty", "termination", "penalty", "days", "governing law", "jurisdiction"
    ]
    clauses_a = [line for line in text_a.splitlines() if any(k in line.lower() for k in legal_keywords)]
    clauses_b = [line for line in text_b.splitlines() if any(k in line.lower() for k in legal_keywords)]

    findings = []
    # Check deadline changes (e.g. Net 60 -> Net 15, 60 days -> 15 days)
    days_a = re.findall(r"(\d+)\s*(?:days|day)", text_a, re.IGNORECASE)
    days_b = re.findall(r"(\d+)\s*(?:days|day)", text_b, re.IGNORECASE)
    if days_a and days_b and days_a != days_b:
        findings.append({
            "clause_type": "Deadline / Response Window",
            "baseline": f"{days_a[0]} days",
            "comparison": f"{days_b[0]} days",
            "risk_impact": "High Severity (Contractual Timeline Tightened/Altered)"
        })

    # Check dispute resolution mechanism changes
    if "mediation" in text_a.lower() and "arbitration" in text_b.lower():
        findings.append({
            "clause_type": "Dispute Resolution",
            "baseline": "Mediation",
            "comparison": "Binding Arbitration",
            "risk_impact": "High Severity (Legal Rights Waived / Mechanism Altered)"
        })

    # Check penalty changes
    if ("penalty" in text_b.lower() or "fine" in text_b.lower()) and not ("penalty" in text_a.lower() or "fine" in text_a.lower()):
        findings.append({
            "clause_type": "Financial Penalties",
            "baseline": "None",
            "comparison": "Newly Introduced Penalty Clause",
            "risk_impact": "High Severity (Unbudgeted Contractual Liability)"
        })

    if not findings:
        findings.append({
            "clause_type": "General Contract Review",
            "clauses_examined": len(clauses_a) + len(clauses_b),
            "status": "No critical legal clause violations detected"
        })

    return json.dumps({
        "tool": "audit_legal_clauses",
        "status": "completed",
        "legal_clauses_identified": findings
    })


def detect_omissions(text_a: str, text_b: str) -> str:
    """Specifically audit dropped checklist items, missing deliverables, or removed safety sections."""
    lines_a = [l.strip() for l in text_a.splitlines() if l.strip()]
    lines_b = [l.strip() for l in text_b.splitlines() if l.strip()]

    omissions = []
    for line in lines_a:
        # Check if line or similar exists in text_b
        best_match = max([difflib.SequenceMatcher(None, line.lower(), lb.lower()).ratio() for lb in lines_b], default=0.0)
        if best_match < 0.6:
            omissions.append({
                "omitted_item": line,
                "impact": "High Severity (Requirement / Section completely removed from comparison text)"
            })

    return json.dumps({
        "tool": "detect_omissions",
        "status": "completed",
        "total_omissions_found": len(omissions),
        "omissions": omissions
    })


# Full OpenAI / Google Gemini function calling tool schemas
TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "compute_text_diff",
            "description": "Compute line and word level differences between two text strings using standard ndiff.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text_a": {"type": "string", "description": "The original baseline text string."},
                    "text_b": {"type": "string", "description": "The modified comparison text string."}
                },
                "required": ["text_a", "text_b"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "categorize_discrepancy",
            "description": "Categorize, assess severity, and record a specific discrepancy identified in the text diff.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["Factual", "Omission", "Tone", "Formatting", "Legal", "Financial"],
                        "description": "The category of the identified difference."
                    },
                    "description": {
                        "type": "string",
                        "description": "Detailed explanation of what differs between the texts."
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["Low", "Medium", "High"],
                        "description": "Severity assessment level."
                    }
                },
                "required": ["category", "description", "severity"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_numerical_variance",
            "description": "Compute exact numerical deltas, currency changes, budget variations, and SLA percentages between texts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text_a": {"type": "string", "description": "Baseline text containing original numbers/metrics."},
                    "text_b": {"type": "string", "description": "Comparison text containing modified numbers/metrics."}
                },
                "required": ["text_a", "text_b"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "extract_sentiment_polarity",
            "description": "Analyze emotional polarity shifts, formality transitions, and positive/negative sentiment deltas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text_a": {"type": "string", "description": "Original text to evaluate baseline sentiment."},
                    "text_b": {"type": "string", "description": "Comparison text to evaluate modified sentiment."}
                },
                "required": ["text_a", "text_b"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "audit_legal_clauses",
            "description": "Audit contract clauses for changes in arbitration, dispute resolution, indemnities, and deadline windows.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text_a": {"type": "string", "description": "Original legal contract or agreement text."},
                    "text_b": {"type": "string", "description": "Modified legal contract or agreement text."}
                },
                "required": ["text_a", "text_b"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "detect_omissions",
            "description": "Detect deleted requirements, dropped checklist bullet points, or missing sections between texts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text_a": {"type": "string", "description": "Original baseline document."},
                    "text_b": {"type": "string", "description": "Comparison document to check for missing items."}
                },
                "required": ["text_a", "text_b"]
            }
        }
    }
]

# Mapping of tool names to executable Python functions
TOOL_HANDLERS: Dict[str, Callable[..., str]] = {
    "compute_text_diff": compute_text_diff,
    "categorize_discrepancy": categorize_discrepancy,
    "analyze_numerical_variance": analyze_numerical_variance,
    "extract_sentiment_polarity": extract_sentiment_polarity,
    "audit_legal_clauses": audit_legal_clauses,
    "detect_omissions": detect_omissions,
}
