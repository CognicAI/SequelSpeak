# SequelSpeak - Few-Shot Prompt Templates for Text-to-SQL
# Created by: Sai Prashanth (Prompt Engineer & Research Lead)
# Project: SequelSpeak - RAG-based Natural Language to SQL Interface

import json
from typing import Dict, List, Any
from langchain.prompts import PromptTemplate
from langchain.llms import OpenAI
from langchain.chains import LLMChain
import openai

class SequelSpeakPromptTemplates:
    """
    Few-shot prompt templates for SequelSpeak Text-to-SQL conversion using BASE MODELS.
    Designed for completion-based models (GPT-3 base, CodeGen, StarCoder, etc.)
    Uses completion-style prompting instead of instruction-following.
    """
    
    def __init__(self, model_config: Dict[str, Any]):
        """
        Initialize with base model configuration
        
        Args:
            model_config: {
                'model_name': 'text-davinci-003' or 'code-davinci-002' or custom base model,
                'api_key': 'your-api-key' (if using OpenAI),
                'temperature': 0.1,
                'max_tokens': 200,
                'stop_tokens': [';', '\n\n']  # Important for base models
            }
        """
        self.model_config = model_config
        
        if 'openai' in model_config.get('model_name', '').lower() or 'davinci' in model_config.get('model_name', '').lower():
            openai.api_key = model_config.get('api_key')
            self.llm = OpenAI(
                model_name=model_config.get('model_name', 'text-davinci-003'),
                temperature=model_config.get('temperature', 0.1),
                max_tokens=model_config.get('max_tokens', 200),
                stop=model_config.get('stop_tokens', [';', '\n\n']),
                openai_api_key=model_config.get('api_key')
            )
        else:
            # For other base models (Hugging Face, local models, etc.)
            self.llm = None  # Will be implemented based on specific model requirements
    
    def get_completion_prompt_template(self) -> str:
        """
        Base completion-style prompt template for base models.
        Uses pattern completion rather than instruction following.
        """
        return """# Text-to-SQL Examples - Convert natural language to PostgreSQL queries

Database Schema Context: {schema_context}

Examples of natural language questions and their SQL queries:

Natural Language: Show me all customers from California
SQL: SELECT * FROM customers WHERE state = 'California';

Natural Language: What is the total revenue for each product category?
SQL: SELECT category, SUM(price * quantity) as total_revenue FROM products p JOIN order_items oi ON p.product_id = oi.product_id GROUP BY category;

Natural Language: Find customers who have placed orders in the last 30 days
SQL: SELECT DISTINCT c.* FROM customers c JOIN orders o ON c.customer_id = o.customer_id WHERE o.order_date >= CURRENT_DATE - INTERVAL '30 days';

Natural Language: Show the top 5 best-selling products
SQL: SELECT p.product_name, SUM(oi.quantity) as total_sold FROM products p JOIN order_items oi ON p.product_id = oi.product_id GROUP BY p.product_id, p.product_name ORDER BY total_sold DESC LIMIT 5;

Natural Language: List all orders that haven't been shipped yet
SQL: SELECT * FROM orders WHERE status != 'shipped' AND status != 'delivered';

Natural Language: {natural_question}
SQL:"""

    def get_base_model_examples(self) -> List[Dict[str, Any]]:
        """
        Five comprehensive few-shot examples optimized for base model completion
        Focus on clear pattern recognition rather than instruction following
        """
        examples = [
            {
                # Example 1: Simple filtering pattern
                "natural_question": "Show me all customers from New York",
                "schema_context": """Tables:
customers: customer_id (integer, PRIMARY KEY), customer_name (varchar), email (varchar), city (varchar), state (varchar)""",
                "completion_pattern": "Natural Language: Show me all customers from New York\nSQL: SELECT * FROM customers WHERE state = 'New York';",
                "sql_query": "SELECT * FROM customers WHERE state = 'New York';"
            },
            {
                # Example 2: JOIN with aggregation pattern
                "natural_question": "What is the total order value for each customer?",
                "schema_context": """Tables:
customers: customer_id (integer, PRIMARY KEY), customer_name (varchar), email (varchar)
orders: order_id (integer, PRIMARY KEY), customer_id (integer, FOREIGN KEY), order_date (date), total_amount (decimal)
Relationships: orders.customer_id -> customers.customer_id""",
                "completion_pattern": "Natural Language: What is the total order value for each customer?\nSQL: SELECT c.customer_name, SUM(o.total_amount) as total_value FROM customers c JOIN orders o ON c.customer_id = o.customer_id GROUP BY c.customer_id, c.customer_name;",
                "sql_query": "SELECT c.customer_name, SUM(o.total_amount) as total_value FROM customers c JOIN orders o ON c.customer_id = o.customer_id GROUP BY c.customer_id, c.customer_name;"
            },
            {
                # Example 3: Complex multi-table JOIN pattern
                "natural_question": "Find the top 5 products by total sales in the last 30 days",
                "schema_context": """Tables:
products: product_id (integer, PRIMARY KEY), product_name (varchar), category (varchar), price (decimal)
order_items: item_id (integer, PRIMARY KEY), order_id (integer, FOREIGN KEY), product_id (integer, FOREIGN KEY), quantity (integer)
orders: order_id (integer, PRIMARY KEY), customer_id (integer), order_date (date), status (varchar)
Relationships: order_items.product_id -> products.product_id, order_items.order_id -> orders.order_id""",
                "completion_pattern": "Natural Language: Find the top 5 products by total sales in the last 30 days\nSQL: SELECT p.product_name, SUM(oi.quantity) as total_sold FROM products p JOIN order_items oi ON p.product_id = oi.product_id JOIN orders o ON oi.order_id = o.order_id WHERE o.order_date >= CURRENT_DATE - INTERVAL '30 days' GROUP BY p.product_id, p.product_name ORDER BY total_sold DESC LIMIT 5;",
                "sql_query": "SELECT p.product_name, SUM(oi.quantity) as total_sold FROM products p JOIN order_items oi ON p.product_id = oi.product_id JOIN orders o ON oi.order_id = o.order_id WHERE o.order_date >= CURRENT_DATE - INTERVAL '30 days' GROUP BY p.product_id, p.product_name ORDER BY total_sold DESC LIMIT 5;"
            },
            {
                # Example 4: NOT EXISTS pattern
                "natural_question": "Show customers who have never placed an order",
                "schema_context": """Tables:
customers: customer_id (integer, PRIMARY KEY), customer_name (varchar), email (varchar), registration_date (timestamp)
orders: order_id (integer, PRIMARY KEY), customer_id (integer, FOREIGN KEY), order_date (date), total_amount (decimal)
Relationships: orders.customer_id -> customers.customer_id""",
                "completion_pattern": "Natural Language: Show customers who have never placed an order\nSQL: SELECT * FROM customers c WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.customer_id = c.customer_id);",
                "sql_query": "SELECT * FROM customers c WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.customer_id = c.customer_id);"
            },
            {
                # Example 5: Date filtering with aggregation pattern
                "natural_question": "Which months in 2024 had more than 100 orders?",
                "schema_context": """Tables:
orders: order_id (integer, PRIMARY KEY), customer_id (integer), order_date (date), total_amount (decimal), status (varchar)""",
                "completion_pattern": "Natural Language: Which months in 2024 had more than 100 orders?\nSQL: SELECT TO_CHAR(order_date, 'YYYY-MM') as month, COUNT(*) as order_count FROM orders WHERE EXTRACT(YEAR FROM order_date) = 2024 GROUP BY TO_CHAR(order_date, 'YYYY-MM') HAVING COUNT(*) > 100 ORDER BY month;",
                "sql_query": "SELECT TO_CHAR(order_date, 'YYYY-MM') as month, COUNT(*) as order_count FROM orders WHERE EXTRACT(YEAR FROM order_date) = 2024 GROUP BY TO_CHAR(order_date, 'YYYY-MM') HAVING COUNT(*) > 100 ORDER BY month;"
            }
        ]
        return examples

    def create_completion_prompt(self, natural_question: str, schema_context: str) -> str:
        """
        Creates completion-style prompt for base models
        Base models work better with pattern completion than instructions
        """
        template = self.get_completion_prompt_template()
        
        # Format the schema context for base model consumption
        formatted_schema = self.format_schema_for_completion(schema_context)
        
        prompt = template.format(
            schema_context=formatted_schema,
            natural_question=natural_question
        )
        
        return prompt

    def format_schema_for_completion(self, schema_context: Dict[str, Any]) -> str:
        """
        Formats schema context optimized for base model pattern recognition
        Simpler, more direct format than instruction-based prompts
        """
        if isinstance(schema_context, str):
            return schema_context
            
        formatted_lines = []
        
        # Format tables in a simple, consistent pattern
        if "tables" in schema_context:
            formatted_lines.append("Tables:")
            for table_name, table_info in schema_context["tables"].items():
                columns = []
                for col_name, col_info in table_info["columns"].items():
                    col_desc = f"{col_name} ({col_info['type']}"
                    if col_info.get("primary_key"):
                        col_desc += ", PRIMARY KEY"
                    if col_info.get("foreign_key"):
                        col_desc += ", FOREIGN KEY"
                    col_desc += ")"
                    columns.append(col_desc)
                
                formatted_lines.append(f"{table_name}: {', '.join(columns)}")
        
        # Format relationships simply
        if "relationships" in schema_context and schema_context["relationships"]:
            formatted_lines.append("Relationships:")
            for rel in schema_context["relationships"]:
                formatted_lines.append(f"{rel['from_table']}.{rel['from_column']} -> {rel['to_table']}.{rel['to_column']}")
        
        return "\n".join(formatted_lines)

    def generate_sql_with_base_model(self, natural_question: str, schema_context: Dict[str, Any]) -> str:
        """
        Generate SQL query using base model with completion-style prompting
        Uses pattern completion instead of instruction following
        """
        # Create completion prompt
        completion_prompt = self.create_completion_prompt(natural_question, schema_context)
        
        # Generate completion using base model
        if self.llm:
            response = self.llm(completion_prompt)
            # Extract just the SQL query from the response
            sql_query = self.extract_sql_from_completion(response)
            return sql_query.strip()
        else:
            # For non-OpenAI base models, implement specific generation logic
            return self.generate_with_custom_base_model(completion_prompt)
    
    def extract_sql_from_completion(self, completion: str) -> str:
        """
        Extract SQL query from base model completion
        Base models might generate extra text, so we need to clean it
        """
        # Remove common completion artifacts
        completion = completion.strip()
        
        # If the completion contains a semicolon, take everything up to and including it
        if ';' in completion:
            sql_part = completion.split(';')[0] + ';'
        else:
            sql_part = completion
        
        # Remove any leading/trailing whitespace or newlines
        sql_part = sql_part.strip()
        
        # Basic cleaning - remove any text before SELECT, INSERT, UPDATE, DELETE
        sql_keywords = ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'WITH', 'CREATE']
        for keyword in sql_keywords:
            if keyword in sql_part.upper():
                keyword_index = sql_part.upper().find(keyword)
                sql_part = sql_part[keyword_index:]
                break
        
        return sql_part
    
    def generate_with_custom_base_model(self, prompt: str) -> str:
        """
        Placeholder for custom base model integration
        Implement this method for specific base models (CodeGen, StarCoder, etc.)
        """
        # Example for Hugging Face Transformers integration:
        # from transformers import AutoTokenizer, AutoModelForCausalLM
        # tokenizer = AutoTokenizer.from_pretrained(self.model_config['model_name'])
        # model = AutoModelForCausalLM.from_pretrained(self.model_config['model_name'])
        # inputs = tokenizer(prompt, return_tensors="pt")
        # outputs = model.generate(**inputs, max_length=len(inputs['input_ids'][0]) + 100)
        # response = tokenizer.decode(outputs[0], skip_special_tokens=True)
        # return self.extract_sql_from_completion(response[len(prompt):])
        
        return "-- Custom base model integration needed"

    def test_base_model_prompts(self):
        """
        Test the base model prompt templates with sample queries
        """
        test_cases = [
            {
                "question": "Show me all orders placed in January 2024",
                "schema": {
                    "tables": {
                        "orders": {
                            "columns": {
                                "order_id": {"type": "integer", "primary_key": True},
                                "customer_id": {"type": "integer"},
                                "order_date": {"type": "date"},
                                "total_amount": {"type": "decimal(10,2)"},
                                "status": {"type": "varchar(20)"}
                            }
                        }
                    },
                    "relationships": []
                }
            },
            {
                "question": "Find customers with more than 5 orders",
                "schema": {
                    "tables": {
                        "customers": {
                            "columns": {
                                "customer_id": {"type": "integer", "primary_key": True},
                                "customer_name": {"type": "varchar(100)"},
                                "email": {"type": "varchar(255)"}
                            }
                        },
                        "orders": {
                            "columns": {
                                "order_id": {"type": "integer", "primary_key": True},
                                "customer_id": {"type": "integer", "foreign_key": "customers.customer_id"},
                                "order_date": {"type": "date"}
                            }
                        }
                    },
                    "relationships": [
                        {
                            "from_table": "orders",
                            "from_column": "customer_id",
                            "to_table": "customers",
                            "to_column": "customer_id"
                        }
                    ]
                }
            }
        ]
        
        print("=== SequelSpeak Base Model Prompt Testing ===\n")
        print(f"Model Configuration: {self.model_config}\n")
        
        for i, test_case in enumerate(test_cases, 1):
            print(f"Test Case {i}:")
            print(f"Question: {test_case['question']}")
            
            # Show the completion prompt that would be sent to base model
            completion_prompt = self.create_completion_prompt(
                test_case['question'], 
                test_case['schema']
            )
            
            print("Generated Completion Prompt:")
            print("=" * 50)
            print(completion_prompt)
            print("=" * 50)
            
            try:
                if self.llm:
                    sql_result = self.generate_sql_with_base_model(test_case['question'], test_case['schema'])
                    print(f"Generated SQL: {sql_result}")
                else:
                    print("Base model not configured - showing prompt template only")
            except Exception as e:
                print(f"Error: {str(e)}")
            
            print("\n" + "-" * 80 + "\n")
        ]

    def create_base_model_scoring_rubric(self) -> Dict[str, Any]:
        """
        Creates a specialized scoring rubric for base model evaluation
        Base models require different evaluation criteria than instruction-tuned models
        """
        rubric = {
            "evaluation_criteria": {
                "completion_quality": {
                    "description": "How well the base model completes the SQL pattern",
                    "weight": 0.30,
                    "scoring": {
                        "excellent": {"score": 4, "description": "Perfect pattern completion, no extraneous text"},
                        "good": {"score": 3, "description": "Good completion with minimal cleanup needed"},
                        "fair": {"score": 2, "description": "Reasonable completion but requires significant cleanup"},
                        "poor": {"score": 1, "description": "Poor completion, pattern not recognized"}
                    }
                },
                "sql_syntax_accuracy": {
                    "description": "Generated SQL is syntactically correct",
                    "weight": 0.25,
                    "scoring": {
                        "excellent": {"score": 4, "description": "Perfect PostgreSQL syntax"},
                        "good": {"score": 3, "description": "Minor syntax issues, easily fixable"},
                        "fair": {"score": 2, "description": "Some syntax errors, requires modification"},
                        "poor": {"score": 1, "description": "Major syntax errors, significant issues"}
                    }
                },
                "semantic_understanding": {
                    "description": "Query correctly interprets natural language intent",
                    "weight": 0.25,
                    "scoring": {
                        "excellent": {"score": 4, "description": "Perfect understanding of user intent"},
                        "good": {"score": 3, "description": "Good understanding, minor misinterpretation"},
                        "fair": {"score": 2, "description": "Partial understanding, some elements missed"},
                        "poor": {"score": 1, "description": "Poor understanding, major misinterpretation"}
                    }
                },
                "schema_adherence": {
                    "description": "Correctly uses provided schema elements",
                    "weight": 0.20,
                    "scoring": {
                        "excellent": {"score": 4, "description": "Perfect schema usage, all references correct"},
                        "good": {"score": 3, "description": "Good schema usage, minor issues"},
                        "fair": {"score": 2, "description": "Some incorrect schema references"},
                        "poor": {"score": 1, "description": "Poor schema usage, major errors"}
                    }
                }
            },
            "base_model_specific_metrics": {
                "pattern_recognition": {
                    "description": "How well the model recognizes few-shot patterns",
                    "measurement": "Consistency in following established patterns"
                },
                "completion_cleanliness": {
                    "description": "Amount of cleanup required post-generation",
                    "measurement": "Percentage of responses requiring minimal cleanup"
                },
                "stop_token_effectiveness": {
                    "description": "How well stop tokens prevent over-generation",
                    "measurement": "Percentage of responses stopping at appropriate points"
                }
            },
            "recommended_base_models": {
                "code_focused": [
                    {
                        "name": "code-davinci-002",
                        "provider": "OpenAI",
                        "strengths": "Excellent SQL generation, good pattern following",
                        "considerations": "Requires careful stop tokens"
                    },
                    {
                        "name": "CodeGen-350M-mono",
                        "provider": "Salesforce",
                        "strengths": "Fast, lightweight, good for SQL",
                        "considerations": "May need fine-tuning for complex queries"
                    }
                ],
                "general_purpose": [
                    {
                        "name": "text-davinci-003",
                        "provider": "OpenAI",
                        "strengths": "Strong reasoning, good completion quality",
                        "considerations": "Higher cost, may over-generate"
                    }
                ]
            },
            "testing_methodology": {
                "test_dataset_size": 100,
                "complexity_distribution": {
                    "simple": 0.5,  # Higher proportion for base models
                    "medium": 0.35,
                    "complex": 0.15  # Lower proportion due to base model limitations
                },
                "evaluation_process": [
                    "Generate completion using base model",
                    "Extract SQL query from completion",
                    "Validate SQL syntax",
                    "Execute against test database",
                    "Compare results with expected output",
                    "Score using base model specific criteria"
                ]
            },
            "optimization_strategies": {
                "prompt_engineering": [
                    "Use consistent pattern formatting",
                    "Include clear stop tokens",
                    "Optimize few-shot example ordering",
                    "Minimize instruction text"
                ],
                "post_processing": [
                    "Implement robust SQL extraction",
                    "Add syntax validation layer",
                    "Handle common completion artifacts",
                    "Implement fallback mechanisms"
                ]
            }
        }
        
        return rubric

    def create_model_comparison_framework(self) -> Dict[str, Any]:
        """
        Framework for comparing different base models for SequelSpeak
        """
        return {
            "comparison_criteria": {
                "sql_generation_accuracy": {
                    "weight": 0.35,
                    "description": "Accuracy of generated SQL queries"
                },
                "pattern_following": {
                    "weight": 0.25,
                    "description": "Consistency in following few-shot patterns"
                },
                "inference_speed": {
                    "weight": 0.20,
                    "description": "Time taken for query generation"
                },
                "resource_efficiency": {
                    "weight": 0.10,
                    "description": "Memory and compute requirements"
                },
                "cost_effectiveness": {
                    "weight": 0.10,
                    "description": "Cost per query generation"
                }
            },
            "benchmark_queries": {
                "simple_select": [
                    "Show all customers from California",
                    "Find orders with amount greater than 1000"
                ],
                "joins": [
                    "List customers with their total order amounts",
                    "Show products and their categories"
                ],
                "aggregations": [
                    "Count orders per month",
                    "Average order value by customer"
                ],
                "complex": [
                    "Top 5 customers by revenue in Q1 2024",
                    "Products with no sales in last 30 days"
                ]
            },
            "evaluation_metrics": {
                "exact_match": "Percentage of queries exactly matching expected SQL",
                "execution_match": "Percentage of queries producing correct results",
                "syntax_validity": "Percentage of syntactically valid SQL queries",
                "completion_quality": "Average quality score of completions"
            }
        }

    def save_base_model_templates(self, filepath: str = "base_model_templates.json"):
        """
        Save base model templates and configuration for integration
        """
        template_data = {
            "completion_prompt_template": self.get_completion_prompt_template(),
            "few_shot_examples": self.get_base_model_examples(),
            "base_model_rubric": self.create_base_model_scoring_rubric(),
            "model_comparison_framework": self.create_model_comparison_framework(),
            "recommended_config": {
                "openai_base_models": {
                    "code-davinci-002": {
                        "temperature": 0.1,
                        "max_tokens": 200,
                        "stop": [";", "\n\n", "Natural Language:"],
                        "best_for": "SQL generation, code completion"
                    },
                    "text-davinci-003": {
                        "temperature": 0.1,
                        "max_tokens": 150,
                        "stop": [";", "\n\n", "Natural Language:"],
                        "best_for": "General text completion"
                    }
                },
                "huggingface_models": {
                    "codegen-350M": {
                        "max_length": 200,
                        "temperature": 0.1,
                        "do_sample": True,
                        "pad_token_id": 50256
                    },
                    "starcoder-base": {
                        "max_new_tokens": 150,
                        "temperature": 0.1,
                        "do_sample": True
                    }
                }
            },
            "integration_notes": {
                "prompt_structure": "Uses completion-style prompting instead of instruction-following",
                "stop_tokens": "Critical for preventing over-generation",
                "post_processing": "Requires SQL extraction from completion",
                "schema_format": "Simplified format optimized for pattern recognition"
            },
            "metadata": {
                "created_by": "Sai Prashanth",
                "project": "SequelSpeak",
                "version": "1.0_base_model",
                "target_models": ["code-davinci-002", "CodeGen", "StarCoder"],
                "integration_ready": True,
                "optimized_for": "completion_based_models"
            }
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(template_data, f, indent=2, ensure_ascii=False)
        
        print(f"Base model templates saved to {filepath}")

    def generate_model_config_examples(self) -> Dict[str, Dict]:
        """
        Generate example configurations for different base models
        """
        return {
            "openai_code_davinci": {
                "model_name": "code-davinci-002",
                "api_key": "your-openai-api-key",
                "temperature": 0.1,
                "max_tokens": 200,
                "stop_tokens": [";", "\n\n", "Natural Language:"]
            },
            "huggingface_codegen": {
                "model_name": "Salesforce/codegen-350M-mono",
                "temperature": 0.1,
                "max_tokens": 200,
                "stop_tokens": [";", "\n\n"],
                "device": "cuda"  # or "cpu"
            },
            "local_starcoder": {
                "model_name": "bigcode/starcoder-base",
                "temperature": 0.1,
                "max_new_tokens": 150,
                "stop_tokens": [";", "\n\n", "Natural Language:"],
                "device": "cuda"
            }
        }


# Example usage for base models
if __name__ == "__main__":
    print("=== SequelSpeak Base Model Prompt Templates ===\n")
    
    # Example configurations for different base models
    model_configs = {
        "openai_base": {
            "model_name": "code-davinci-002",
            "api_key": "your-openai-api-key-here",
            "temperature": 0.1,
            "max_tokens": 200,
            "stop_tokens": [";", "\n\n", "Natural Language:"]
        },
        "codegen_base": {
            "model_name": "Salesforce/codegen-350M-mono",
            "temperature": 0.1,
            "max_tokens": 200,
            "stop_tokens": [";", "\n\n"]
        }
    }
    
    # Initialize with OpenAI base model config
    prompt_system = SequelSpeakPromptTemplates(model_configs["openai_base"])
    
    # Test base model prompts
    prompt_system.test_base_model_prompts()
    
    # Save base model templates
    prompt_system.save_base_model_templates("sequelspeak_base_model_templates.json")
    
    # Display configuration examples
    configs = prompt_system.generate_model_config_examples()
    print("\n=== Model Configuration Examples ===")
    for model_type, config in configs.items():
        print(f"\n{model_type.upper()}:")
        for key, value in config.items():
            print(f"  {key}: {value}")
    
    print("""
=== Base Model Integration Guide for SequelSpeak ===

KEY DIFFERENCES FROM INSTRUCTION-TUNED MODELS:
1. Uses completion-style prompting instead of instructions
2. Relies on pattern recognition from few-shot examples
3. Requires proper stop tokens to prevent over-generation
4. Needs post-processing to extract clean SQL from completions
5. Optimized for code-focused base models (code-davinci-002, CodeGen, StarCoder)

RECOMMENDED BASE MODELS:
1. code-davinci-002 (OpenAI) - Best overall SQL generation
2. CodeGen-350M-mono (Salesforce) - Fast, lightweight, good for SQL
3. StarCoder-base (BigCode) - Strong code understanding
4. text-davinci-003 (OpenAI) - General purpose, high quality

PROMPT ENGINEERING OPTIMIZATIONS:
- Consistent pattern formatting across examples
- Clear stop tokens to prevent over-generation
- Simplified schema representation
- Direct completion format (no instructions)
- Optimized few-shot example ordering

INTEGRATION NOTES:
- Temperature: 0.1 (low for consistent SQL generation)
- Max tokens: 150-200 (sufficient for most SQL queries)
- Stop tokens: [";", "\\n\\n", "Natural Language:"]
- Post-processing: Extract SQL from completion text
- Fallback: Handle incomplete or malformed completions

The templates are ready for integration with your RAG pipeline!
    """)

