import logging
from typing import List, Optional
from uuid import UUID

import motor.motor_asyncio

from app.schemas.telemetry import TelemetryEvent

logger = logging.getLogger("griffsox.repo.telemetry")


class TelemetryRepository:
    """MongoDB repository for TelemetryEvent persistence."""

    def __init__(self, db: motor.motor_asyncio.AsyncIOMotorDatabase):
        self.collection = db["telemetry_events"]

    async def insert(self, event: TelemetryEvent) -> None:
        doc = event.model_dump(mode="json")
        doc["_id"] = doc.pop("event_id")
        await self.collection.insert_one(doc)

    async def get_by_trace(self, trace_id: UUID) -> List[dict]:
        cursor = self.collection.find(
            {"trace_id": str(trace_id)},
            sort=[("timestamp", 1)],
        )
        return await cursor.to_list(length=None)

    async def get_by_id(self, event_id: UUID) -> Optional[dict]:
        return await self.collection.find_one({"_id": str(event_id)})

    async def get_all(self, limit: int = 100) -> List[dict]:
        cursor = self.collection.find({}, sort=[("timestamp", -1)]).limit(limit)
        docs = await cursor.to_list(length=limit)
        for doc in docs:
            doc["event_id"] = doc.pop("_id")
        return docs

