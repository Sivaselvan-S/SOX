import React from 'react';
import { X, ShieldAlert, AlertTriangle, Cpu, Terminal, Clock, User } from 'lucide-react';
import type { TelemetryEvent } from '../types/telemetry';

interface NodeDetailModalProps {
  event: TelemetryEvent | null;
  onClose: () => void;
}

export const NodeDetailModal: React.FC<NodeDetailModalProps> = ({ event, onClose }) => {
  if (!event) return null;

  const fp = event.detections?.fastpath;
  const policy = event.detections?.policy;
  const judge = event.detections?.judge;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="title-wrap">
            <Terminal className="modal-icon text-cyan" />
            <div>
              <h3>Span Inspector: {event.operation_name}</h3>
              <span className="mono font-sm text-muted">ID: {event.event_id}</span>
            </div>
          </div>
          <button onClick={onClose} className="close-btn">
            <X />
          </button>
        </div>

        <div className="modal-body">
          {/* Metadata Grid */}
          <div className="meta-grid">
            <div className="meta-item">
              <span className="meta-label">
                <Clock className="icon-sm" /> Timestamp:
              </span>
              <span className="meta-val mono">{new Date(event.timestamp).toLocaleString()}</span>
            </div>

            <div className="meta-item">
              <span className="meta-label">
                <User className="icon-sm" /> Agent ID:
              </span>
              <span className="meta-val">{event.agent.agent_id}</span>
            </div>

            <div className="meta-item col-span-2">
              <span className="meta-label">SPIFFE URN:</span>
              <span className="meta-val mono">{event.agent.identity_urn}</span>
            </div>

            {event.tool && (
              <>
                <div className="meta-item">
                  <span className="meta-label">Tool Name:</span>
                  <span className="meta-val highlight">{event.tool.name}</span>
                </div>
                <div className="meta-item">
                  <span className="meta-label">Tool Category:</span>
                  <span className={`category-tag ${event.tool.category}`}>{event.tool.category}</span>
                </div>
              </>
            )}
          </div>

          {/* Detections Section */}
          <div className="detections-section">
            <h4>Security Analysis & Detection Signals</h4>

            {/* FastPath */}
            <div className={`det-box ${fp?.matched ? 'matched' : 'clean'}`}>
              <div className="det-header">
                <ShieldAlert className="det-icon" />
                <span>FastPath Sync Rule Check (Sub-5ms)</span>
                <span className="det-badge">{fp?.matched ? 'MATCHED' : 'PASS'}</span>
              </div>
              {fp?.matched && (
                <p className="det-body">
                  Triggered Rule: <strong>{fp.rule_id}</strong> ({fp.rule_name}) in {fp.latency_ms} ms.
                </p>
              )}
            </div>

            {/* Policy */}
            <div className={`det-box ${policy ? (policy.allowed === false ? 'violating' : 'clean') : 'clean'}`}>
              <div className="det-header">
                <AlertTriangle className="det-icon" />
                <span>RBAC Policy Engine</span>
                <span className="det-badge">{policy ? (policy.allowed === false ? 'VIOLATION' : 'ALLOWED') : 'N/A'}</span>
              </div>
              {policy?.allowed === false && <p className="det-body">{policy.reason}</p>}
            </div>

            {/* Judge SLM */}
            <div className={`det-box ${judge ? (judge.is_anomalous ? 'anomalous' : 'clean') : 'clean'}`}>
              <div className="det-header">
                <Cpu className="det-icon" />
                <span>Async Gemini SLM Intent Judge</span>
                <span className="det-badge">{judge ? (judge.is_anomalous ? 'ANOMALOUS' : 'NORMAL') : 'N/A'}</span>
              </div>
              {judge && (
                <div className="det-body">
                  <p>
                    Divergence Score: <strong>{(judge.divergence_score * 100).toFixed(1)}%</strong> |
                    Confidence: <strong>{(judge.confidence * 100).toFixed(0)}%</strong>
                  </p>
                  <p className="rationale-text">"{judge.rationale}"</p>
                </div>
              )}
            </div>
          </div>

          {/* Payload Content */}
          <div className="payload-box">
            <h4>Payload Content</h4>
            <pre className="payload-text">{event.payload_content}</pre>
          </div>

          {event.sanitized_payload && event.sanitized_payload !== event.payload_content && (
            <div className="payload-box sanitized">
              <h4>Sanitized / Redacted Payload</h4>
              <pre className="payload-text">{event.sanitized_payload}</pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
