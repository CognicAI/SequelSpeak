"""
SQLGuardian Persona

Single responsibility:
- Validation and security gate before execution

SRS source:
- Persona contracts: Section "Persona Input/Output Contracts"
- FR-46 to FR-59

Input contract:
{
  "sql": "string",
  "schema_metadata": "object",
  "execution_context": "object"
}

Output contract:
{
  "is_valid": "boolean",
  "security_passed": "boolean",
  "errors": ["string"],
  "suggested_fixes": ["string (optional)"]
}
"""
