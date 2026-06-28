import json
import logging
import redis.asyncio as aioredis
from app.core.config import settings
from app.core.exceptions import CacheException

logger = logging.getLogger(__name__)

# Single async Redis client, reused across requests
_redis_client: aioredis.Redis | None = None


def get_redis_client() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            decode_responses=True,
        )
    return _redis_client


async def get_cached_summary(shipment_id: str) -> dict | None:
    """
    Returns the cached AI summary dict for a shipment ID, or None on miss/error.
    Cache miss is silent — the app falls through to a fresh AI call.
    """
    try:
        client = get_redis_client()
        raw = await client.get(f"summary:{shipment_id}")
        if raw:
            logger.info(f"Cache HIT for shipment {shipment_id}")
            return json.loads(raw)
        logger.info(f"Cache MISS for shipment {shipment_id}")
        return None
    except Exception as e:
        logger.warning(f"Redis GET failed for {shipment_id}: {e} — continuing without cache")
        return None


async def set_cached_summary(shipment_id: str, summary_dict: dict) -> None:
    """
    Stores the AI summary dict in Redis with a TTL.
    Failure is non-fatal — logged and swallowed.
    """
    try:
        client = get_redis_client()
        await client.setex(
            f"summary:{shipment_id}",
            settings.CACHE_TTL_SECONDS,
            json.dumps(summary_dict, default=str),   # default=str handles datetime serialisation
        )
        logger.info(f"Cached summary for shipment {shipment_id} (TTL={settings.CACHE_TTL_SECONDS}s)")
    except Exception as e:
        logger.warning(f"Redis SET failed for {shipment_id}: {e} — response not cached")
