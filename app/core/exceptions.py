class ShipmentNotFoundException(Exception):
    """Raised when a shipment ID does not exist in the data store."""
    def __init__(self, shipment_id: str):
        self.shipment_id = shipment_id
        super().__init__(f"Shipment '{shipment_id}' not found.")


class AIServiceException(Exception):
    """Raised when the Gemini AI service fails or returns unparseable output."""
    pass


class CacheException(Exception):
    """Raised when Redis operations fail. Non-fatal — app continues without cache."""
    pass
