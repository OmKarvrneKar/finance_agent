import os
import json
import logging
from PIL import Image, UnidentifiedImageError
from datetime import datetime, date
from openai import OpenAI, APITimeoutError, APIConnectionError, APIStatusError
import pytesseract

logger = logging.getLogger(__name__)

# Config flag for OCR approach
OCR_PROVIDER = os.getenv("OCR_PROVIDER", "tesseract") # options: "tesseract" or "gemini_vision"

def get_openrouter_client() -> OpenAI:
    """Lazy client creation to avoid import-time failures when API key is not set."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key or api_key == "your_key_here":
        raise ValueError("OPENROUTER_API_KEY is not configured in the environment.")
    
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        timeout=30.0,
        max_retries=0
    )

def extract_receipt_text(image_path: str) -> str:
    """Extract raw text from an image using Tesseract OCR."""
    if OCR_PROVIDER == "gemini_vision":
        # Note: A real gemini_vision implementation would send the image bytes directly to the vision model
        # instead of doing local OCR. For this demo, we use tesseract as the default.
        pass
        
    try:
        image = Image.open(image_path)
        text = pytesseract.image_to_string(image)
        return text
    except UnidentifiedImageError:
        raise ValueError("Invalid or unreadable image file.")
    except Exception as e:
        logger.error(f"OCR Error: {e}")
        # Could be TesseractNotFound error if tesseract is not installed on the system
        raise ValueError(f"Failed to process image with OCR: {e}")

def parse_receipt_with_ai(raw_text: str) -> dict:
    """Send OCR text to Gemini to extract structured receipt data."""
    if not raw_text or not raw_text.strip():
        return {"needs_review": True, "error": "No text extracted from image."}
    
    try:
        client = get_openrouter_client()
    except ValueError as e:
        logger.error(f"AI client configuration error: {e}")
        return {"needs_review": True, "error": "AI service not configured."}
        
    prompt = f"""
    You are a precise data extraction assistant. I am providing you with the raw OCR text extracted from a receipt.
    Your task is to extract the following information and return ONLY a valid JSON object:
    - "merchant": The name of the store or merchant (string, null if unknown)
    - "date": The date of the transaction in YYYY-MM-DD format (string, null if unknown)
    - "amount": The final total amount as a float (number, null if unknown)
    - "category": A best-guess category for this expense (e.g., Food & Dining, Transport, Shopping) (string, null if unknown)
    
    If the text is messy and you cannot confidently determine the merchant or the final total amount, set "needs_review" to true. 
    Otherwise, set "needs_review" to false.

    Raw OCR Text:
    {raw_text}
    
    Respond ONLY with JSON. Example:
    {{
      "merchant": "Starbucks",
      "date": "2026-07-10",
      "amount": 5.40,
      "category": "Food & Dining",
      "needs_review": false
    }}
    """
    
    try:
        response = client.chat.completions.create(
            model="google/gemini-2.5-flash",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content
        parsed = json.loads(content)
        
        # Ensure we have a date
        dt = parsed.get("date")
        if not dt:
            dt = datetime.today().strftime("%Y-%m-%d")
            
        return {
            "merchant": parsed.get("merchant"),
            "date": dt,
            "amount": parsed.get("amount"),
            "category": parsed.get("category"),
            "needs_review": parsed.get("needs_review", True)
        }
    except APITimeoutError:
        logger.error("AI service timeout during receipt parsing")
        return {"needs_review": True, "error": "AI service timed out."}
    except APIConnectionError as e:
        logger.error(f"AI service connection error during receipt parsing: {e}")
        return {"needs_review": True, "error": "Could not connect to AI service."}
    except APIStatusError as e:
        logger.error(f"AI service error during receipt parsing: status={e.status_code}")
        return {"needs_review": True, "error": f"AI service error (HTTP {e.status_code})."}
    except Exception as e:
        logger.error(f"AI Parse Error: {e}")
        return {"needs_review": True, "error": "AI extraction failed."}
