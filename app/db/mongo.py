import logging
from typing import Optional

import motor.motor_asyncio
from pymongo import ASCENDING

from app.core.config import settings

logger = logging.getLogger("griffsox.db")

_client: Optional[motor.motor_asyncio.AsyncIOMotorClient] = None


def get_client() -> motor.motor_asyncio.AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = motor.motor_asyncio.AsyncIOMotorClient(settings.MONGO_URI)
    return _client


def get_db() -> motor.motor_asyncio.AsyncIOMotorDatabase:
    return get_client()[settings.MONGO_DB_NAME]


async def init_indexes() -> None:
    """Create MongoDB indexes at startup. Idempotent — safe to call multiple times."""
    db = get_db()

    # telemetry_events: TTL index on timestamp for auto-expiry
    await db.telemetry_events.create_index(
        [("timestamp", ASCENDING)],
        expireAfterSeconds=settings.TELEMETRY_TTL_DAYS * 86400,
        name="telemetry_ttl",
    )
    # telemetry_events: compound index for trace-level queries
    await db.telemetry_events.create_index(
        [("trace_id", ASCENDING), ("timestamp", ASCENDING)],
        name="trace_time",
    )
    # incidents: index on severity + created_at for dashboard queries
    await db.incidents.create_index(
        [("severity", ASCENDING), ("created_at", ASCENDING)],
        name="severity_time",
    )
    logger.info("MongoDB indexes ensured.")


async def close_client() -> None:
    global _client
    if _client:
        _client.close()
        _client = None
