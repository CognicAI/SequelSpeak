"""
Executor Persona

Single responsibility:
- Execute validated SQL with timeout and row safety constraints

SRS source:
- Overall flow + FR-60 to FR-67

Input contract:
{
  "validated_sql": "string",
  "database_connection": "object",
  "timeout": "number (default: 30 seconds)"
}

Output contract:
{
  "results": [{"column": "value"}],
  "row_count": "number",
  "execution_time": "number",
  "status": "string"
}
"""
