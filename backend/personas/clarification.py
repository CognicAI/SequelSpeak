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
