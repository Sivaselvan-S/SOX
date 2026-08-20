import React, { useEffect, useState } from 'react';
import { Plug, Plus, Trash2, ShieldCheck, Server, Wrench, ExternalLink, RefreshCw, X, Edit3, CheckSquare, Square } from 'lucide-react';
import { fetchConnections, createConnection, updateConnection, deleteConnection } from '../api/client';
import type { AgentConnectionModel } from '../api/client';

const ALL_SYSTEM_TOOLS = [
  { id: 'database_delete', label: 'database_delete', desc: 'Delete database rows (Subject to max 100 record threshold rule)' },
  { id: 'database_insert', label: 'database_insert', desc: 'Insert new database records' },
  { id: 'query_database', label: 'query_database', desc: 'Read database record count and inspect schema' },
  { id: 'send_email', label: 'send_email', desc: 'Send outbound emails (Subject to external domain HITL rule)' },
  { id: 'read_file', label: 'read_file', desc: 'Read filesystem documents (Subject to confidential path log rule)' },
  { id: 'system_shell', label: 'system_shell', desc: 'Execute operating system shell commands' },
];

export const AgentConnectors: React.FC = () => {
  const [connections, setConnections] = useState<AgentConnectionModel[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);

  // Edit Modal State
  const [editingConn, setEditingConn] = useState<AgentConnectionModel | null>(null);
  const [editName, setEditName] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [editTools, setEditTools] = useState<string[]>([]);
  const [editMode, setEditMode] = useState('strict_enforce');
  const [isUpdating, setIsUpdating] = useState(false);

  // New Connection Form State
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [targetUrl, setTargetUrl] = useState('http://127.0.0.1:8000/api/v1/agent/chat');
  const [identityUrn, setIdentityUrn] = useState('spiffe://prod/read-only-agent');
  const [allowedTools, setAllowedTools] = useState<string[]>(['read_file']);
  const [enforcementMode, setEnforcementMode] = useState<string>('strict_enforce');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [formError, setFormError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const loadData = async () => {
    setIsLoading(true);
    const data = await fetchConnections();
    setConnections(data);
    setIsLoading(false);
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleToggleToolNew = (tool: string) => {
    if (allowedTools.includes(tool)) {
      setAllowedTools(allowedTools.filter((t) => t !== tool));
    } else {
      setAllowedTools([...allowedTools, tool]);
    }
  };

  const handleToggleToolEdit = (tool: string) => {
    if (editTools.includes(tool)) {
      setEditTools(editTools.filter((t) => t !== tool));
    } else {
      setEditTools([...editTools, tool]);
    }
  };

  const openEditModal = (conn: AgentConnectionModel) => {
    setEditingConn(conn);
    setEditName(conn.name);
    setEditDescription(conn.description || '');
    setEditTools(conn.allowed_tools || []);
    setEditMode(conn.enforcement_mode || 'strict_enforce');
    setFormError(null);
  };

  const handleUpdate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingConn) return;
    setIsUpdating(true);
    setFormError(null);

    try {
      await updateConnection(editingConn.id, {
        name: editName,
        description: editDescription,
        allowed_tools: editTools,
        enforcement_mode: editMode,
      });

      setEditingConn(null);
      loadData();
    } catch (err: any) {
      setFormError(err.message || 'Failed to update connection.');
    } finally {
      setIsUpdating(false);
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name || !targetUrl) return;
    setIsSubmitting(true);
    setFormError(null);

    try {
      await createConnection({
        name,
        description,
        target_url: targetUrl,
        identity_urn: identityUrn,
        allowed_tools: allowedTools,
        enforcement_mode: enforcementMode,
      });

      setShowModal(false);
      setName('');
      setDescription('');
      loadData();
    } catch (err: any) {
      setFormError(err.message || 'Failed to register connection.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const confirmDelete = async (id: string) => {
    try {
      await deleteConnection(id);
      setDeletingId(null);
      loadData();
    } catch (err: any) {
      setFormError('Failed to remove connection.');
    }
  };

  return (
    <div className="connectors-container">
      <div className="section-header-wrap">
        <div className="title-group">
          <Plug className="section-icon text-cyan" />
          <div>
            <h2>Action Guardrail Agent Connections Hub</h2>
            <p className="subtitle">Connect external LangGraph agents (Docker, Cloud, HTTP endpoints) and manage tool allowances governed by LongWall AI.</p>
          </div>
        </div>

        <button onClick={() => setShowModal(true)} className="btn-add-conn">
          <Plus className="btn-icon" /> Connect New Agent
        </button>
      </div>

      {isLoading ? (
        <div className="loading-box">
          <RefreshCw className="spinner" /> Loading Agent Connections...
        </div>
      ) : (
        <div className="conn-grid">
          {connections.map((conn) => (
            <div key={conn.id} className="conn-card">
              <div className="conn-card-header">
                <div className="conn-title-wrap">
                  <Server className="conn-icon text-cyan" />
                  <div>
                    <h3 className="conn-name">{conn.name}</h3>
                    <span className="conn-id mono">{conn.id}</span>
                  </div>
                </div>
                <div className="conn-status-badge active">
                  <span className="dot"></span> {(conn.enforcement_mode || 'STRICT_ENFORCE').toUpperCase()}
                </div>
              </div>

              <p className="conn-desc">{conn.description || 'No description provided.'}</p>

              <div className="conn-details">
                <div className="detail-item">
                  <span className="detail-label">ENDPOINT TARGET URL:</span>
                  <div className="url-box mono">
                    <ExternalLink className="icon-xs" /> {conn.target_url}
                  </div>
                </div>

                <div className="detail-item">
                  <span className="detail-label">SPIFFE SECURITY IDENTITY:</span>
                  <div className="spiffe-box mono">
                    <ShieldCheck className="icon-xs text-amber" /> {conn.identity_urn}
                  </div>
                </div>

                <div className="detail-item">
                  <span className="detail-label">PERMITTED AGENT TOOLS ({conn.allowed_tools?.length || 0}):</span>
                  <div className="roles-tags">
                    {(conn.allowed_tools || []).length === 0 ? (
                      <span className="text-dim font-mono text-xs">No tools permitted</span>
                    ) : (
                      (conn.allowed_tools || []).map((tool) => (
                        <span key={tool} className="role-pill">
                          <Wrench className="icon-nano" /> {tool}
                        </span>
                      ))
                    )}
                  </div>
                </div>
              </div>

              <div className="conn-card-footer">
                <button onClick={() => openEditModal(conn)} className="btn-edit-conn">
                  <Edit3 className="icon-sm" /> Edit Capabilities
                </button>
                {!conn.id.startsWith('builtin') && (
                  deletingId === conn.id ? (
                    <div className="inline-confirm-row">
                      <button onClick={() => confirmDelete(conn.id)} className="btn-confirm-yes">
                        Confirm Delete
                      </button>
                      <button onClick={() => setDeletingId(null)} className="btn-confirm-no">
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <button onClick={() => setDeletingId(conn.id)} className="btn-delete-conn">
                      <Trash2 className="icon-sm" /> Remove
                    </button>
                  )
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Edit Connection Modal */}
      {editingConn && (
        <div className="modal-backdrop">
          <div className="modal-card">
            <div className="modal-header">
              <h3>
                <Edit3 className="icon-sm text-cyan" /> Edit Agent Capabilities & Tool Allowances
              </h3>
              <button onClick={() => setEditingConn(null)} className="btn-close">
                <X className="icon-sm" />
              </button>
            </div>

            <form onSubmit={handleUpdate} className="modal-form">
              {formError && <div className="error-banner">⚠️ {formError}</div>}

              <div className="form-group">
                <label className="form-label">AGENT NAME / LABEL:</label>
                <input
                  type="text"
                  required
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="form-input"
                />
              </div>

              <div className="form-group">
                <label className="form-label">DESCRIPTION:</label>
                <input
                  type="text"
                  value={editDescription}
                  onChange={(e) => setEditDescription(e.target.value)}
                  className="form-input"
                />
              </div>

              <div className="form-group">
                <label className="form-label">PERMITTED TOOL ALLOWANCES (CHECK TO ALLOW):</label>
                <p className="help-text">Select which system tools this agent identity is allowed to invoke.</p>
                <div className="tools-checklist-grid">
                  {ALL_SYSTEM_TOOLS.map((t) => {
                    const isChecked = editTools.includes(t.id);
                    return (
                      <div
                        key={t.id}
                        onClick={() => handleToggleToolEdit(t.id)}
                        className={`tool-check-card ${isChecked ? 'selected' : ''}`}
                      >
                        <div className="tool-check-header">
                          {isChecked ? <CheckSquare className="icon-sm text-cyan" /> : <Square className="icon-sm text-dim" />}
                          <strong className="mono">{t.label}</strong>
                        </div>
                        <span className="tool-check-desc">{t.desc}</span>
                      </div>
                    );
                  })}
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">ACTION GUARDRAIL ENFORCEMENT MODE:</label>
                <select
                  value={editMode}
                  onChange={(e) => setEditMode(e.target.value)}
                  className="form-select mono"
                >
                  <option value="strict_enforce">STRICT ENFORCE (Block violations pre-execution)</option>
                  <option value="dry_run">DRY RUN (Log policy decisions without blocking)</option>
                  <option value="disabled">DISABLED (Bypass guardrail checks)</option>
                </select>
              </div>
            </form>

            <div className="modal-footer-fixed">
              <button type="button" onClick={() => setEditingConn(null)} className="btn-cancel">
                Cancel
              </button>
              <button onClick={handleUpdate} disabled={isUpdating} className="btn-submit">
                {isUpdating ? <RefreshCw className="spinner btn-icon" /> : <CheckSquare className="btn-icon" />}
                Save Capabilities
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Add Connection Modal */}
      {showModal && (
        <div className="modal-backdrop">
          <div className="modal-card">
            <div className="modal-header">
              <h3>
                <Plug className="icon-sm text-cyan" /> Connect New Remote Agent Endpoint
              </h3>
              <button onClick={() => setShowModal(false)} className="btn-close">
                <X className="icon-sm" />
              </button>
            </div>

            <form onSubmit={handleCreate} className="modal-form">
              {formError && <div className="error-banner">⚠️ {formError}</div>}

              <div className="form-group">
                <label className="form-label">AGENT NAME / LABEL:</label>
                <input
                  type="text"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Finance & Auditing Bot (GCP Cluster)"
                  className="form-input"
                />
              </div>

              <div className="form-group">
                <label className="form-label">DESCRIPTION:</label>
                <input
                  type="text"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Brief description of the agent's function"
                  className="form-input"
                />
              </div>

              <div className="form-group">
                <label className="form-label">REMOTE ENDPOINT TARGET URL:</label>
                <input
                  type="url"
                  required
                  value={targetUrl}
                  onChange={(e) => setTargetUrl(e.target.value)}
                  placeholder="http://127.0.0.1:8000/api/v1/agent/chat"
                  className="form-input mono"
                />
              </div>

              <div className="form-group">
                <label className="form-label">SPIFFE SECURITY IDENTITY URN:</label>
                <input
                  type="text"
                  required
                  value={identityUrn}
                  onChange={(e) => setIdentityUrn(e.target.value)}
                  placeholder="spiffe://prod/finance-agent"
                  className="form-input mono"
                />
              </div>

              <div className="form-group">
                <label className="form-label">PERMITTED AGENT TOOLS (CHECK TO ALLOW):</label>
                <div className="tools-checklist-grid">
                  {ALL_SYSTEM_TOOLS.map((t) => {
                    const isChecked = allowedTools.includes(t.id);
                    return (
                      <div
                        key={t.id}
                        onClick={() => handleToggleToolNew(t.id)}
                        className={`tool-check-card ${isChecked ? 'selected' : ''}`}
                      >
                        <div className="tool-check-header">
                          {isChecked ? <CheckSquare className="icon-sm text-cyan" /> : <Square className="icon-sm text-dim" />}
                          <strong className="mono">{t.label}</strong>
                        </div>
                        <span className="tool-check-desc">{t.desc}</span>
                      </div>
                    );
                  })}
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">ENFORCEMENT MODE:</label>
                <select
                  value={enforcementMode}
                  onChange={(e) => setEnforcementMode(e.target.value)}
                  className="form-select mono"
                >
                  <option value="strict_enforce">STRICT ENFORCE (Block violations pre-execution)</option>
                  <option value="dry_run">DRY RUN (Log policy decisions without blocking)</option>
                  <option value="disabled">DISABLED (Bypass guardrail checks)</option>
                </select>
              </div>
            </form>

            <div className="modal-footer-fixed">
              <button type="button" onClick={() => setShowModal(false)} className="btn-cancel">
                Cancel
              </button>
              <button onClick={handleCreate} disabled={isSubmitting} className="btn-submit">
                {isSubmitting ? <RefreshCw className="spinner btn-icon" /> : <Plus className="btn-icon" />}
                Register Connection
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
