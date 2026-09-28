import os
import json
import logging
from typing import List, Dict, Any, Optional
from openai import OpenAI, APITimeoutError, APIConnectionError, APIStatusError

logger = logging.getLogger(__name__)

MODEL = "google/gemini-2.5-flash"
TIMEOUT = 30.0


def get_openrouter_client() -> OpenAI:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key or api_key == "your_key_here":
        raise ValueError("OPENROUTER_API_KEY is not configured in the environment.")
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        timeout=TIMEOUT,
        max_retries=0,
    )


def _build_explanation_prompt(recommendations: List[Dict[str, Any]]) -> str:
    """Build a prompt that sends ONLY the deterministic recommendation data to Gemini."""
    summary_lines = []
    for i, rec in enumerate(recommendations, 1):
        summary_lines.append(
            f"{i}. Type: {rec['type']}\n"
            f"   Title: {rec['title']}\n"
            f"   Description: {rec['description']}\n"
            f"   Estimated monthly savings: {rec['estimated_monthly_savings']}\n"
            f"   Supporting data: {json.dumps(rec['supporting_data'])}"
        )
    recommendations_text = "\n\n".join(summary_lines)

    return (
        "You are a friendly financial advisor. The user has received the following "
        "data-driven savings recommendations from a financial analysis engine.\n\n"
        "IMPORTANT RULES:\n"
        "- The estimated savings amounts shown below are CALCULATED by the backend. "
        "Do NOT change, modify, override, or invent new savings amounts.\n"
        "- Your role is to explain WHY each recommendation exists and provide practical "
        "advice for how the user could act on it.\n"
        "- Always describe savings as estimates or potential, never guaranteed.\n"
        "- Be concise, practical, and encouraging.\n\n"
        f"RECOMMENDATIONS (already calculated):\n\n{recommendations_text}\n\n"
        "Respond in JSON format:\n"
        "{\n"
        '  "explanations": [\n'
        "    {\n"
        '      "recommendation_index": 1,\n'
        '      "explanation": "Why this recommendation exists and what it means",\n'
        '      "practical_tips": ["tip1", "tip2"]\n'
        "    }\n"
        "  ],\n"
        '  "summary": "Overall encouraging summary of their savings potential"\n'
        "}"
    )


def generate_ai_explanations(
    recommendations: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Send deterministic recommendation data to Gemini for explanations only.

    Returns:
        {"explanations": [...], "summary": str} on success
        {"error": str, "fallback_summary": str} on failure
    """
    if not recommendations:
        return {
            "explanations": [],
            "summary": (
                "We don't have enough spending data yet to identify actionable savings patterns. "
                "Keep tracking your transactions and check back once you have at least 2 months of data."
            ),
        }

    try:
        client = get_openrouter_client()
    except ValueError as e:
        logger.error(f"AI client configuration error: {e}")
        return {
            "error": "AI service not configured.",
            "fallback_summary": _build_fallback_summary(recommendations),
        }

    prompt = _build_explanation_prompt(recommendations)

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=1500,
            extra_headers={
                "HTTP-Referer": "http://localhost:5173",
                "X-Title": "AI Finance Agent",
            },
        )

        content = response.choices[0].message.content.strip()
        parsed = json.loads(content)

        explanations = parsed.get("explanations", [])
        summary = parsed.get("summary", "")

        sanitized = _sanitize_explanations(explanations, recommendations)

        return {"explanations": sanitized, "summary": summary}

    except APITimeoutError:
        logger.error("OpenRouter API timeout during savings explanation generation")
        return {
            "error": "AI service timed out.",
            "fallback_summary": _build_fallback_summary(recommendations),
        }
    except APIConnectionError as e:
        logger.error(f"OpenRouter connection error during savings explanation: {str(e)}")
        return {
            "error": "Could not connect to AI service.",
            "fallback_summary": _build_fallback_summary(recommendations),
        }
    except APIStatusError as e:
        logger.error(f"OpenRouter API error during savings explanation: status={e.status_code}")
        return {
            "error": f"AI service error (HTTP {e.status_code}).",
            "fallback_summary": _build_fallback_summary(recommendations),
        }
    except Exception as e:
        logger.error(f"Unexpected AI error during savings explanation: {str(e)}")
        return {
            "error": "AI explanation generation failed.",
            "fallback_summary": _build_fallback_summary(recommendations),
        }


def _sanitize_explanations(
    explanations: List[Dict[str, Any]],
    recommendations: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Ensure explanations are valid and don't override authoritative savings amounts."""
    sanitized = []
    for exp in explanations:
        idx = exp.get("recommendation_index", 0)
        if not isinstance(idx, int) or idx < 1 or idx > len(recommendations):
            continue
        tips = exp.get("practical_tips", [])
        if not isinstance(tips, list):
            tips = []
        sanitized.append({
            "recommendation_index": idx,
            "explanation": str(exp.get("explanation", "")),
            "practical_tips": [str(t) for t in tips],
        })
    return sanitized


def _build_fallback_summary(recommendations: List[Dict[str, Any]]) -> str:
    """Build a deterministic fallback summary when AI is unavailable."""
    total = sum(
        float(r.get("estimated_monthly_savings", 0)) for r in recommendations
    )
    if total > 0:
        return (
            f"Based on your spending patterns, there are potential savings opportunities "
            f"totaling approximately ${total:.2f}/month. Review the individual recommendations "
            f"for specific actions you can take."
        )
    return (
        "Review the recommendations above for potential savings opportunities "
        "in your spending patterns."
    )
