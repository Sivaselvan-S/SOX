import React, { useState } from 'react';
import { Network, Layers, ShieldAlert, AlertTriangle, Cpu, Terminal, ArrowRight } from 'lucide-react';
import type { TelemetryEvent, OperationName } from '../types/telemetry';

interface GraphNode {
  id: string;
  event_id: string;
  trace_id: string;
  operation_name: OperationName;
  tool_name?: string;
  tool_category?: string;
  hasFastpathMatch: boolean;
  hasPolicyViolation: boolean;
  hasJudgeDivergence: boolean;
  isMetaNode?: boolean;
  compressedCount?: number;
  payload: string;
  rawEvent: TelemetryEvent;
}

interface GraphVisualizerProps {
  events: TelemetryEvent[];
  selectedTraceId: string;
  onSelectTraceId: (traceId: string) => void;
  onSelectNode: (event: TelemetryEvent) => void;
}

export const GraphVisualizer: React.FC<GraphVisualizerProps> = ({
  events,
  selectedTraceId,
  onSelectTraceId,
  onSelectNode,
}) => {
  const [isCompressed, setIsCompressed] = useState(false);

  // Group trace IDs
  const traceIds = Array.from(new Set(events.map((e) => e.trace_id)));
  const currentTraceEvents = events.filter((e) => e.trace_id === selectedTraceId);

  // Transform events into DAG nodes
  const nodes: GraphNode[] = currentTraceEvents.map((e) => ({
    id: e.event_id,
    event_id: e.event_id,
    trace_id: e.trace_id,
    operation_name: e.operation_name,
    tool_name: e.tool?.name,
    tool_category: e.tool?.category,
    hasFastpathMatch: Boolean(e.detections?.fastpath?.matched),
    hasPolicyViolation: Boolean(e.detections?.policy?.allowed === false),
    hasJudgeDivergence: Boolean(e.detections?.judge?.is_anomalous),
    payload: e.payload_content,
    rawEvent: e,
  }));

  // Apply semantic compression if enabled
  const displayNodes = React.useMemo(() => {
    if (!isCompressed || nodes.length <= 1) return nodes;

    const compressed: GraphNode[] = [];
    let currentBatch: GraphNode[] = [];

    for (let i = 0; i < nodes.length; i++) {
      const curr = nodes[i];
      const isBenign = !curr.hasFastpathMatch && !curr.hasPolicyViolation && !curr.hasJudgeDivergence;

      if (isBenign && currentBatch.length > 0) {
        const prev = currentBatch[currentBatch.length - 1];
        const sameOp = prev.operation_name === curr.operation_name;
        const sameTool = prev.tool_category === curr.tool_category;

        if (sameOp && sameTool) {
          currentBatch.push(curr);
          continue;
        }
      }

      if (currentBatch.length > 1) {
        compressed.push({
          ...currentBatch[0],
          id: `meta-${currentBatch[0].id}`,
          isMetaNode: true,
          compressedCount: currentBatch.length,
        });
      } else if (currentBatch.length === 1) {
        compressed.push(currentBatch[0]);
      }

      if (isBenign) {
        currentBatch = [curr];
      } else {
        currentBatch = [];
        compressed.push(curr);
      }
    }

    if (currentBatch.length > 1) {
      compressed.push({
        ...currentBatch[0],
        id: `meta-${currentBatch[0].id}`,
        isMetaNode: true,
        compressedCount: currentBatch.length,
      });
    } else if (currentBatch.length === 1) {
      compressed.push(currentBatch[0]);
    }

    return compressed;
  }, [nodes, isCompressed]);

  return (
    <div className="graph-container">
      {/* Controls Bar */}
      <div className="graph-header">
        <div className="graph-title-group">
          <Network className="section-icon text-cyan" />
          <h2 className="section-title">Causal Attack Graph (NetworkX DAG)</h2>
        </div>

        <div className="graph-controls">
          {/* Trace ID Selector */}
          <div className="trace-selector">
            <span className="selector-label">TRACE ID:</span>
            <select
              value={selectedTraceId}
              onChange={(e) => onSelectTraceId(e.target.value)}
              className="select-input"
            >
              {traceIds.length === 0 ? (
                <option value="">No trace sessions available</option>
              ) : (
                traceIds.map((tid) => (
                  <option key={tid} value={tid}>
                    {tid.slice(0, 18)}...
                  </option>
                ))
              )}
            </select>
          </div>

          {/* Compress Toggle */}
          <button
            onClick={() => setIsCompressed(!isCompressed)}
            className={`toggle-btn ${isCompressed ? 'active' : ''}`}
          >
            <Layers className="btn-icon" />
            <span>{isCompressed ? 'Semantic Compressed' : 'Raw Event DAG'}</span>
          </button>
        </div>
      </div>

      {/* Visual DAG Renderer */}
      <div className="dag-canvas">
        {displayNodes.length === 0 ? (
          <div className="empty-graph">
            <Network className="empty-icon" />
            <p>Select a trace ID above or simulate an attack chain to render the causal DAG.</p>
          </div>
        ) : (
          <div className="dag-timeline">
            {displayNodes.map((node, index) => {
              const isThreat = node.hasFastpathMatch || node.hasPolicyViolation || node.hasJudgeDivergence;

              return (
                <React.Fragment key={node.id}>
                  {index > 0 && (
                    <div className="dag-edge">
                      <div className="edge-line"></div>
                      <ArrowRight className="edge-arrow" />
                    </div>
                  )}

                  <div
                    onClick={() => onSelectNode(node.rawEvent)}
                    className={`dag-node ${node.isMetaNode ? 'meta-node' : ''} ${
                      isThreat ? 'threat-node' : 'benign-node'
                    }`}
                  >
                    {/* Node Header */}
                    <div className="node-header">
                      <span className="node-op">{node.operation_name}</span>
                      {node.isMetaNode && (
                        <span className="meta-badge">Collapsed x{node.compressedCount}</span>
                      )}
                    </div>

                    {/* Node Body */}
                    <div className="node-body">
                      {node.tool_name && (
                        <div className="tool-info">
                          <Terminal className="tool-icon" />
                          <span className="tool-name">{node.tool_name}</span>
                          {node.tool_category && (
                            <span className={`category-tag ${node.tool_category}`}>
                              {node.tool_category}
                            </span>
                          )}
                        </div>
                      )}

                      <p className="node-payload">
                        {node.payload.length > 80 ? `${node.payload.slice(0, 80)}...` : node.payload}
                      </p>
                    </div>

                    {/* Node Threat Badges */}
                    {isThreat && (
                      <div className="node-threats">
                        {node.hasFastpathMatch && (
                          <span className="threat-tag fastpath">
                            <ShieldAlert className="tag-icon" /> FastPath Match
                          </span>
                        )}
                        {node.hasPolicyViolation && (
                          <span className="threat-tag rbac">
                            <AlertTriangle className="tag-icon" /> RBAC Violation
                          </span>
                        )}
                        {node.hasJudgeDivergence && (
                          <span className="threat-tag judge">
                            <Cpu className="tag-icon" /> SLM Intent Divergent
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                </React.Fragment>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
