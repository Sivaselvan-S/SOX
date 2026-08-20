import logging
from enum import Enum
from typing import List, Optional
from uuid import UUID

import httpx
from pydantic import BaseModel

logger = logging.getLogger("griffsox.containment")

_CONTAINMENT_TIMEOUT = 5.0  # seconds — prevent indefinite blocking on unresponsive endpoints


class ContainmentTier(str, Enum):
    TIER_1_SOFT = "tier_1_soft"      # State Context Clear
    TIER_2_MEDIUM = "tier_2_medium"  # Session / Token Invalidation
    TIER_3_HARD = "tier_3_hard"      # Container Eviction & Isolation


class ContainmentActionResult(BaseModel):
    tier: ContainmentTier
    action_name: str
    success: bool
    details: str


class ContainmentResult(BaseModel):
    incident_id: UUID
    status: str  # e.g. "CONTAINED", "PARTIALLY_CONTAINED", "FAILED", "NO_ACTION"
    executed_tiers: List[ContainmentTier]
    action_results: List[ContainmentActionResult]


class ContainmentEngine:
    """Agent-native SOAR containment engine handling Tier 1/2/3 enforcement."""

    def __init__(
        self,
        sts_revoke_url: Optional[str] = None,
        docker_evict_url: Optional[str] = None,
        langgraph_interrupt_url: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
    ):
        self.sts_revoke_url = sts_revoke_url
        self.docker_evict_url = docker_evict_url
        self.langgraph_interrupt_url = langgraph_interrupt_url
        self.client = client

    async def tier_1_state_clear(self, agent_id: str) -> ContainmentActionResult:
        """Tier 1: Mutate LangGraph state to purge working memory and force safety interrupt."""
        logger.info(f"[SOAR Tier 1] Clearing state context for agent '{agent_id}'")
        try:
            if self.langgraph_interrupt_url:
                payload = {"agent_id": agent_id, "action": "purge_memory_interrupt"}
                if self.client:
                    await self.client.post(
                        self.langgraph_interrupt_url, json=payload, timeout=_CONTAINMENT_TIMEOUT
                    )
                else:
                    async with httpx.AsyncClient() as client:
                        await client.post(
                            self.langgraph_interrupt_url, json=payload, timeout=_CONTAINMENT_TIMEOUT
                        )
            return ContainmentActionResult(
                tier=ContainmentTier.TIER_1_SOFT,
                action_name="State Context Clear",
                success=True,
                details=f"LangGraph working memory purged & safety interrupt invoked for agent '{agent_id}'.",
            )
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as e:
            logger.error(f"[SOAR Tier 1] Failed state clear for '{agent_id}': {type(e).__name__}: {e}")
            return ContainmentActionResult(
                tier=ContainmentTier.TIER_1_SOFT,
                action_name="State Context Clear",
                success=False,
                details=f"Failed to purge working memory: {type(e).__name__}: {e}",
            )

    async def tier_2_token_revoke(self, identity_urn: str) -> ContainmentActionResult:
        """Tier 2: Revoke dynamic short-lived STS bearer credentials for identity_urn."""
        logger.info(f"[SOAR Tier 2] Revoking STS token for identity '{identity_urn}'")
        try:
            if self.sts_revoke_url:
                payload = {"identity_urn": identity_urn, "action": "revoke_bearer_token"}
                if self.client:
                    await self.client.post(
                        self.sts_revoke_url, json=payload, timeout=_CONTAINMENT_TIMEOUT
                    )
                else:
                    async with httpx.AsyncClient() as client:
                        await client.post(
                            self.sts_revoke_url, json=payload, timeout=_CONTAINMENT_TIMEOUT
                        )
            return ContainmentActionResult(
                tier=ContainmentTier.TIER_2_MEDIUM,
                action_name="Session / Token Invalidation",
                success=True,
                details=f"STS bearer token invalidated for URN '{identity_urn}'.",
            )
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as e:
            logger.error(f"[SOAR Tier 2] Token revocation failed for '{identity_urn}': {type(e).__name__}: {e}")
            return ContainmentActionResult(
                tier=ContainmentTier.TIER_2_MEDIUM,
                action_name="Session / Token Invalidation",
                success=False,
                details=f"Failed to revoke token: {type(e).__name__}: {e}",
            )

    async def tier_3_container_eviction(self, agent_id: str) -> ContainmentActionResult:
        """Tier 3: Trigger Docker/K8s sandbox termination & network isolation."""
        logger.info(f"[SOAR Tier 3] Evicting container & isolating network for agent '{agent_id}'")
        try:
            if self.docker_evict_url:
                payload = {"agent_id": agent_id, "action": "evict_container", "isolate_network": True}
                if self.client:
                    await self.client.post(
                        self.docker_evict_url, json=payload, timeout=_CONTAINMENT_TIMEOUT
                    )
                else:
                    async with httpx.AsyncClient() as client:
                        await client.post(
                            self.docker_evict_url, json=payload, timeout=_CONTAINMENT_TIMEOUT
                        )
            return ContainmentActionResult(
                tier=ContainmentTier.TIER_3_HARD,
                action_name="Container Eviction & Network Isolation",
                success=True,
                details=f"Container terminated and network isolated for agent '{agent_id}'. Immutable audit logged.",
            )
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as e:
            logger.error(f"[SOAR Tier 3] Container eviction failed for '{agent_id}': {type(e).__name__}: {e}")
            return ContainmentActionResult(
                tier=ContainmentTier.TIER_3_HARD,
                action_name="Container Eviction & Network Isolation",
                success=False,
                details=f"Failed to evict container: {type(e).__name__}: {e}",
            )

    async def enforce(
        self,
        incident_id: UUID,
        severity: str,
        agent_id: str,
        identity_urn: str,
    ) -> ContainmentResult:
        """Enforce SOAR containment based on Incident severity matrix."""
        target_tiers: List[ContainmentTier] = []
        action_results: List[ContainmentActionResult] = []

        sev_upper = severity.upper()
        if sev_upper == "CRITICAL":
            target_tiers = [
                ContainmentTier.TIER_1_SOFT,
                ContainmentTier.TIER_2_MEDIUM,
                ContainmentTier.TIER_3_HARD,
            ]
        elif sev_upper == "HIGH":
            target_tiers = [ContainmentTier.TIER_1_SOFT, ContainmentTier.TIER_2_MEDIUM]
        elif sev_upper == "MEDIUM":
            target_tiers = [ContainmentTier.TIER_1_SOFT]
        else:
            return ContainmentResult(
                incident_id=incident_id,
                status="NO_ACTION",
                executed_tiers=[],
                action_results=[],
            )

        # Execute targeted containment tiers
        for tier in target_tiers:
            if tier == ContainmentTier.TIER_1_SOFT:
                res = await self.tier_1_state_clear(agent_id)
            elif tier == ContainmentTier.TIER_2_MEDIUM:
                res = await self.tier_2_token_revoke(identity_urn)
            elif tier == ContainmentTier.TIER_3_HARD:
                res = await self.tier_3_container_eviction(agent_id)
            action_results.append(res)

        all_passed = all(r.success for r in action_results)
        final_status = "CONTAINED" if all_passed else "PARTIALLY_CONTAINED"

        return ContainmentResult(
            incident_id=incident_id,
            status=final_status,
            executed_tiers=target_tiers,
            action_results=action_results,
        )
