import os
import json
import logging
from typing import List, Dict, Any
from openai import OpenAI, APITimeoutError, APIConnectionError, APIStatusError

logger = logging.getLogger(__name__)

def get_openrouter_client() -> OpenAI:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key or api_key == "your_key_here":
        raise ValueError("OPENROUTER_API_KEY is not configured in the environment.")
    
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        timeout=60.0,
        max_retries=0
    )

def categorize_transactions(transactions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not transactions:
        return []
        
    client = get_openrouter_client()
    categorized_results = []
    
    system_prompt = (
        "You are an AI financial assistant that analyzes bank transaction descriptions and categorizes them.\n"
        "You will receive a JSON list of transaction objects, each containing 'description', 'amount', and 'transaction_type'.\n"
        "Your task is to assign the most appropriate category and subcategory, and determine if it is recurring.\n\n"
        "Valid Categories:\n"
        "- Food & Dining\n"
        "- Groceries\n"
        "- Shopping\n"
        "- Transport\n"
        "- Bills & Utilities\n"
        "- Subscriptions\n"
        "- Entertainment\n"
        "- Healthcare\n"
        "- Transfers\n"
        "- Salary/Income\n"
        "- ATM/Cash\n"
        "- Other\n\n"
        "Rules:\n"
        "1. Return a JSON object with a single key 'transactions' containing a list of categorized transaction objects in the EXACT same order as the input list.\n"
        "2. Do NOT add any extra commentary, markdown blocks, or text. Return ONLY the raw JSON object.\n"
        "3. Each object in the 'transactions' list must have these exact keys:\n"
        "   - 'category': Must be one of the valid categories list above.\n"
        "   - 'subcategory': A string naming a specific subcategory (e.g., 'Cafe', 'Gas', 'Rent', 'OTT Streaming', 'Pharmacy', 'Grocery Store'), or null.\n"
        "   - 'is_recurring': A boolean (true or false). Set to true if the transaction is a recurring monthly bill, salary, subscription (like NETFLIX, SPOTIFY, YOUTUBE, GYM, etc.), or rent.\n"
    )
    
    # Process in batches of 25 to respect token/rate limits
    batch_size = 25
    for i in range(0, len(transactions), batch_size):
        batch = transactions[i:i + batch_size]
        
        # Prepare input payload for OpenRouter
        input_data = []
        for tx in batch:
            input_data.append({
                'description': tx['description'],
                'amount': tx['amount'],
                'transaction_type': tx['transaction_type']
            })
            
        user_prompt = f"Categorize this batch of transactions:\n{json.dumps(input_data, indent=2)}"
        
        try:
            response = client.chat.completions.create(
                model="google/gemini-2.5-flash",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
                max_tokens=1500,
                extra_headers={
                    "HTTP-Referer": "http://localhost:5173",
                    "X-Title": "AI Finance Agent"
                }
            )
        except APITimeoutError:
            logger.error("OpenRouter API timeout during categorization")
            raise RuntimeError("Transaction categorization timed out. Please try again.")
        except APIConnectionError as e:
            logger.error(f"OpenRouter connection error during categorization: {str(e)}")
            raise RuntimeError("Could not connect to AI service for categorization.")
        except APIStatusError as e:
            logger.error(f"OpenRouter API error during categorization: status={e.status_code}")
            raise RuntimeError(f"AI service returned an error during categorization (HTTP {e.status_code}).")
        except Exception as e:
            logger.error(f"OpenRouter API failure during categorization: {str(e)}")
            raise RuntimeError(f"Failed to categorize transactions via AI API: {str(e)}")
        
        # Process response
        content_str = response.choices[0].message.content.strip()
        batch_results_data = json.loads(content_str)
        
        # Extract transactions list
        if isinstance(batch_results_data, dict):
            batch_results = batch_results_data.get("transactions", [])
        elif isinstance(batch_results_data, list):
            batch_results = batch_results_data
        else:
            batch_results = []
        
        # Basic validation of response format and length
        if not isinstance(batch_results, list) or len(batch_results) != len(batch):
            logger.error(f"Invalid response length or format from OpenRouter. Expected {len(batch)} items, got {type(batch_results)}")
            # Fallback list of default items
            batch_results = [{
                'category': 'Other',
                'subcategory': None,
                'is_recurring': False
            } for _ in batch]
            
        categorized_results.extend(batch_results)
            
    # Combine original transaction data with category results
    final_transactions = []
    for tx, cat in zip(transactions, categorized_results):
        final_tx = tx.copy()
        final_tx['category'] = cat.get('category', 'Other')
        final_tx['subcategory'] = cat.get('subcategory', None)
        final_tx['is_recurring'] = cat.get('is_recurring', False)
        final_transactions.append(final_tx)
        
    return final_transactions
