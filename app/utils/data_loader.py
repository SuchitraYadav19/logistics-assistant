import json
import logging
from pathlib import Path
from functools import lru_cache

logger = logging.getLogger(__name__)

DATA_FILE = Path(__file__).parent.parent.parent / "data" / "synthetic_data.json"


@lru_cache(maxsize=1)
def load_logistics_data() -> list[dict]:
    """
    Loads shipment data from JSON once and caches it in memory for the
    process lifetime. Use `load_logistics_data.cache_clear()` in tests.
    """
    if not DATA_FILE.exists():
        logger.error(f"Data file not found at {DATA_FILE}")
        return []
    with open(DATA_FILE) as f:
        data = json.load(f)
    logger.info(f"Loaded {len(data)} shipments from {DATA_FILE.name}")
    return data
