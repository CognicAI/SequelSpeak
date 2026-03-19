"""
SQLWriter Persona

Single responsibility:
- SQL generation only
- No validation, no execution

SRS source:
- Persona contracts: Section "Persona Input/Output Contracts"
- FR-38 to FR-45

Input contract:
{
  "nl_query": "string",
  "schema_context": "object",
  "examples": ["string"],
  "resolved_params": "object"
}

Output contract:
{
  "generated_sql": "string",
  "confidence": "number",
  "assumptions_made": ["string"]
}
"""
