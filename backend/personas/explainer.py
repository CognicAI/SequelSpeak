"""
Explainer Persona

Single responsibility:
- Explain SQL and results in plain language

SRS source:
- Overall flow + FR-68 to FR-72

Input contract:
{
  "sql": "string",
  "results": "object",
  "original_query": "string"
}

Output contract:
{
  "explanation": "string",
  "sql_breakdown": ["string"],
  "business_context": "string"
}
"""
