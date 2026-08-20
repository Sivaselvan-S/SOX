import asyncio
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field

from app.response.containment import ContainmentEngine, ContainmentResult
from app.response.notifier import SIEMNotification, SIEMNotifier

router = APIRouter()


class IncidentCreateRequest(BaseModel):
    trace_id: UUID
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    agent_id: str
    identity_urn: str
    matched_techniques: List[str] = Field(default_factory=list)
    rationale: str = "Incident registered."


class IncidentRecord(BaseModel):
    incident_id: UUID
    trace_id: UUID
    severity: str
    status: str  # OPEN, CONTAINED, PARTIALLY_CONTAINED, NO_ACTION
    agent_id: str
    identity_urn: str
    matched_techniques: List[str]
    rationale: str
    containment_result: Optional[ContainmentResult] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# In-memory Incident Store & WebSocket Connection Manager
class IncidentStoreManager:
    def __init__(self):
        # Use str key to avoid UUID equality edge cases across serializations
        self.incidents: dict[str, IncidentRecord] = {}
        self.active_websockets: List[WebSocket] = []

    async def connect_ws(self, websocket: WebSocket):
        await websocket.accept()
        self.active_websockets.append(websocket)

    def disconnect_ws(self, websocket: WebSocket):
        if websocket in self.active_websockets:
            self.active_websockets.remove(websocket)

    async def broadcast_ws(self, payload: dict):
        """Non-blocking fan-out: each send wrapped in a task so slow clients don't stall others."""
        for ws in list(self.active_websockets):
            asyncio.create_task(_safe_send(ws, payload, self))


async def _safe_send(ws: WebSocket, payload: dict, manager: "IncidentStoreManager"):
    try:
        await ws.send_json(payload)
    except Exception:
        manager.disconnect_ws(ws)


store_manager = IncidentStoreManager()
containment_engine = ContainmentEngine()
siem_notifier = SIEMNotifier()


@router.get("", response_model=List[IncidentRecord])
async def list_incidents() -> List[IncidentRecord]:
    """Retrieve all registered incidents."""
    return list(store_manager.incidents.values())


@router.get("/{incident_id}", response_model=IncidentRecord)
async def get_incident(incident_id: UUID) -> IncidentRecord:
    """Retrieve a specific incident by ID."""
    key = str(incident_id)
    if key not in store_manager.incidents:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incident not found.",
        )
    return store_manager.incidents[key]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=IncidentRecord)
async def create_and_contain_incident(req: IncidentCreateRequest) -> IncidentRecord:
    """Register an incident, execute SOAR containment, send SIEM alert, and broadcast WS feed."""
    # Validate severity
    valid_severities = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
    if req.severity.upper() not in valid_severities:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid severity '{req.severity}'. Must be one of: {sorted(valid_severities)}",
        )

    incident_id = uuid4()

    # Enforce SOAR Containment Matrix
    containment_res = await containment_engine.enforce(
        incident_id=incident_id,
        severity=req.severity,
        agent_id=req.agent_id,
        identity_urn=req.identity_urn,
    )

    record = IncidentRecord(
        incident_id=incident_id,
        trace_id=req.trace_id,
        severity=req.severity,
        status=containment_res.status,
        agent_id=req.agent_id,
        identity_urn=req.identity_urn,
        matched_techniques=req.matched_techniques,
        rationale=req.rationale,
        containment_result=containment_res,
    )

    # Store using str key for consistent UUID-to-str lookups
    store_manager.incidents[str(incident_id)] = record

    # Fire-and-forget SIEM notification (non-blocking)
    asyncio.create_task(
        siem_notifier.dispatch(
            SIEMNotification(
                incident_id=str(incident_id),
                trace_id=str(req.trace_id),
                severity=req.severity,
                matched_techniques=req.matched_techniques,
                status=containment_res.status,
                summary=req.rationale,
            )
        )
    )

    # Non-blocking WebSocket broadcast
    ws_payload = {
        "event_type": "INCIDENT_CREATED",
        "incident": record.model_dump(mode="json"),
    }
    await store_manager.broadcast_ws(ws_payload)

    return record


@router.websocket("/stream")
async def incident_websocket_stream(websocket: WebSocket):
    """WebSocket live incident streaming endpoint."""
    await store_manager.connect_ws(websocket)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        store_manager.disconnect_ws(websocket)
