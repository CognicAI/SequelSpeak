"""
SchemaExpert Persona

Single responsibility:
- Schema scoping, relevant tables/columns, join paths

SRS source:
- Persona contracts: Section "Persona Input/Output Contracts"
- FR-21 to FR-31

Input contract:
{
  "intent": "string",
  "database_id": "string"
}

Output contract:
{
  "relevant_tables": ["string"],
  "relevant_columns": [{"table": "string", "column": "string", "type": "string"}],
  "join_paths": [{"from": "string", "to": "string", "via": "string"}],
  "scope_confidence": "number"
}
"""
