import logging
from typing import Optional

import httpx
from pydantic import BaseModel

logger = logging.getLogger("griffsox.notifier")


class SIEMNotification(BaseModel):
    incident_id: str
    trace_id: str
    severity: str
    matched_techniques: list[str]
    status: str
    summary: str


class SIEMNotifier:
    """SIEM Webhook alert dispatcher."""

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
    ):
        self.webhook_url = webhook_url
        self.client = client

    async def dispatch(self, notification: SIEMNotification) -> bool:
        """Dispatch incident payload to configured SIEM webhook URL."""
        if not self.webhook_url:
            logger.info("No SIEM webhook URL configured. Skipping notification dispatch.")
            return False

        payload = notification.model_dump(mode="json")
        try:
            if self.client:
                res = await self.client.post(self.webhook_url, json=payload, timeout=3.0)
            else:
                async with httpx.AsyncClient() as client:
                    res = await client.post(self.webhook_url, json=payload, timeout=3.0)

            if res.status_code in (200, 201, 202):
                logger.info(f"Successfully dispatched SIEM notification for incident {notification.incident_id}")
                return True
            else:
                logger.warning(f"SIEM webhook returned non-200 status {res.status_code}")
                return False
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as e:
            logger.error(f"Failed to dispatch SIEM webhook notification: {type(e).__name__}: {e}")
            return False
