"""
Full test suite for Logistics Assistant.
Covers: service layer unit tests + API integration tests (no real AI or Redis calls).
Run with: pytest tests/ -v
"""
import pytest
from unittest.mock import patch, AsyncMock
from datetime import datetime

from httpx import AsyncClient, ASGITransport

from app.main import app
from app.services import ai_summary
from app.models.schemas import AISummaryResponse
from app.services.tracking_shipment import get_shipment_by_id, extract_shipment_context
from app.core.exceptions import ShipmentNotFoundException

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SAMPLE_SHIPMENT = {
    "shipment_id": "TRK99999LOG",
    "overall_status": "In Transit",
    "origin": "Shanghai, CN",
    "destination": "New York, NY",
    "estimated_delivery": "2026-05-10",
    "tracking_history": [
        {"timestamp": "2026-05-01T07:00:00Z", "location": "Shanghai, CN",
         "status_code": "DEP", "description": "Departed Facility", "carrier": "TestCarrier"},
        {"timestamp": "2026-05-02T10:00:00Z", "location": "Los Angeles, CA",
         "status_code": "WTH", "description": "Delay - Weather Conditions", "carrier": "TestCarrier"},
    ],
}

MOCK_DATA = [SAMPLE_SHIPMENT]

# Mock AI response — uses correct field name (estimated_delivery, not estimated_deliver)
MOCK_AI_RESPONSE = AISummaryResponse(
    shipment_id="TRK86742LOG",
    summary="Your package is safely in transit through Memphis.",
    estimated_delivery=datetime(2026, 3, 25),   # fixed: was estimated_deliver
    is_exception=False,
    suggested_actions=None,
    cached=False,
)


# ---------------------------------------------------------------------------
# Service layer: get_shipment_by_id
# ---------------------------------------------------------------------------

async def test_get_shipment_found():
    with patch("app.services.tracking_shipment.load_logistics_data", return_value=MOCK_DATA):
        result = get_shipment_by_id("TRK99999LOG")
        assert result["shipment_id"] == "TRK99999LOG"


async def test_get_shipment_not_found():
    with patch("app.services.tracking_shipment.load_logistics_data", return_value=MOCK_DATA):
        with pytest.raises(ShipmentNotFoundException) as exc_info:
            get_shipment_by_id("INVALID123")
        assert "INVALID123" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Service layer: extract_shipment_context
# ---------------------------------------------------------------------------

async def test_extract_context_basic_fields():
    ctx = extract_shipment_context(SAMPLE_SHIPMENT)
    assert ctx["shipment_id"] == "TRK99999LOG"
    assert ctx["origin"] == "Shanghai, CN"
    assert ctx["destination"] == "New York, NY"
    assert ctx["total_stops"] == 2


async def test_extract_context_last_location():
    ctx = extract_shipment_context(SAMPLE_SHIPMENT)
    assert ctx["last_location"] == "Los Angeles, CA"
    assert ctx["last_status_code"] == "WTH"


async def test_extract_context_exception_events_detected():
    ctx = extract_shipment_context(SAMPLE_SHIPMENT)
    assert len(ctx["exception_events"]) == 1
    assert ctx["exception_events"][0]["status_code"] == "WTH"


async def test_extract_context_no_exceptions():
    clean_shipment = {**SAMPLE_SHIPMENT, "tracking_history": [
        {"timestamp": "2026-05-01T07:00:00Z", "location": "Shanghai, CN",
         "status_code": "DEP", "description": "Departed Facility", "carrier": "TestCarrier"},
    ]}
    ctx = extract_shipment_context(clean_shipment)
    assert ctx["exception_events"] == []


async def test_extract_context_empty_history():
    empty_shipment = {**SAMPLE_SHIPMENT, "tracking_history": []}
    ctx = extract_shipment_context(empty_shipment)
    assert ctx["last_location"] == "Unknown"
    assert ctx["total_stops"] == 0


# ---------------------------------------------------------------------------
# API integration tests (no real Redis or Gemini calls)
# ---------------------------------------------------------------------------

async def test_read_root():
    """Root endpoint returns service metadata."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"          # matches new root response


async def test_health_check():
    """Health endpoint always returns ok."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_get_shipment_summary_success(monkeypatch):
    """
    Successful summary request — mocks both Redis (cache miss) and Gemini
    so no external calls are made.
    """
    # Mock Redis: always return cache miss
    monkeypatch.setattr("app.main.get_cached_summary", AsyncMock(return_value=None))
    monkeypatch.setattr("app.main.set_cached_summary", AsyncMock(return_value=None))

    # Mock Gemini: return our canned response
    async def mock_generate_ai_summary(*args, **kwargs):
        return MOCK_AI_RESPONSE

    monkeypatch.setattr(ai_summary, "generate_ai_summary", mock_generate_ai_summary)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/summarize", json={"shipment_id": "TRK86742LOG"})

    assert response.status_code == 200
    data = response.json()
    assert data["shipment_id"] == "TRK86742LOG"
    assert "Memphis" in data["summary"]
    assert data["is_exception"] is False
    assert data["cached"] is False


async def test_get_shipment_summary_cache_hit(monkeypatch):
    """
    When Redis returns a cached result, Gemini should NOT be called.
    """
    cached_payload = MOCK_AI_RESPONSE.model_dump()
    cached_payload["estimated_delivery"] = cached_payload["estimated_delivery"].isoformat()
    cached_payload["cached"] = True

    monkeypatch.setattr("app.main.get_cached_summary", AsyncMock(return_value=cached_payload))

    # If Gemini were called, this would raise — proving it wasn't reached
    monkeypatch.setattr(ai_summary, "generate_ai_summary", AsyncMock(side_effect=Exception("Should not be called")))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/summarize", json={"shipment_id": "TRK86742LOG"})

    assert response.status_code == 200
    assert response.json()["cached"] is True


async def test_get_shipment_summary_not_found():
    """Invalid shipment ID returns 404 with a meaningful message."""
    monkeypatch_cache = AsyncMock(return_value=None)

    with patch("app.main.get_cached_summary", monkeypatch_cache):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post("/summarize", json={"shipment_id": "NON_EXISTENT_ID"})

    assert response.status_code == 404
    assert "not found in our records" in response.json()["detail"]
