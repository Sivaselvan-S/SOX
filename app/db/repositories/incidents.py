import logging
from typing import List, Optional
from uuid import UUID

import motor.motor_asyncio

logger = logging.getLogger("griffsox.repo.incidents")


class IncidentRepository:
    """MongoDB repository for IncidentRecord persistence."""

    def __init__(self, db: motor.motor_asyncio.AsyncIOMotorDatabase):
        self.collection = db["incidents"]

    async def insert(self, record: dict) -> None:
        doc = dict(record)
        doc["_id"] = doc.get("incident_id")
        await self.collection.insert_one(doc)

    async def get_by_id(self, incident_id: str) -> Optional[dict]:
        return await self.collection.find_one({"_id": incident_id})

    async def list_all(self) -> List[dict]:
        cursor = self.collection.find({}, sort=[("created_at", -1)])
        return await cursor.to_list(length=None)

    async def update_status(self, incident_id: str, status: str) -> None:
        from datetime import datetime, timezone
        await self.collection.update_one(
            {"_id": incident_id},
            {"$set": {"status": status, "updated_at": datetime.now(timezone.utc).isoformat()}},
        )
