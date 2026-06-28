from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class TrackingDataFormat(BaseModel):
    timestamp: datetime
    location: str
    status_code: str
    description: str
    carrier: str


class ShipmentDataFormat(BaseModel):
    shipment_id: str
    overall_status: str
    origin: str
    destination: str
    estimated_delivery: datetime
    tracking_history: List[TrackingDataFormat]


class ShipmentInputFormat(BaseModel):
    shipment_id: str = Field(..., example="TRK86742LOG")


class AISummaryResponse(BaseModel):
    shipment_id: str
    summary: str
    estimated_delivery: datetime          # fixed typo from original (was: estimated_deliver)
    is_exception: bool
    suggested_actions: Optional[str] = None
    cached: bool = False                  # tells caller if response came from cache
