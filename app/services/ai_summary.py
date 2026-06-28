import json
import logging
from datetime import datetime

import google.generativeai as genai

from app.core.config import settings
from app.core.exceptions import AIServiceException
from app.models.schemas import AISummaryResponse

logger = logging.getLogger(__name__)

# --- Gemini setup ---
genai.configure(api_key=settings.GOOGLE_API_KEY)
_model = genai.GenerativeModel("gemini-2.5-flash")

# --- Prompt versioning ---
# Keep prompts as named constants so changes are traceable in git history.
PROMPT_V1 = """
You are an expert Logistics Communication Assistant.
Your job is to translate pre-processed shipment data into a clear, empathetic customer update.

SHIPMENT CONTEXT:
- Shipment ID      : {shipment_id}
- Overall Status   : {overall_status}
- Route            : {origin} → {destination}
- Expected Delivery: {estimated_delivery}
- Last Known Stop  : {last_location} ({last_description})
- Total Stops So Far: {total_stops}
- Exception Events : {exception_events}

INSTRUCTIONS:
- Write a friendly, professional summary in under 3 sentences.
- If exception_events is non-empty (WTH = weather delay, HLD = documentation hold), explain empathetically.
- Always mention the last known location.
- Set is_exception to true only if exception_events is non-empty.
- If is_exception is true, suggest a concrete action for the customer in suggested_action.
- If no exceptions, set suggested_action to null.

RESPOND ONLY WITH THIS JSON — no preamble, no markdown:
{{
    "summary_text": "string",
    "is_exception": boolean,
    "suggested_action": "string or null"
}}
"""


async def generate_ai_summary(shipment_context: dict) -> AISummaryResponse:
    """
    Calls Gemini with pre-processed shipment context and returns a structured AISummaryResponse.
    Raises AIServiceException on failure.
    """
    prompt = PROMPT_V1.format(
        shipment_id=shipment_context["shipment_id"],
        overall_status=shipment_context["overall_status"],
        origin=shipment_context["origin"],
        destination=shipment_context["destination"],
        estimated_delivery=shipment_context["estimated_delivery"],
        last_location=shipment_context["last_location"],
        last_description=shipment_context["last_description"],
        total_stops=shipment_context["total_stops"],
        exception_events=shipment_context["exception_events"] or "None",
    )

    try:
        response = await _model.generate_content_async(
            prompt,
            generation_config={"response_mime_type": "application/json"},
        )
        ai_raw = json.loads(response.text)
        logger.info(f"Gemini response for {shipment_context['shipment_id']}: {ai_raw}")
    except json.JSONDecodeError as e:
        logger.error(f"Gemini returned non-JSON for {shipment_context['shipment_id']}: {e}")
        raise AIServiceException("AI service returned an unreadable response.")
    except Exception as e:
        logger.error(f"Gemini call failed for {shipment_context['shipment_id']}: {e}")
        raise AIServiceException(f"AI service unavailable: {str(e)}")

    # Parse estimated_delivery — may be a string ("2026-04-28") or datetime
    eta = shipment_context["estimated_delivery"]
    if isinstance(eta, str):
        eta = datetime.fromisoformat(eta)

    return AISummaryResponse(
        shipment_id=shipment_context["shipment_id"],
        summary=ai_raw.get("summary_text", ""),
        estimated_delivery=eta,
        is_exception=ai_raw.get("is_exception", False),
        suggested_actions=ai_raw.get("suggested_action"),
        cached=False,
    )
