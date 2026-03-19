"""
Clarification Persona

Single responsibility:
- Ask targeted questions for ambiguous/missing parameters
- Pause and resume interaction support

SRS source:
- Persona contracts: Section "Persona Input/Output Contracts"
- FR-73 to FR-87

Input contract:
{
  "ambiguities": [{"type": "string", "description": "string"}],
  "missing_params": ["string"],
  "context": "object"
}

Output contract:
{
  "questions": ["string"],
  "parameter_options": [{"param": "string", "options": ["value"]}],
  "pause_reason": "string"
}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ClarificationInput:
  """Clarification persona input contract."""

  ambiguities: list[dict[str, str]]
  missing_params: list[str]
  context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ClarificationOutput:
  """Clarification persona output contract."""

  questions: list[str]
  parameter_options: list[dict[str, Any]]
  pause_reason: str


class ClarificationPersona:
  """Generates deterministic clarification prompts for ambiguous queries."""

  def generate(self, payload: ClarificationInput) -> ClarificationOutput:
    questions: list[str] = []
    parameter_options: list[dict[str, Any]] = []

    ambiguity_types = {a.get("type", "") for a in payload.ambiguities}

    if "vague_query" in ambiguity_types:
      questions.append(
        "Can you describe exactly what you want to analyze? "
        "For example: metric, entity, and time period."
      )

    if "missing_time_range" in ambiguity_types or "time_range" in payload.missing_params:
      questions.append(
        "What time period should I use? (e.g., last 7 days, last month, this quarter)"
      )
      parameter_options.append(
        {
          "param": "time_range",
          "options": ["last_7_days", "last_30_days", "last_month", "this_quarter", "custom"],
          "default": "last_30_days",
        }
      )

    if "ambiguous_metric" in ambiguity_types or "metric" in payload.missing_params:
      questions.append(
        "Which metric should I compute? (e.g., total sales, order count, active users)"
      )
      parameter_options.append(
        {
          "param": "metric",
          "options": ["count", "sum", "average"],
          "default": "count",
        }
      )

    if not questions:
      questions.append("I need one more detail to continue. What exactly should I query?")

    return ClarificationOutput(
      questions=questions,
      parameter_options=parameter_options,
      pause_reason="Missing or ambiguous parameters",
    )

