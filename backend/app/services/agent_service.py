import os
import json
import logging
import datetime
from typing import Dict, Any, List
from openai import OpenAI
from app.database.db import SessionLocal
import app.services.agent_tools as agent_tools
import app.services.forecasting as forecasting
import app.services.budgets as budgets
import app.services.anomalies as anomalies

logger = logging.getLogger(__name__)

def get_openrouter_client() -> OpenAI:
    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "your_key_here":
        raise ValueError("Neither OPENROUTER_API_KEY nor GEMINI_API_KEY is configured in the environment.")
    
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key
    )

# Map names to Python functions
TOOL_MAP = {
    "filter_transactions": agent_tools.filter_transactions,
    "sum_by_category": agent_tools.sum_by_category,
    "compare_periods": agent_tools.compare_periods,
    "find_recurring_transactions": agent_tools.find_recurring_transactions,
    "get_total_spent": agent_tools.get_total_spent,
    "get_total_income": agent_tools.get_total_income,
    "forecast_month_end_spend": forecasting.forecast_month_end_spend,
    "generate_overspend_alerts": forecasting.generate_overspend_alerts,
    "get_budget_status": budgets.get_budget_status,
    "simulate_what_if": budgets.simulate_what_if,
    "generate_anomaly_report": anomalies.generate_anomaly_report
}

# Define OpenAI-style tool declarations
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "filter_transactions",
            "description": (
                "Filter and retrieve transactions in the database based on category, date range, or transaction type. "
                "Returns a list of matching transactions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Filter by category name (e.g. Food & Dining, Groceries, Shopping, Transport, Bills & Utilities, Subscriptions, Entertainment, Healthcare, Transfers, Salary/Income, ATM/Cash, Other). Case-insensitive."
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Start date for filtering in YYYY-MM-DD format."
                    },
                    "end_date": {
                        "type": "string",
                        "description": "End date for filtering in YYYY-MM-DD format."
                    },
                    "transaction_type": {
                        "type": "string",
                        "enum": ["debit", "credit"],
                        "description": "Filter by transaction type: 'debit' (spending) or 'credit' (income)."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "sum_by_category",
            "description": "Compute total spending (debits) grouped by category for the given date range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {
                        "type": "string",
                        "description": "Start date in YYYY-MM-DD format."
                    },
                    "end_date": {
                        "type": "string",
                        "description": "End date in YYYY-MM-DD format."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compare_periods",
            "description": "Compare spending in a specific category between two time periods, returning difference and percent change.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "The category name to compare."
                    },
                    "period1_start": {
                        "type": "string",
                        "description": "Start date of the first period (YYYY-MM-DD)."
                    },
                    "period1_end": {
                        "type": "string",
                        "description": "End date of the first period (YYYY-MM-DD)."
                    },
                    "period2_start": {
                        "type": "string",
                        "description": "Start date of the second period (YYYY-MM-DD)."
                    },
                    "period2_end": {
                        "type": "string",
                        "description": "End date of the second period (YYYY-MM-DD)."
                    }
                },
                "required": ["category", "period1_start", "period1_end", "period2_start", "period2_end"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_recurring_transactions",
            "description": "Find recurring transactions (subscriptions, bills, salary, recurring transfers). Returns details on frequency and estimated monthly cost.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_total_spent",
            "description": "Calculate total spending (debits) in the given date range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {
                        "type": "string",
                        "description": "Start date in YYYY-MM-DD format."
                    },
                    "end_date": {
                        "type": "string",
                        "description": "End date in YYYY-MM-DD format."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_total_income",
            "description": "Calculate total income (credits) in the given date range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {
                        "type": "string",
                        "description": "Start date in YYYY-MM-DD format."
                    },
                    "end_date": {
                        "type": "string",
                        "description": "End date in YYYY-MM-DD format."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "forecast_month_end_spend",
            "description": "Forecast the total spend for the entire month (overall or for a specific category) based on the daily run rate so far.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "The specific category to forecast (e.g. Food & Dining). Leave empty for overall forecast."
                    },
                    "month": {
                        "type": "string",
                        "description": "The month to forecast in YYYY-MM format. Defaults to current month."
                    }
                },
                "required": ["month"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_overspend_alerts",
            "description": "Generate proactive alerts for categories where forecasted spend exceeds the historical average by a threshold.",
            "parameters": {
                "type": "object",
                "properties": {
                    "month": {
                        "type": "string",
                        "description": "The month to check in YYYY-MM format. Defaults to current month."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_budget_status",
            "description": "Get the status of all budget goals, showing how much has been spent versus the cap and pacing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "month": {
                        "type": "string",
                        "description": "The month to check in YYYY-MM format. Defaults to current month."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "simulate_what_if",
            "description": "Simulate a hypothetical scenario of changing spending behavior to see long-term impact on savings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "The specific category to simulate changes for (e.g. Food)."
                    },
                    "percent_change": {
                        "type": "number",
                        "description": "Percentage change in spending. Negative to cut spending (e.g. -20 for a 20% cut), positive for increasing."
                    },
                    "months": {
                        "type": "integer",
                        "description": "Number of months to simulate over. Default 12."
                    },
                    "goal_name": {
                        "type": "string",
                        "description": "Optional name of a savings goal to see how fast it would be reached."
                    }
                },
                "required": ["category", "percent_change"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_anomaly_report",
            "description": "Detects unusual spending activity such as recurring bill price jumps, duplicate charges, or unfamiliar large expenses.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]

def process_query(user_question: str) -> Dict[str, Any]:
    client = get_openrouter_client()
    db = SessionLocal()
    
    current_date = datetime.date.today()
    system_prompt = (
        "You are a friendly and expert financial assistant. Your goal is to answer questions about the user's finances (spending, income, transactions, budgets, subscriptions).\n"
        "You have access to several database querying tools. Always use these tools to fetch data from the database to answer questions. Do not make up answers.\n"
        "When explaining results, follow these rules:\n"
        "1. Always output currency amounts in Indian Rupees (e.g. ₹250 or Rs. 250).\n"
        "2. Explain your reasoning and summarize the data clearly in a friendly, conversational tone.\n"
        "3. Highlight trends, percentage changes, or unusual spending where relevant.\n"
        "4. If a tool returns no data, explain that clearly and ask if they would like to check a different date range or category.\n\n"
        f"Context: The current local date is {current_date.isoformat()}. "
        f"Therefore, 'this month' refers to month {current_date.strftime('%B %Y')}, "
        f"and 'last month' refers to the previous calendar month. "
        "Use date ranges matching this calendar context when calling tools."
    )
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_question}
    ]
    
    steps = []
    max_iterations = 5
    
    try:
        for i in range(max_iterations):
            response = client.chat.completions.create(
                model="google/gemini-2.5-flash",
                messages=messages,
                tools=TOOLS,
                max_tokens=1500,
                extra_headers={
                    "HTTP-Referer": "http://localhost:5173",
                    "X-Title": "AI Finance Agent"
                }
            )
            
            choice = response.choices[0]
            message = choice.message
            tool_calls = message.tool_calls
            
            # If no tool calls, we have our final text answer
            if not tool_calls:
                return {
                    "answer": message.content or "No response received.",
                    "steps": steps
                }
                
            # Construct assistant message dict to append to history
            assistant_msg = {
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in tool_calls
                ]
            }
            messages.append(assistant_msg)
            
            # Process each requested tool call
            for tool_call in tool_calls:
                name = tool_call.function.name
                args_str = tool_call.function.arguments
                
                # Parse arguments
                try:
                    args = json.loads(args_str) if args_str else {}
                except Exception as e:
                    logger.error(f"Failed to parse tool call arguments: {args_str}. Error: {str(e)}")
                    args = {}
                    
                # Execute tool
                if name in TOOL_MAP:
                    try:
                        result = TOOL_MAP[name](db=db, **args)
                    except Exception as e:
                        logger.error(f"Error executing tool {name} with args {args}: {str(e)}")
                        result = {"error": f"Failed to execute tool {name}: {str(e)}"}
                else:
                    logger.error(f"Requested unknown tool: {name}")
                    result = {"error": f"Unknown tool name: {name}"}
                    
                # Log step trace
                steps.append({
                    "tool": name,
                    "args": args,
                    "result": result
                })
                
                # Append tool response message to history
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": name,
                    "content": json.dumps(result)
                })
                
        # If loop ended without returning (exceeded max iterations)
        return {
            "answer": "I reached my reasoning iteration limit. Here is the last trace of my planning.",
            "steps": steps
        }
        
    finally:
        db.close()
