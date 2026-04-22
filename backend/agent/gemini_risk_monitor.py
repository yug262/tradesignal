"""Gemini Risk Monitor — DISABLED STUB.

This file is intentionally left as a no-op stub.

The Risk Monitor Agent (Agent 4) now uses a pure deterministic rule engine
(risk_rules.py) and does NOT call any LLM in its execution path.

This stub exists solely to prevent ImportError if any legacy code
still references `evaluate_risk_with_llm`.
"""


def evaluate_risk_with_llm(
    signal: dict,
    features: dict,
    rule_engine_result: dict,
) -> dict:
    """DISABLED — returns rule engine result as-is.

    The risk monitor no longer uses Gemini/LLM for decisions.
    All decisions are made deterministically by risk_rules.evaluate_trade().
    """
    result = dict(rule_engine_result)
    result["_source"] = "llm_disabled"
    result["_llm_available"] = False
    return result
