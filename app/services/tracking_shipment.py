import logging
from app.utils.data_loader import load_logistics_data
from app.core.exceptions import ShipmentNotFoundException

logger = logging.getLogger(__name__)

# Exception status codes that indicate a delay or hold
EXCEPTION_CODES = {"WTH", "HLD"}


def get_shipment_by_id(shipment_id: str) -> dict:
    """
    Fetches shipment dict by ID.
    Raises ShipmentNotFoundException if not found.
    """
    data = load_logistics_data()
    shipment = next((s for s in data if s["shipment_id"] == shipment_id), None)
    if not shipment:
        logger.warning(f"Shipment not found: {shipment_id}")
        raise ShipmentNotFoundException(shipment_id)
    return shipment


def extract_shipment_context(shipment: dict) -> dict:
    """
    Pre-processes raw shipment data into a lean context dict for the AI prompt.
    Doing this in Python (not in the prompt) keeps the LLM call focused and cheap.

    Returns:
        {
            shipment_id, overall_status, origin, destination,
            estimated_delivery, last_location, last_status_code,
            exception_events: [{timestamp, location, status_code, description}],
            total_stops: int
        }
    """
    history = shipment.get("tracking_history", [])

    # Last known event
    last_event = history[-1] if history else {}

    # Filter only exception events (WTH / HLD)
    exception_events = [
        {
            "timestamp": e["timestamp"],
            "location": e["location"],
            "status_code": e["status_code"],
            "description": e["description"],
        }
        for e in history
        if e.get("status_code") in EXCEPTION_CODES
    ]

    return {
        "shipment_id": shipment["shipment_id"],
        "overall_status": shipment["overall_status"],
        "origin": shipment["origin"],
        "destination": shipment["destination"],
        "estimated_delivery": shipment["estimated_delivery"],
        "last_location": last_event.get("location", "Unknown"),
        "last_status_code": last_event.get("status_code", ""),
        "last_description": last_event.get("description", ""),
        "exception_events": exception_events,
        "total_stops": len(history),
    }
