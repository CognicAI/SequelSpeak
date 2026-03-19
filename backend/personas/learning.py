"""
Learning Persona

Single responsibility:
- Capture feedback, corrections, and update retrieval signals

SRS source:
- Overall flow + FR-115 to FR-121

Input contract:
{
  "query_id": "string",
  "feedback_type": "string",
  "corrected_sql": "string (optional)",
  "rating": "number (1-5)"
}

Output contract:
{
  "feedback_stored": "boolean",
  "embeddings_updated": "boolean",
  "retrieval_signal_updated": "boolean"
}
"""
