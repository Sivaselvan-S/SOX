export type OperationName = 'llm_prompt' | 'execute_tool' | 'state_transition';
export type ToolCategory = 'database_write' | 'file_egress' | 'system_exec' | 'read';
export type SeverityLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
export type ContainmentStatus = 'CONTAINED' | 'PARTIALLY_CONTAINED' | 'FAILED' | 'NO_ACTION';
export type ContainmentTier = 'tier_1_soft' | 'tier_2_medium' | 'tier_3_hard';

export interface AgentMeta {
  agent_id: string;
  framework: string;
  identity_urn: string;
  delegation_chain: string[];
}

export interface ToolMeta {
  name: string;
  category: ToolCategory;
  call_id: string;
  parameters: Record<string, any>;
}

export interface FastPathResult {
  matched: boolean;
  rule_id?: string;
  rule_name?: string;
  latency_ms: number;
}

export interface PolicyResult {
  allowed: boolean;
  identity_urn: string;
  tool_category?: ToolCategory;
  reason?: string;
}

export interface JudgeVerdict {
  is_anomalous: boolean;
  confidence: number;
  divergence_score: number;
  rationale: string;
}

export interface EventDetections {
  fastpath?: FastPathResult;
  policy?: PolicyResult;
  judge?: JudgeVerdict;
}

export interface TelemetryEvent {
  event_id: string;
  trace_id: string;
  parent_span_id?: string | null;
  timestamp: string;
  agent: AgentMeta;
  operation_name: OperationName;
  tool?: ToolMeta | null;
  payload_content: string;
  sanitized_payload?: string | null;
  detections?: EventDetections;
}

export interface ContainmentActionResult {
  tier: ContainmentTier;
  action_name: string;
  success: boolean;
  details: string;
}

export interface ContainmentResult {
  incident_id: string;
  status: ContainmentStatus;
  executed_tiers: ContainmentTier[];
  action_results: ContainmentActionResult[];
}

export interface IncidentRecord {
  incident_id: string;
  trace_id: string;
  severity: SeverityLevel;
  status: ContainmentStatus;
  agent_id: string;
  identity_urn: string;
  matched_techniques: string[];
  rationale: string;
  containment_result?: ContainmentResult;
  created_at: string;
  updated_at?: string;
}

export interface SystemHealth {
  status: string;
  project: string;
  mongodb?: string;
  judge_mode?: string;
}
