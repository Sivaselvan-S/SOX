import React, { useState } from 'react';
import { Terminal, Shield, Filter, Code, CheckCircle } from 'lucide-react';
import type { TelemetryEvent } from '../types/telemetry';

interface TelemetryInspectorProps {
  events: TelemetryEvent[];
}

export const TelemetryInspector: React.FC<TelemetryInspectorProps> = ({ events }) => {
  const [opFilter, setOpFilter] = useState<string>('ALL');
  const [selectedEvent, setSelectedEvent] = useState<TelemetryEvent | null>(null);

  const filteredEvents = events.filter((e) => {
    if (opFilter === 'ALL') return true;
    return e.operation_name === opFilter;
  });

  return (
    <div className="telemetry-inspector-container">
      <div className="section-header-wrap">
        <div className="title-group">
          <Terminal className="section-icon text-cyan" />
          <h2>Live Agent Telemetry Inspector (OpenTelemetry GenAI Spans)</h2>
        </div>

        <div className="filter-group">
          <Filter className="filter-icon" />
          <select
            value={opFilter}
            onChange={(e) => setOpFilter(e.target.value)}
            className="select-input"
          >
            <option value="ALL">All Operations</option>
            <option value="llm_prompt">LLM Prompt Spans</option>
            <option value="execute_tool">Tool Execution Spans</option>
            <option value="state_transition">State Transitions</option>
          </select>
        </div>
      </div>

      <div className="telemetry-split-layout">
        {/* Events Table */}
        <div className="telemetry-table-wrap">
          <table className="telemetry-table">
            <thead>
              <tr>
                <th>TIMESTAMP</th>
                <th>OPERATION</th>
                <th>AGENT ID / URN</th>
                <th>TOOL / CATEGORY</th>
                <th>REDACTION</th>
                <th>PAYLOAD PREVIEW</th>
              </tr>
            </thead>
            <tbody>
              {filteredEvents.length === 0 ? (
                <tr>
                  <td colSpan={6} className="empty-table">
                    No telemetry events recorded yet. Run an attack simulation or connect an agent stream.
                  </td>
                </tr>
              ) : (
                filteredEvents.map((ev) => {
                  const isRedacted = ev.sanitized_payload && ev.sanitized_payload !== ev.payload_content;
                  const isSelected = selectedEvent?.event_id === ev.event_id;

                  return (
                    <tr
                      key={ev.event_id}
                      onClick={() => setSelectedEvent(ev)}
                      className={`telemetry-row ${isSelected ? 'selected' : ''}`}
                    >
                      <td className="mono font-sm">{new Date(ev.timestamp).toLocaleTimeString()}</td>
                      <td>
                        <span className={`op-tag ${ev.operation_name}`}>{ev.operation_name}</span>
                      </td>
                      <td>
                        <div className="agent-cell">
                          <span className="agent-id font-bold">{ev.agent.agent_id}</span>
                          <span className="urn font-sm">{ev.agent.identity_urn}</span>
                        </div>
                      </td>
                      <td>
                        {ev.tool ? (
                          <div className="tool-cell">
                            <span className="tool-name">{ev.tool.name}</span>
                            <span className={`category-tag ${ev.tool.category}`}>{ev.tool.category}</span>
                          </div>
                        ) : (
                          <span className="text-muted">—</span>
                        )}
                      </td>
                      <td>
                        {isRedacted ? (
                          <span className="redact-tag">
                            <Shield className="tag-icon" /> PII/Cred Scrubbed
                          </span>
                        ) : (
                          <span className="clean-tag">
                            <CheckCircle className="tag-icon" /> Clean
                          </span>
                        )}
                      </td>
                      <td className="payload-preview mono">
                        {ev.payload_content.slice(0, 60)}...
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* JSON Inspector Pane */}
        <div className="inspector-pane">
          <div className="pane-header">
            <Code className="pane-icon" />
            <span>GenAI OpenTelemetry Event JSON</span>
          </div>

          {selectedEvent ? (
            <pre className="json-viewer">
              {JSON.stringify(selectedEvent, null, 2)}
            </pre>
          ) : (
            <div className="empty-pane">
              <p>Click any telemetry event row to inspect its raw OpenTelemetry GenAI JSON payload.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
