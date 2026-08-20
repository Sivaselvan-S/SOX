from fastapi import APIRouter
from app.api.v1 import ingestion, incidents, agent, connections, action_audit

api_router = APIRouter()
api_router.include_router(ingestion.router, prefix="/telemetry", tags=["telemetry"])
api_router.include_router(incidents.router, prefix="/incidents", tags=["incidents"])
api_router.include_router(agent.router, prefix="/agent", tags=["agent"])
api_router.include_router(connections.router, prefix="/connections", tags=["connections"])
api_router.include_router(action_audit.router, prefix="/audit", tags=["action_audit"])

