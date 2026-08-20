import React, { useState } from 'react';
import { AlertOctagon, ShieldCheck, Zap, ChevronDown, ChevronUp } from 'lucide-react';
import type { IncidentRecord } from '../types/telemetry';

interface IncidentDeskProps {
  incidents: IncidentRecord[];
  onTriggerContainment: (incident: IncidentRecord) => void;
}

export const IncidentDesk: React.FC<IncidentDeskProps> = ({ incidents, onTriggerContainment }) => {
  const [selectedSeverity, setSelectedSeverity] = useState<string>('ALL');
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const filteredIncidents = incidents.filter((inc) => {
    if (selectedSeverity === 'ALL') return true;
    return inc.severity === selectedSeverity;
  });

  const toggleExpand = (id: string) => {
    setExpandedId(expandedId === id ? null : id);
  };

  return (
    <div className="incident-desk-container">
      <div className="section-header-wrap">
        <div className="title-group">
          <AlertOctagon className="section-icon text-critical" />
          <h2>SOAR Incident & Containment Desk</h2>
        </div>

        {/* Severity Filter Tabs */}
        <div className="severity-tabs">
          {['ALL', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].map((sev) => (
            <button
              key={sev}
              onClick={() => setSelectedSeverity(sev)}
              className={`sev-tab ${selectedSeverity === sev ? 'active' : ''} ${sev.toLowerCase()}`}
            >
              {sev}
            </button>
          ))}
        </div>
      </div>

      {/* Incidents Table / Cards */}
      <div className="incidents-list">
        {filteredIncidents.length === 0 ? (
          <div className="empty-incidents">
            <ShieldCheck className="empty-icon text-success" />
            <p>No active security incidents matching filter. System operates within normal parameters.</p>
          </div>
        ) : (
          filteredIncidents.map((inc) => {
            const isExpanded = expandedId === inc.incident_id;

            return (
              <div key={inc.incident_id} className={`incident-card severity-${inc.severity.toLowerCase()}`}>
                <div className="incident-main-row" onClick={() => toggleExpand(inc.incident_id)}>
                  <div className="incident-col-badge">
                    <span className={`severity-badge ${inc.severity.toLowerCase()}`}>{inc.severity}</span>
                  </div>

                  <div className="incident-col-info">
                    <div className="incident-id-wrap">
                      <span className="inc-id">INC-{inc.incident_id.slice(0, 8)}</span>
                      <span className="inc-time">{new Date(inc.created_at).toLocaleTimeString()}</span>
                    </div>
                    <p className="inc-rationale">{inc.rationale}</p>
                  </div>

                  <div className="incident-col-agent">
                    <span className="agent-label">AGENT ID:</span>
                    <span className="agent-id">{inc.agent_id}</span>
                    <span className="identity-urn">{inc.identity_urn}</span>
                  </div>

                  <div className="incident-col-techniques">
                    {inc.matched_techniques.map((tech) => (
                      <span key={tech} className="atlas-tag">
                        {tech}
                      </span>
                    ))}
                  </div>

                  <div className="incident-col-status">
                    <span className={`status-badge ${inc.status.toLowerCase()}`}>{inc.status}</span>
                  </div>

                  <div className="incident-col-expand">
                    {isExpanded ? <ChevronUp /> : <ChevronDown />}
                  </div>
                </div>

                {/* Expanded Containment Log Audit */}
                {isExpanded && (
                  <div className="incident-audit-drawer">
                    <h4 className="drawer-title">SOAR Enforcement Execution Log</h4>

                    {inc.containment_result?.action_results ? (
                      <div className="tiers-grid">
                        {inc.containment_result.action_results.map((action, idx) => (
                          <div key={idx} className={`tier-card ${action.success ? 'success' : 'failed'}`}>
                            <div className="tier-header">
                              <span className="tier-name">{action.action_name}</span>
                              <span className={`tier-status ${action.success ? 'pass' : 'fail'}`}>
                                {action.success ? 'EXECUTED' : 'FAILED'}
                              </span>
                            </div>
                            <p className="tier-details">{action.details}</p>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="no-audit">No active containment actions required for this severity level.</p>
                    )}

                    <div className="drawer-actions">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onTriggerContainment(inc);
                        }}
                        className="btn-enforce"
                      >
                        <Zap className="btn-icon" />
                        <span>Re-enforce SOAR Containment Matrix</span>
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
