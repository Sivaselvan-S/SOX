import React from 'react';
import { ShieldCheck, Lock, Cpu } from 'lucide-react';

export const RbacMatrix: React.FC = () => {
  const policies = [
    {
      identity: 'spiffe://prod/read-only-agent',
      role: 'Read-Only Agent',
      allowed: ['READ'],
      description: 'Allowed to perform search & query operations only. State-changing sinks blocked.',
    },
    {
      identity: 'spiffe://prod/finance-agent',
      role: 'Finance Processing Agent',
      allowed: ['READ', 'DATABASE_WRITE'],
      description: 'Permitted to query and write financial database records.',
    },
    {
      identity: 'spiffe://prod/egress-agent',
      role: 'Export & Egress Agent',
      allowed: ['READ', 'FILE_EGRESS'],
      description: 'Permitted to generate files and export metrics.',
    },
    {
      identity: 'spiffe://prod/admin-agent',
      role: 'System Admin Orchestrator',
      allowed: ['READ', 'DATABASE_WRITE', 'FILE_EGRESS', 'SYSTEM_EXEC'],
      description: 'Full administrative access across all tool categories.',
    },
  ];

  const fastpathRules = [
    {
      id: 'FP-101',
      name: 'DIRECT_PROMPT_INJECTION',
      pattern: 'ignore previous instructions | system override | DAN mode',
      latency: '< 0.5 ms',
      action: 'Flag & Trigger Out-of-band SLM Judge',
    },
    {
      id: 'FP-102',
      name: 'UNAUTHORIZED_SHELL_EXEC',
      pattern: 'exec /bin/sh | cat /etc/passwd | drop database | /etc/shadow',
      latency: '< 0.3 ms',
      action: 'Block Instantly + Raise High/Critical Threat',
    },
    {
      id: 'FP-103',
      name: 'NETWORK_EGRESS_SHELL',
      pattern: 'curl http | wget http | nc -e /bin/bash | > /dev/tcp',
      latency: '< 0.4 ms',
      action: 'Immediate Tier 2/3 SOAR Containment Trigger',
    },
  ];

  return (
    <div className="rbac-matrix-container">
      <div className="section-header-wrap">
        <div className="title-group">
          <Lock className="section-icon text-amber" />
          <h2>Agent Identity RBAC & FastPath Guardrails Matrix</h2>
        </div>
      </div>

      <div className="rbac-grid">
        {/* SPIFFE Identity URN Policies */}
        <div className="matrix-card">
          <h3 className="card-title">
            <ShieldCheck className="card-title-icon text-success" /> Registered SPIFFE URN RBAC Policies
          </h3>
          <div className="policies-table">
            {policies.map((p) => (
              <div key={p.identity} className="policy-row">
                <div className="policy-identity-wrap">
                  <span className="urn-title">{p.identity}</span>
                  <span className="role-subtitle">{p.role}</span>
                </div>
                <div className="policy-categories">
                  {p.allowed.map((cat) => (
                    <span key={cat} className={`cat-pill ${cat.toLowerCase()}`}>
                      {cat}
                    </span>
                  ))}
                </div>
                <p className="policy-desc">{p.description}</p>
              </div>
            ))}
          </div>
        </div>

        {/* FastPath Guardrail Rules */}
        <div className="matrix-card">
          <h3 className="card-title">
            <Cpu className="card-title-icon text-cyan" /> Sub-5ms Synchronous FastPath Guardrails
          </h3>
          <div className="rules-list">
            {fastpathRules.map((rule) => (
              <div key={rule.id} className="rule-card">
                <div className="rule-header">
                  <span className="rule-id">{rule.id}</span>
                  <span className="rule-name">{rule.name}</span>
                  <span className="rule-latency">{rule.latency}</span>
                </div>
                <code className="rule-pattern">{rule.pattern}</code>
                <p className="rule-action">
                  <strong>Enforcement:</strong> {rule.action}
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
