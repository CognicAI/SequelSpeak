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
