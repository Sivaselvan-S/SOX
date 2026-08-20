import React, { useEffect, useState } from 'react';
import { PauseCircle, CheckCircle2, XCircle, RefreshCw, AlertCircle } from 'lucide-react';
import { fetchPendingHitl, approveHitl, rejectHitl } from '../api/client';
import type { AuditRecord } from '../api/client';

export const HitlQueue: React.FC = () => {
  const [pendingItems, setPendingItems] = useState<AuditRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [processingId, setProcessingId] = useState<string | null>(null);

  const loadData = async (showLoadingSpinner = false) => {
    if (showLoadingSpinner) setIsLoading(true);
    try {
      const data = await fetchPendingHitl();
      setPendingItems(data);
    } catch (err) {
      console.error('Error fetching HITL queue:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData(true);
    const interval = setInterval(() => loadData(false), 3000);
    return () => clearInterval(interval);
  }, []);

  const handleApprove = async (id: string) => {
    setProcessingId(id);
    try {
      await approveHitl(id);
      loadData();
    } catch (err) {
      alert('Failed to approve action.');
    } finally {
      setProcessingId(null);
    }
  };

  const handleReject = async (id: string) => {
    setProcessingId(id);
    try {
      await rejectHitl(id);
      loadData();
    } catch (err) {
      alert('Failed to reject action.');
    } finally {
      setProcessingId(null);
    }
  };

  return (
    <div className="hitl-container">
      <div className="section-header-wrap">
        <div className="title-group">
          <PauseCircle className="section-icon text-amber" />
          <div>
            <h2>Human-In-The-Loop (HITL) Action Approval Queue</h2>
            <p className="subtitle">Agent tool calls paused pre-execution requiring human review before dispatch.</p>
          </div>
        </div>

        <button onClick={() => loadData(true)} className="btn-refresh">
          <RefreshCw className="icon-sm" /> Refresh Queue
        </button>
      </div>

      {isLoading ? (
        <div className="loading-box">
          <RefreshCw className="spinner" /> Loading HITL Queue...
        </div>
      ) : pendingItems.length === 0 ? (
        <div className="empty-card green-border">
          <CheckCircle2 className="empty-icon text-emerald" />
          <h3>No Pending Action Approvals</h3>
          <p>All agent tool executions have been evaluated or resolved.</p>
        </div>
      ) : (
        <div className="hitl-cards-grid">
          {pendingItems.map((item) => (
            <div key={item.id} className="hitl-card">
              <div className="hitl-card-header">
                <div className="status-title">
                  <AlertCircle className="icon-sm text-amber" />
                  <span className="hitl-title">Action Approval Required</span>
                </div>
                <span className="mono-sm text-muted">{new Date(item.timestamp).toLocaleTimeString()}</span>
              </div>

              <div className="hitl-card-body">
                <div className="hitl-field">
                  <span className="field-label">TOOL NAME:</span>
                  <span className="field-val mono bold">{item.tool_name}</span>
                </div>

                <div className="hitl-field">
                  <span className="field-label">AGENT IDENTITY:</span>
                  <span className="field-val mono-sm">{item.identity_urn}</span>
                </div>

                <div className="hitl-field">
                  <span className="field-label">MATCHED GUARDRAIL RULE:</span>
                  <span className="field-val rule-highlight">[{item.rule_id}] {item.rule_name}</span>
                </div>

                <div className="hitl-field col-span-2">
                  <span className="field-label">POLICY REASON:</span>
                  <p className="reason-text">{item.reason}</p>
                </div>

                <div className="hitl-field col-span-2">
                  <span className="field-label">TOOL PARAMETERS:</span>
                  <pre className="json-box">{JSON.stringify(item.parameters, null, 2)}</pre>
                </div>
              </div>

              <div className="hitl-card-actions">
                <button
                  onClick={() => handleReject(item.id)}
                  disabled={processingId === item.id}
                  className="btn-reject"
                >
                  <XCircle className="btn-icon" /> Reject Action
                </button>
                <button
                  onClick={() => handleApprove(item.id)}
                  disabled={processingId === item.id}
                  className="btn-approve"
                >
                  <CheckCircle2 className="btn-icon" /> Approve Execution
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
