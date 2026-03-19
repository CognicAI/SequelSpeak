"""
ContextRetriever Persona

Single responsibility:
- Semantic retrieval of similar queries, examples, schema snippets

SRS source:
- Overall flow + FR-32 to FR-37
- Persona contracts section intent

Input contract:
{
  "nl_query": "string",
  "schema_context": "object",
  "top_k": "number (optional, default: 5)"
}

Output contract:
{
  "similar_queries": [{"query": "string", "sql": "string", "similarity": "number"}],
  "example_sqls": ["string"],
  "schema_snippets": ["string"],
  "relevance_scores": ["number"]
}
"""
