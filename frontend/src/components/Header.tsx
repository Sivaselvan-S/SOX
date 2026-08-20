import { Cpu, Database, Activity, PlayCircle, RefreshCw } from 'lucide-react';
import type { SystemHealth } from '../types/telemetry';
import type { AuditRecord } from '../api/client';

interface HeaderProps {
  health: SystemHealth;
  wsConnected: boolean;
  auditRecords: AuditRecord[];
  pendingHitlRecords: AuditRecord[];
  onSimulateAttack: () => void;
  isSimulating: boolean;
  onRefresh: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  health,
  wsConnected,
  auditRecords,
  pendingHitlRecords,
  onSimulateAttack,
  isSimulating,
  onRefresh,
}) => {
  const totalEvaluations = auditRecords.length;
  const blockedCount = auditRecords.filter((r) => r.outcome === 'block').length;
  const pendingHitlCount = pendingHitlRecords.length;
  const auditedCount = auditRecords.filter((r) => r.outcome === 'log_and_allow').length;

  return (
    <header className="brand-header">
      <div className="header-top">
        <div className="brand-logo">
          <div className="logo-icon-wrap">
            <img src="/logo.png" alt="LongWall AI" className="logo-img" />
          </div>
          <div>
            <div className="brand-title-wrap">
              <h1 className="brand-name">LongWall AI</h1>
              <span className="version-badge">v1.0.0</span>
            </div>
            <p className="brand-sub">PS-3.1 Pre-Execution Action Guardrail & Policy Governance Engine</p>
          </div>
        </div>

        {/* System Health Indicators */}
        <div className="health-bar">
          <div className={`status-pill ${health.status === 'healthy' ? 'online' : 'offline'}`}>
            <span className="status-dot"></span>
            <span className="status-label">Backend {health.status}</span>
          </div>

          <div className={`status-pill ${wsConnected ? 'online' : 'offline'}`}>
            <Activity className="pill-icon" />
            <span className="status-label">WebSocket {wsConnected ? 'Live' : 'Connecting'}</span>
          </div>

          <div className="status-pill info">
            <Database className="pill-icon" />
            <span className="status-label">YAML Rules Loaded</span>
          </div>

          <div className="status-pill gemini">
            <Cpu className="pill-icon" />
            <span className="status-label">Action Guardrail Active</span>
          </div>
        </div>

        {/* Quick Action Button */}
        <div className="header-actions">
          <button
            onClick={onRefresh}
            className="btn-secondary"
            title="Refresh Data"
          >
            <RefreshCw className="btn-icon" />
          </button>
          <button
            onClick={onSimulateAttack}
            disabled={isSimulating}
            className="btn-danger-action"
          >
            {isSimulating ? (
              <>
                <RefreshCw className="btn-icon spin" />
                <span>Simulating Action Evaluation...</span>
              </>
            ) : (
              <>
                <PlayCircle className="btn-icon" />
                <span>Simulate Action Evaluation</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Action Guardrail Metrics Strip */}
      <div className="metrics-strip">
        <div className="metric-box">
          <span className="metric-label">ACTION EVALUATIONS</span>
          <span className="metric-value cyan">{totalEvaluations}</span>
        </div>

        <div className="metric-box">
          <span className="metric-label">BLOCKED ACTIONS</span>
          <span className="metric-value critical">{blockedCount}</span>
        </div>

        <div className="metric-box">
          <span className="metric-label">PENDING HITL APPROVALS</span>
          <span className="metric-value danger">{pendingHitlCount}</span>
        </div>

        <div className="metric-box">
          <span className="metric-label">LOG & ALLOW AUDITS</span>
          <span className="metric-value success">{auditedCount}</span>
        </div>

        <div className="metric-box">
          <span className="metric-label">GUARDRAIL LATENCY</span>
          <span className="metric-value green">&lt; 0.5 ms</span>
        </div>
      </div>
    </header>
  );
};
