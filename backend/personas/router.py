"""
Router Persona

Single responsibility:
- Intent classification
- Ambiguity detection
- Execution plan selection
- Never responds to user directly

SRS source:
- Persona contracts: Section "Persona Input/Output Contracts"
- FR-6 to FR-13

Input contract:
{
  "nl_query": "string",
  "conversation_id": "string",
  "user_context": "object (optional)"
}

Output contract:
{
  "next_persona": "string",
  "execution_plan": ["string"],
  "requires_clarification": "boolean",
  "detected_intent": "string"
}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Any


class IntentType(str, Enum):
  """Router intent classes used to select execution plans."""

  ANALYTICS = "analytics"
  SCHEMA_DISCOVERY = "schema_discovery"
  DEBUGGING = "debugging"
  VISUALIZATION = "visualization"
  ADMIN = "admin"


@dataclass(frozen=True)
class RouterInput:
  """Router input contract."""

  nl_query: str
  conversation_id: str
  user_context: dict[str, Any] | None = None


@dataclass(frozen=True)
class RouterDecision:
  """Router output including planning and clarification metadata."""

  next_persona: str
  execution_plan: list[str]
  requires_clarification: bool
  detected_intent: str
  ambiguities: list[dict[str, str]] = field(default_factory=list)
  missing_params: list[str] = field(default_factory=list)


class RouterPersona:
  """
  Heuristic Router persona.

  Note:
  - This is a deterministic fallback implementation until LLM routing is added.
  - It intentionally favors clarification over guessing when query intent is vague.
  """

  _TIME_RANGE_RE = re.compile(
    r"\b(today|yesterday|week|month|quarter|year|ytd|mtd|last\s+\d+\s+days|between\s+\d{4}-\d{2}-\d{2})\b",
    re.IGNORECASE,
  )
  _ANALYTICS_HINT_RE = re.compile(
    r"\b(show|list|get|count|total|sum|avg|average|trend|growth|sales|revenue|users|orders)\b",
    re.IGNORECASE,
  )
  _SCHEMA_HINT_RE = re.compile(r"\b(schema|table|tables|column|columns|relationship|foreign key)\b", re.IGNORECASE)
  _VIS_HINT_RE = re.compile(r"\b(chart|graph|plot|visual|dashboard|line|bar|pie)\b", re.IGNORECASE)
  _DEBUG_HINT_RE = re.compile(r"\b(error|fail|failing|bug|debug|why|issue|invalid sql)\b", re.IGNORECASE)
  _ADMIN_HINT_RE = re.compile(r"\b(create|drop|grant|revoke|alter|truncate|admin)\b", re.IGNORECASE)

  _VAGUE_QUERIES = {
    "hey",
    "hi",
    "hello",
    "show",
    "show me",
    "data",
    "report",
  }

  def decide(self, payload: RouterInput) -> RouterDecision:
    """Classify intent, detect ambiguity, and choose next persona/plan."""
    query = payload.nl_query.strip()
    query_lower = query.lower()

    intent = self._classify_intent(query_lower)
    ambiguities, missing_params = self._detect_ambiguity(query_lower)

    requires_clarification = bool(ambiguities or missing_params)
    if requires_clarification:
      return RouterDecision(
        next_persona="Clarification",
        execution_plan=["Clarification"],
        requires_clarification=True,
        detected_intent=intent.value,
        ambiguities=ambiguities,
        missing_params=missing_params,
      )

    return RouterDecision(
      next_persona="SchemaExpert",
      execution_plan=[
        "SchemaExpert",
        "ContextRetriever",
        "SQLWriter",
        "SQLGuardian",
        "Executor",
        "Explainer",
        "Analytics",
      ],
      requires_clarification=False,
      detected_intent=intent.value,
    )

  def _classify_intent(self, query_lower: str) -> IntentType:
    if self._SCHEMA_HINT_RE.search(query_lower):
      return IntentType.SCHEMA_DISCOVERY
    if self._VIS_HINT_RE.search(query_lower):
      return IntentType.VISUALIZATION
    if self._DEBUG_HINT_RE.search(query_lower):
      return IntentType.DEBUGGING
    if self._ADMIN_HINT_RE.search(query_lower):
      return IntentType.ADMIN
    return IntentType.ANALYTICS

  def _detect_ambiguity(self, query_lower: str) -> tuple[list[dict[str, str]], list[str]]:
    ambiguities: list[dict[str, str]] = []
    missing_params: list[str] = []

    token_count = len([t for t in query_lower.split() if t])
    if query_lower in self._VAGUE_QUERIES or token_count <= 1:
      ambiguities.append({
        "type": "vague_query",
        "description": "Query is too short or non-specific to route safely.",
      })

    looks_analytic = bool(self._ANALYTICS_HINT_RE.search(query_lower))
    has_time_range = bool(self._TIME_RANGE_RE.search(query_lower))
    if looks_analytic and not has_time_range:
      ambiguities.append({
        "type": "missing_time_range",
        "description": "Analytical query is missing an explicit time range.",
      })
      missing_params.append("time_range")

    if looks_analytic and token_count <= 3:
      ambiguities.append({
        "type": "ambiguous_metric",
        "description": "Metric or dimension is unclear.",
      })
      missing_params.append("metric")

    # De-duplicate while preserving order
    dedup_params: list[str] = []
    for p in missing_params:
      if p not in dedup_params:
        dedup_params.append(p)

    return ambiguities, dedup_params

