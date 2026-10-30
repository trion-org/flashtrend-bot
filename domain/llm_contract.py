"""The ``ideas.llm`` contract (docs/02 · Gemini): validate Gemini's JSON before it is stored."""
from __future__ import annotations

from domain.models import LLM_FORMATS, LLM_RISKS

TEXT_KEYS = ("summary", "why_viral", "hook")


class LlmSchemaError(ValueError):
    pass


def validate_llm(obj: object) -> dict:
    """Return a clean ``ideas.llm`` dict or raise :class:`LlmSchemaError`.

    Keys: summary, why_viral, hook (non-empty strings), angles (exactly 3 non-empty strings),
    format (long|short|compilation|review), risk (copyright|reused|kids|sensitive).
    Unknown extra keys are dropped.
    """
    if not isinstance(obj, dict):
        raise LlmSchemaError("llm output is not a JSON object")
    out: dict = {}
    for key in TEXT_KEYS:
        val = obj.get(key)
        if not isinstance(val, str) or not val.strip():
            raise LlmSchemaError(f"{key} must be a non-empty string")
        out[key] = val.strip()
    angles = obj.get("angles")
    if (
        not isinstance(angles, list)
        or len(angles) != 3
        or not all(isinstance(a, str) and a.strip() for a in angles)
    ):
        raise LlmSchemaError("angles must be exactly 3 non-empty strings")
    out["angles"] = [a.strip() for a in angles]
    if obj.get("format") not in LLM_FORMATS:
        raise LlmSchemaError(f"format must be one of {LLM_FORMATS}")
    out["format"] = obj["format"]
    if obj.get("risk") not in LLM_RISKS:
        raise LlmSchemaError(f"risk must be one of {LLM_RISKS}")
    out["risk"] = obj["risk"]
    return out
