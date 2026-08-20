import React, { useEffect, useState } from 'react';
import { ShieldAlert, CheckCircle2, PauseCircle, Eye, RefreshCw, FileText } from 'lucide-react';
import { fetchAuditLog } from '../api/client';
import type { AuditRecord } from '../api/client';

export const ActionAuditLog: React.FC = () => {
  const [records, setRecords] = useState<AuditRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [filterOutcome, setFilterOutcome] = useState<string>('all');

  const loadData = async () => {
    setIsLoading(true);
    const data = await fetchAuditLog();
    setRecords(data);
    setIsLoading(false);
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 4000);
    return () => clearInterval(interval);
  }, []);

  const filteredRecords = records.filter((r) => {
    if (filterOutcome === 'all') return true;
    return r.outcome === filterOutcome;
  });

  const getBadgeClass = (outcome: string) => {
    switch (outcome) {
      case 'block':
        return 'badge-block';
      case 'require_hitl':
        return 'badge-hitl';
      case 'log_and_allow':
        return 'badge-log-allow';
      default:
        return 'badge-allow';
    }
  };

  return (
    <div className="audit-log-container">
      <div className="section-header-wrap">
        <div className="title-group">
          <FileText className="section-icon text-cyan" />
          <div>
            <h2>Pre-Execution Action Guardrail Audit Log</h2>
            <p className="subtitle">Real-time audit decisions for every agent tool call evaluated against declarative policy rules.</p>
          </div>
        </div>

        <div className="header-actions">
          <div className="filter-group">
            <span className="filter-label">OUTCOME:</span>
            <button onClick={() => setFilterOutcome('all')} className={`filter-btn ${filterOutcome === 'all' ? 'active' : ''}`}>
              All ({records.length})
            </button>
            <button onClick={() => setFilterOutcome('block')} className={`filter-btn ${filterOutcome === 'block' ? 'active' : ''}`}>
              Blocked
            </button>
            <button onClick={() => setFilterOutcome('require_hitl')} className={`filter-btn ${filterOutcome === 'require_hitl' ? 'active' : ''}`}>
              HITL
            </button>
            <button onClick={() => setFilterOutcome('log_and_allow')} className={`filter-btn ${filterOutcome === 'log_and_allow' ? 'active' : ''}`}>
              Log & Allow
            </button>
          </div>

          <button onClick={loadData} className="btn-refresh">
            <RefreshCw className="icon-sm" /> Refresh
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="loading-box">
          <RefreshCw className="spinner" /> Loading Action Audit Log...
        </div>
      ) : filteredRecords.length === 0 ? (
        <div className="empty-card">
          <FileText className="empty-icon text-dim" />
          <p>No action evaluations found matching current filter.</p>
        </div>
      ) : (
        <div className="audit-table-wrap">
          <table className="audit-table">
            <thead>
              <tr>
                <th>TIMESTAMP</th>
                <th>ACTION OUTCOME</th>
                <th>TOOL NAME</th>
                <th>MATCHED RULE</th>
                <th>IDENTITY URN</th>
                <th>TOOL PARAMETERS</th>
                <th>REASON</th>
              </tr>
            </thead>
            <tbody>
              {filteredRecords.map((rec) => (
                <tr key={rec.id} className={`audit-row ${rec.outcome}`}>
                  <td className="mono-sm">{new Date(rec.timestamp).toLocaleTimeString()}</td>
                  <td>
                    <span className={`outcome-pill ${getBadgeClass(rec.outcome)}`}>
                      {rec.outcome === 'block' && <ShieldAlert className="icon-nano" />}
                      {rec.outcome === 'require_hitl' && <PauseCircle className="icon-nano" />}
                      {rec.outcome === 'log_and_allow' && <Eye className="icon-nano" />}
                      {rec.outcome === 'allow' && <CheckCircle2 className="icon-nano" />}
                      {rec.outcome.toUpperCase()}
                    </span>
                  </td>
                  <td className="mono bold">{rec.tool_name}</td>
                  <td className="rule-cell">
                    {rec.rule_id ? (
                      <span className="rule-tag">
                        [{rec.rule_id}] {rec.rule_name}
                      </span>
                    ) : (
                      <span className="text-muted">None (Default)</span>
                    )}
                  </td>
                  <td className="mono-sm text-dim">{rec.identity_urn}</td>
                  <td className="params-cell mono-sm">
                    <pre>{JSON.stringify(rec.parameters, null, 1)}</pre>
                  </td>
                  <td className="reason-cell">{rec.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
