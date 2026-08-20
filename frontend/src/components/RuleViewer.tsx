import React, { useEffect, useState } from 'react';
import {
  Sliders,
  ShieldCheck,
  FileCode,
  CheckCircle2,
  PauseCircle,
  ShieldAlert,
  Eye,
  RefreshCw,
  Plus,
  Edit3,
  Trash2,
  X,
  Save,
} from 'lucide-react';
import { fetchActiveRules, toggleDryRun, createActionRule, updateActionRule, deleteActionRule } from '../api/client';

interface RuleFormState {
  id: string;
  name: string;
  tool: string;
  param: string;
  operator: string;
  value: string;
  outcome: 'block' | 'require_hitl' | 'log_and_allow' | 'allow';
  reason: string;
}

const DEFAULT_FORM: RuleFormState = {
  id: '',
  name: '',
  tool: 'database_delete',
  param: 'record_count',
  operator: '>',
  value: '100',
  outcome: 'block',
  reason: '',
};

export const RuleViewer: React.FC = () => {
  const [ruleData, setRuleData] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [formData, setFormData] = useState<RuleFormState>(DEFAULT_FORM);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const loadData = async () => {
    setIsLoading(true);
    const data = await fetchActiveRules();
    setRuleData(data);
    setIsLoading(false);
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleToggleDryRun = async () => {
    await toggleDryRun();
    loadData();
  };

  const handleOpenAddModal = () => {
    setIsEditing(false);
    setFormData({
      ...DEFAULT_FORM,
      id: `rule-${Date.now().toString(36)}`,
    });
    setErrorMsg(null);
    setShowModal(true);
  };

  const handleOpenEditModal = (rule: any) => {
    setIsEditing(true);
    let valStr = '';
    if (Array.isArray(rule.condition.value)) {
      valStr = rule.condition.value.join(', ');
    } else {
      valStr = String(rule.condition.value);
    }

    setFormData({
      id: rule.id,
      name: rule.name,
      tool: rule.tool,
      param: rule.condition.param,
      operator: rule.condition.operator,
      value: valStr,
      outcome: rule.outcome,
      reason: rule.reason,
    });
    setErrorMsg(null);
    setShowModal(true);
  };

  const handleDeleteRule = async (ruleId: string) => {
    if (!window.confirm(`Are you sure you want to delete rule '${ruleId}'?`)) return;
    try {
      await deleteActionRule(ruleId);
      loadData();
    } catch (err: any) {
      alert(err.message || 'Failed to delete rule.');
    }
  };

  const handleSaveRule = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name || !formData.tool || !formData.param || !formData.reason) {
      setErrorMsg('Please fill in all required fields.');
      return;
    }

    setIsSubmitting(true);
    setErrorMsg(null);

    // Parse value appropriately
    let parsedValue: any = formData.value;
    if (formData.operator === 'in' || formData.operator === 'not_in') {
      parsedValue = formData.value.split(',').map((s) => s.trim()).filter(Boolean);
    } else if (!isNaN(Number(formData.value)) && formData.value.trim() !== '') {
      parsedValue = Number(formData.value);
    }

    const payload = {
      id: formData.id,
      name: formData.name,
      tool: formData.tool,
      condition: {
        param: formData.param,
        operator: formData.operator,
        value: parsedValue,
      },
      outcome: formData.outcome,
      reason: formData.reason,
    };

    try {
      if (isEditing) {
        await updateActionRule(formData.id, payload);
      } else {
        await createActionRule(payload);
      }
      setShowModal(false);
      loadData();
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to save rule.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="rules-viewer-container">
      <div className="section-header-wrap">
        <div className="title-group">
          <Sliders className="section-icon text-cyan" />
          <div>
            <h2>Declarative Action Guardrail Ruleset Manager</h2>
            <p className="subtitle">Visually configure pre-execution policy rules evaluated for every agent tool call.</p>
          </div>
        </div>

        <div className="header-actions">
          <button onClick={handleOpenAddModal} className="btn-add-rule">
            <Plus className="icon-sm" /> Add New Rule
          </button>
          <button
            onClick={handleToggleDryRun}
            className={`btn-toggle-mode ${ruleData?.dry_run ? 'dry-run' : 'live'}`}
          >
            {ruleData?.dry_run ? '🟡 DRY RUN MODE (SIMULATED)' : '🟢 LIVE ENFORCEMENT MODE'}
          </button>
          <button onClick={loadData} className="btn-refresh">
            <RefreshCw className="icon-sm" /> Reload
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="loading-box">
          <RefreshCw className="spinner" /> Loading Action Guardrail Rules...
        </div>
      ) : !ruleData ? (
        <div className="empty-card">Failed to load action rules.</div>
      ) : (
        <div className="rules-grid">
          {/* Rules Cards List */}
          <div className="rules-list-col">
            <div className="col-header">
              <h3 className="sub-title">Configured Action Rules ({ruleData.rules.length})</h3>
            </div>

            {ruleData.rules.length === 0 ? (
              <div className="empty-card">No rules defined. Click "Add New Rule" above to create one.</div>
            ) : (
              ruleData.rules.map((rule: any) => (
                <div key={rule.id} className={`rule-card ${rule.outcome}`}>
                  <div className="rule-card-header">
                    <div className="rule-id-wrap">
                      <FileCode className="icon-sm text-cyan" />
                      <span className="rule-id mono">{rule.id}</span>
                    </div>

                    <div className="rule-header-actions">
                      <span className={`outcome-pill ${rule.outcome}`}>
                        {rule.outcome === 'block' && <ShieldAlert className="icon-nano" />}
                        {rule.outcome === 'require_hitl' && <PauseCircle className="icon-nano" />}
                        {rule.outcome === 'log_and_allow' && <Eye className="icon-nano" />}
                        {rule.outcome === 'allow' && <CheckCircle2 className="icon-nano" />}
                        {rule.outcome.toUpperCase()}
                      </span>
                      <button
                        onClick={() => handleOpenEditModal(rule)}
                        className="btn-icon-action edit"
                        title="Edit Rule"
                      >
                        <Edit3 className="icon-nano" />
                      </button>
                      <button
                        onClick={() => handleDeleteRule(rule.id)}
                        className="btn-icon-action delete"
                        title="Delete Rule"
                      >
                        <Trash2 className="icon-nano" />
                      </button>
                    </div>
                  </div>

                  <h4 className="rule-name">{rule.name}</h4>
                  <p className="rule-reason">{rule.reason}</p>

                  <div className="rule-cond-box">
                    <span className="cond-label">PRE-EXECUTION CONDITION:</span>
                    <div className="cond-expr mono">
                      <span className="text-cyan">tool:</span> <strong>{rule.tool}</strong>
                      <br />
                      <span className="text-amber">if {rule.condition.param}</span>{' '}
                      <code>{rule.condition.operator}</code>{' '}
                      <span>{JSON.stringify(rule.condition.value)}</span>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>

          {/* YAML Live File Preview */}
          <div className="rules-yaml-col">
            <div className="yaml-card">
              <div className="yaml-header">
                <span className="mono">
                  <ShieldCheck className="icon-sm text-emerald" /> {ruleData.rules_file}
                </span>
                <span className="mode-badge">
                  {ruleData.dry_run ? 'DRY RUN ENABLED' : 'LIVE ENFORCEMENT'}
                </span>
              </div>
              <pre className="yaml-content">
{`rules:
${ruleData.rules
  .map(
    (r: any) => `  - id: ${r.id}
    name: "${r.name}"
    tool: ${r.tool}
    condition:
      param: ${r.condition.param}
      operator: "${r.condition.operator}"
      value: ${JSON.stringify(r.condition.value)}
    outcome: ${r.outcome}
    reason: "${r.reason}"`
  )
  .join('\n\n')}`}
              </pre>
            </div>
          </div>
        </div>
      )}

      {/* Non-Tech Friendly Visual Rule Editor Modal */}
      {showModal && (
        <div className="modal-backdrop">
          <div className="modal-card rule-modal">
            <div className="modal-header">
              <h3>
                <Sliders className="icon-sm text-cyan" />
                {isEditing ? `Edit Rule [${formData.id}]` : 'Create New Action Guardrail Rule'}
              </h3>
              <button onClick={() => setShowModal(false)} className="btn-close">
                <X className="icon-sm" />
              </button>
            </div>

            {errorMsg && <div className="error-banner">⚠️ {errorMsg}</div>}

            <form onSubmit={handleSaveRule} className="modal-form">
              <div className="form-row-2">
                <div className="form-group">
                  <label className="form-label">RULE ID</label>
                  <input
                    type="text"
                    value={formData.id}
                    onChange={(e) => setFormData({ ...formData, id: e.target.value })}
                    disabled={isEditing}
                    className="form-input mono"
                    placeholder="e.g. rule-db-bulk-delete"
                    required
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">RULE NAME</label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    className="form-input"
                    placeholder="e.g. Block Bulk Database Delete"
                    required
                  />
                </div>
              </div>

              <div className="form-row-2">
                <div className="form-group">
                  <label className="form-label">TARGET AGENT TOOL</label>
                  <select
                    value={formData.tool}
                    onChange={(e) => setFormData({ ...formData, tool: e.target.value })}
                    className="form-select mono"
                  >
                    <option value="database_delete">database_delete</option>
                    <option value="send_email">send_email</option>
                    <option value="read_file">read_file</option>
                    <option value="system_shell">system_shell</option>
                    <option value="custom">Custom Tool...</option>
                  </select>
                  {formData.tool === 'custom' && (
                    <input
                      type="text"
                      onChange={(e) => setFormData({ ...formData, tool: e.target.value })}
                      className="form-input mono mt-2"
                      placeholder="Type tool name..."
                      required
                    />
                  )}
                </div>

                <div className="form-group">
                  <label className="form-label">ACTION OUTCOME</label>
                  <select
                    value={formData.outcome}
                    onChange={(e) => setFormData({ ...formData, outcome: e.target.value as any })}
                    className={`form-select select-outcome ${formData.outcome}`}
                  >
                    <option value="block">🛑 BLOCK (Reject Execution)</option>
                    <option value="require_hitl">⏳ REQUIRE_HITL (Human Review Queue)</option>
                    <option value="log_and_allow">👁️ LOG_AND_ALLOW (Audit Log Only)</option>
                    <option value="allow">✅ ALLOW (Execute Tool)</option>
                  </select>
                </div>
              </div>

              <div className="form-row-3">
                <div className="form-group">
                  <label className="form-label">CONDITION PARAMETER</label>
                  <input
                    type="text"
                    value={formData.param}
                    onChange={(e) => setFormData({ ...formData, param: e.target.value })}
                    className="form-input mono"
                    placeholder="e.g. record_count or to_domain"
                    required
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">OPERATOR</label>
                  <select
                    value={formData.operator}
                    onChange={(e) => setFormData({ ...formData, operator: e.target.value })}
                    className="form-select mono"
                  >
                    <option value=">">Greater Than (&gt;)</option>
                    <option value="<">Less Than (&lt;)</option>
                    <option value="==">Equals (==)</option>
                    <option value="!=">Not Equals (!=)</option>
                    <option value="contains">Contains</option>
                    <option value="not_in">Not In Domain List (not_in)</option>
                    <option value="in">In List (in)</option>
                  </select>
                </div>

                <div className="form-group">
                  <label className="form-label">THRESHOLD VALUE</label>
                  <input
                    type="text"
                    value={formData.value}
                    onChange={(e) => setFormData({ ...formData, value: e.target.value })}
                    className="form-input mono"
                    placeholder="e.g. 100 or company.internal"
                    required
                  />
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">POLICY REASON (HUMAN EXPLANATION)</label>
                <textarea
                  value={formData.reason}
                  onChange={(e) => setFormData({ ...formData, reason: e.target.value })}
                  className="form-textarea"
                  rows={2}
                  placeholder="Explain why this rule blocks or pauses the tool call..."
                  required
                />
              </div>

              <div className="modal-actions">
                <button type="button" onClick={() => setShowModal(false)} className="btn-cancel">
                  Cancel
                </button>
                <button type="submit" disabled={isSubmitting} className="btn-save btn-submit">
                  <Save className="icon-sm" /> {isSubmitting ? 'Saving...' : 'Save Rule'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
