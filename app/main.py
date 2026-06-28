import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.core.exceptions import ShipmentNotFoundException, AIServiceException
from app.core.cache import get_cached_summary, set_cached_summary
from app.models.schemas import ShipmentInputFormat, AISummaryResponse
from app.services.tracking_shipment import get_shipment_by_id, extract_shipment_context
from app.services.ai_summary import generate_ai_summary

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# --- Rate limiter (10 requests/minute per IP) ---
limiter = Limiter(key_func=get_remote_address, default_limits=["10/minute"])


# --- Lifespan: startup/shutdown events ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Logistics Assistant starting up...")
    yield
    logger.info("Logistics Assistant shutting down.")


# --- App ---
app = FastAPI(
    title=settings.APP_TITLE,
    description="AI-powered shipment tracking with Redis caching and Gemini summaries.",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# --- Custom exception handlers ---
@app.exception_handler(ShipmentNotFoundException)
async def shipment_not_found_handler(request: Request, exc: ShipmentNotFoundException):
    return JSONResponse(
        status_code=404,
        content={"detail": f"Shipment '{exc.shipment_id}' was not found in our records."},
    )


@app.exception_handler(AIServiceException)
async def ai_service_handler(request: Request, exc: AIServiceException):
    return JSONResponse(
        status_code=503,
        content={"detail": "The AI assistant is temporarily unavailable. Please try again later."},
    )


# --- Routes ---
@app.get("/", tags=["Health"])
async def read_root():
    return {
        "service": settings.APP_TITLE,
        "version": settings.APP_VERSION,
        "status": "healthy",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.post("/summarize", response_model=AISummaryResponse, tags=["Shipment"])
@limiter.limit("10/minute")
async def get_shipment_summary(request: Request, body: ShipmentInputFormat):
    """
    Returns an AI-generated summary for a given shipment ID.

    - Checks Redis cache first (10-minute TTL)
    - On cache miss: fetches shipment, pre-processes context, calls Gemini
    - Stores fresh result in Redis for subsequent requests
    """
    shipment_id = body.shipment_id
    logger.info(f"Received summarize request for shipment: {shipment_id}")

    # 1. Cache check
    cached = await get_cached_summary(shipment_id)
    if cached:
        cached["cached"] = True
        return AISummaryResponse(**cached)

    # 2. Fetch & validate shipment (raises ShipmentNotFoundException if missing)
    shipment = get_shipment_by_id(shipment_id)

    # 3. Pre-process into lean context (Python does the heavy lifting, not the LLM)
    context = extract_shipment_context(shipment)

    # 4. Call Gemini (raises AIServiceException on failure)
    summary = await generate_ai_summary(context)

    # 5. Store in cache (non-fatal if Redis is down)
    await set_cached_summary(shipment_id, summary.model_dump())

    return summary
