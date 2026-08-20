import type { IncidentRecord, TelemetryEvent, SystemHealth } from '../types/telemetry';

const getApiBase = () => {
  if (import.meta.env.VITE_API_BASE) return import.meta.env.VITE_API_BASE;
  if (typeof window !== 'undefined' && window.location.port !== '8000' && window.location.port !== '') {
    return `http://${window.location.hostname}:8000`;
  }
  return typeof window !== 'undefined' ? window.location.origin : 'http://127.0.0.1:8000';
};

const getWsBase = () => {
  if (import.meta.env.VITE_WS_BASE) return import.meta.env.VITE_WS_BASE;
  return getApiBase().replace(/^http/, 'ws');
};

const API_BASE = getApiBase();
const WS_BASE = getWsBase();

export async function checkHealth(): Promise<SystemHealth> {
  try {
    const res = await fetch(`${API_BASE}/health`);
    if (!res.ok) throw new Error(`Health check failed: ${res.statusText}`);
    return await res.json();
  } catch (err) {
    return { status: 'offline', project: 'LongWall AI' };
  }
}

export async function fetchIncidents(): Promise<IncidentRecord[]> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/incidents`);
    if (!res.ok) throw new Error(`Failed to fetch incidents: ${res.statusText}`);
    return await res.json();
  } catch (err) {
    console.warn('Backend offline or incident fetch error:', err);
    return [];
  }
}

export async function fetchTelemetryEvents(): Promise<TelemetryEvent[]> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/telemetry/events`);
    if (!res.ok) throw new Error(`Failed to fetch events: ${res.statusText}`);
    return await res.json();
  } catch (err) {
    console.warn('Backend offline or telemetry fetch error:', err);
    return [];
  }
}


export async function postTelemetryEvent(eventData: Partial<TelemetryEvent>): Promise<any> {
  const res = await fetch(`${API_BASE}/api/v1/telemetry/events`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(eventData),
  });
  if (!res.ok) throw new Error(`Telemetry post failed: ${res.statusText}`);
  return await res.json();
}

export async function postIncident(incidentData: {
  trace_id: string;
  severity: string;
  agent_id: string;
  identity_urn: string;
  matched_techniques: string[];
  rationale: string;
}): Promise<IncidentRecord> {
  const res = await fetch(`${API_BASE}/api/v1/incidents`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(incidentData),
  });
  if (!res.ok) throw new Error(`Incident post failed: ${res.statusText}`);
  return await res.json();
}

export function connectIncidentStream(
  onIncident: (incident: IncidentRecord) => void,
  onStatusChange?: (connected: boolean) => void
): () => void {
  let ws: WebSocket | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let isClosedIntentionally = false;

  const connect = () => {
    try {
      ws = new WebSocket(`${WS_BASE}/api/v1/incidents/stream`);

      ws.onopen = () => {
        onStatusChange?.(true);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.event_type === 'INCIDENT_CREATED' && data.incident) {
            onIncident(data.incident);
          }
        } catch (e) {
          console.error('Failed to parse WebSocket message:', e);
        }
      };

      ws.onclose = () => {
        onStatusChange?.(false);
        if (!isClosedIntentionally) {
          reconnectTimer = setTimeout(connect, 3000);
        }
      };

      ws.onerror = () => {
        onStatusChange?.(false);
        ws?.close();
      };
    } catch (e) {
      onStatusChange?.(false);
      reconnectTimer = setTimeout(connect, 3000);
    }
  };

  connect();

  return () => {
    isClosedIntentionally = true;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    if (ws) ws.close();
  };
}

export async function evaluateAction(req: {
  tool_name: string;
  parameters: Record<string, any>;
  agent_id?: string;
  identity_urn?: string;
  trace_id?: string;
}): Promise<AuditRecord> {
  const res = await fetch(`${API_BASE}/api/v1/audit/evaluate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error(`Evaluate action failed: ${res.statusText}`);
  return await res.json();
}

export async function simulateAttackChain(): Promise<{
  traceId: string;
  incident: IncidentRecord;
}> {
  const traceId = crypto.randomUUID();
  const agentId = 'builtin-finance';
  const identityUrn = 'spiffe://prod/finance-agent';

  // Step 1: Trigger Block Outcome (Bulk Delete > 100)
  await evaluateAction({
    tool_name: 'database_delete',
    parameters: { query: 'DELETE FROM users WHERE active = 0', record_count: 500 },
    agent_id: 'builtin-finance',
    identity_urn: 'spiffe://prod/finance-agent',
    trace_id: traceId,
  }).catch(() => {});

  // Step 2: Trigger HITL Outcome (External Email)
  await evaluateAction({
    tool_name: 'send_email',
    parameters: { to: 'attacker@external-domain.com', to_domain: 'external-domain.com', subject: 'Quarterly Audit Dump' },
    agent_id: 'builtin-readonly',
    identity_urn: 'spiffe://prod/read-only-agent',
    trace_id: traceId,
  }).catch(() => {});

  // Step 3: Trigger Log & Allow Outcome (Confidential File Read)
  await evaluateAction({
    tool_name: 'read_file',
    parameters: { path: 'confidential/passwords.txt' },
    agent_id: 'builtin-finance',
    identity_urn: 'spiffe://prod/finance-agent',
    trace_id: traceId,
  }).catch(() => {});

  // Step 4: Post Incident summary
  const incident = await postIncident({
    trace_id: traceId,
    severity: 'CRITICAL',
    agent_id: agentId,
    identity_urn: identityUrn,
    matched_techniques: ['AML.T0051', 'AML.T0061', 'AML.T0062'],
    rationale: 'CRITICAL: PS-3.1 Action Guardrail evaluation completed across all 3 outcome tiers.',
  });

  return { traceId, incident };
}

export async function sendAgentChat(
  message: string,
  traceId?: string
): Promise<{ response: string; trace_id: string; tool_calls: Array<{ name: string; args: any }> }> {
  const res = await fetch(`${API_BASE}/api/v1/agent/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, trace_id: traceId }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Failed to communicate with LangGraph Agent');
  }
  return await res.json();
}

export interface AgentConnectionModel {
  id: string;
  name: string;
  description: string;
  target_url: string;
  identity_urn: string;
  allowed_tools: string[];
  enforcement_mode: string;
  status: string;
  created_at: string;
}

export async function fetchConnections(): Promise<AgentConnectionModel[]> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/connections`);
    if (!res.ok) throw new Error(`Failed to fetch connections: ${res.statusText}`);
    return await res.json();
  } catch (err) {
    console.warn('Backend offline or connections fetch error:', err);
    return [];
  }
}

export async function createConnection(connectionData: {
  name: string;
  description?: string;
  target_url: string;
  identity_urn: string;
  allowed_tools: string[];
  enforcement_mode?: string;
  api_key?: string;
}): Promise<AgentConnectionModel> {
  const res = await fetch(`${API_BASE}/api/v1/connections`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(connectionData),
  });
  if (!res.ok) throw new Error(`Failed to create connection: ${res.statusText}`);
  return await res.json();
}

export async function deleteConnection(connectionId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/connections/${connectionId}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error(`Failed to delete connection: ${res.statusText}`);
}

export async function sendProxyAgentChat(
  connectionId: string,
  message: string,
  traceId?: string
): Promise<{
  response: string;
  trace_id: string;
  tool_calls: Array<{ name: string; args: any }>;
  security_audit?: any;
}> {
  const res = await fetch(`${API_BASE}/api/v1/connections/${connectionId}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, trace_id: traceId }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Failed to chat via Proxy Gateway');
  }
  return await res.json();
}

// ─── PS-3.1 Action Guardrail Audit & HITL Endpoints ──────────────────────────

export interface AuditRecord {
  id: string;
  trace_id: string;
  agent_id: string;
  identity_urn: string;
  tool_name: string;
  parameters: Record<string, any>;
  outcome: 'block' | 'require_hitl' | 'log_and_allow' | 'allow';
  rule_id?: string;
  rule_name?: string;
  reason: string;
  hitl_status?: 'pending' | 'approved' | 'rejected';
  dry_run: boolean;
  timestamp: string;
}

export async function fetchAuditLog(): Promise<AuditRecord[]> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/audit/log`);
    if (!res.ok) throw new Error(`Failed to fetch audit log: ${res.statusText}`);
    return await res.json();
  } catch (err) {
    console.warn('Audit log fetch error:', err);
    return [];
  }
}

export async function fetchPendingHitl(): Promise<AuditRecord[]> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/audit/hitl/pending`);
    if (!res.ok) throw new Error(`Failed to fetch pending HITL: ${res.statusText}`);
    return await res.json();
  } catch (err) {
    console.warn('Pending HITL fetch error:', err);
    return [];
  }
}

export async function approveHitl(recordId: string): Promise<AuditRecord> {
  const res = await fetch(`${API_BASE}/api/v1/audit/hitl/${recordId}/approve`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error(`Approve HITL failed: ${res.statusText}`);
  return await res.json();
}

export async function rejectHitl(recordId: string): Promise<AuditRecord> {
  const res = await fetch(`${API_BASE}/api/v1/audit/hitl/${recordId}/reject`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error(`Reject HITL failed: ${res.statusText}`);
  return await res.json();
}

export async function fetchActiveRules(): Promise<any> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/audit/rules`);
    if (!res.ok) throw new Error(`Failed to fetch active rules: ${res.statusText}`);
    return await res.json();
  } catch (err) {
    console.warn('Active rules fetch error:', err);
    return null;
  }
}

export async function toggleDryRun(): Promise<{ dry_run: boolean }> {
  const res = await fetch(`${API_BASE}/api/v1/audit/dry-run/toggle`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error(`Toggle dry-run failed: ${res.statusText}`);
  return await res.json();
}

export async function createActionRule(ruleData: any): Promise<any> {
  const res = await fetch(`${API_BASE}/api/v1/audit/rules`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(ruleData),
  });
  if (!res.ok) throw new Error(`Create rule failed: ${res.statusText}`);
  return await res.json();
}

export async function updateActionRule(ruleId: string, ruleData: any): Promise<any> {
  const res = await fetch(`${API_BASE}/api/v1/audit/rules/${ruleId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(ruleData),
  });
  if (!res.ok) throw new Error(`Update rule failed: ${res.statusText}`);
  return await res.json();
}

export async function deleteActionRule(ruleId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/audit/rules/${ruleId}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error(`Delete rule failed: ${res.statusText}`);
}

export async function fetchFinanceDbStatus(): Promise<{ total_records: number; records: any[]; message: string }> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/audit/db-status`);
    if (!res.ok) throw new Error(`Fetch DB status failed: ${res.statusText}`);
    return await res.json();
  } catch (err) {
    console.warn('Fetch DB status error:', err);
    return { total_records: 30, records: [], message: 'SQLite DB status unavailable' };
  }
}

export async function resetFinanceDb(): Promise<{ total_records: number; message: string }> {
  const res = await fetch(`${API_BASE}/api/v1/audit/db-reset`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error(`Reset DB failed: ${res.statusText}`);
  return await res.json();
}

export async function updateConnection(connectionId: string, data: Partial<AgentConnectionModel>): Promise<AgentConnectionModel> {
  const res = await fetch(`${API_BASE}/api/v1/connections/${connectionId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`Update connection failed: ${res.statusText}`);
  return await res.json();
}


