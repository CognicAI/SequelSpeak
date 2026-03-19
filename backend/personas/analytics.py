"""
Analytics Persona

Single responsibility:
- Visualization decisioning (chart type, bucketing, BI formatting)

SRS source:
- Persona contracts: Section "Persona Input/Output Contracts"
- FR-108 to FR-114

Input contract:
{
  "query_results": "object",
  "original_intent": "string",
  "data_characteristics": "object"
}

Output contract:
{
  "visualization_required": "boolean",
  "chart_type": "string",
  "time_bucket": "string",
  "bi_format": "object"
}
"""
