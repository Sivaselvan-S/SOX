import { useEffect, useState } from 'react';
import { Cpu, Plug, FileText, PauseCircle, Sliders } from 'lucide-react';
import { Header } from './components/Header';
import { AgentStudio } from './components/AgentStudio';
import { AgentConnectors } from './components/AgentConnectors';
import { ActionAuditLog } from './components/ActionAuditLog';
import { HitlQueue } from './components/HitlQueue';
import { RuleViewer } from './components/RuleViewer';
import { NodeDetailModal } from './components/NodeDetailModal';
import {
  checkHealth,
  fetchAuditLog,
  fetchPendingHitl,
  connectIncidentStream,
  simulateAttackChain,
} from './api/client';
import type { SystemHealth, TelemetryEvent } from './types/telemetry';
import type { AuditRecord } from './api/client';

export function App() {
  const [activeTab, setActiveTab] = useState<'studio' | 'audit' | 'hitl' | 'rules' | 'connectors'>('studio');
  const [health, setHealth] = useState<SystemHealth>({ status: 'checking', project: 'LongWall AI' });
  const [wsConnected, setWsConnected] = useState(false);
  const [auditRecords, setAuditRecords] = useState<AuditRecord[]>([]);
  const [pendingHitlRecords, setPendingHitlRecords] = useState<AuditRecord[]>([]);
  const [selectedNodeEvent, setSelectedNodeEvent] = useState<TelemetryEvent | null>(null);
  const [isSimulating, setIsSimulating] = useState(false);

  // Poll backend health, audit log, and pending HITL records
  const loadData = async () => {
    const h = await checkHealth();
    setHealth(h);
    const logs = await fetchAuditLog();
    setAuditRecords(logs);
    const hitls = await fetchPendingHitl();
    setPendingHitlRecords(hitls);
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 10000);

    // WebSocket real-time incident listener
    const cleanupWs = connectIncidentStream(
      () => {
        loadData();
      },
      (connected) => setWsConnected(connected)
    );

    return () => {
      clearInterval(interval);
      cleanupWs();
    };
  }, []);

  const handleSimulateAttack = async () => {
    setIsSimulating(true);
    try {
      await simulateAttackChain();
      await loadData();
      setActiveTab('audit');
    } catch (err) {
      console.error('Simulation failed:', err);
    } finally {
      setIsSimulating(false);
    }
  };

  return (
    <div className="app-shell">
      {/* Header & Metrics Strip */}
      <Header
        health={health}
        wsConnected={wsConnected}
        auditRecords={auditRecords}
        pendingHitlRecords={pendingHitlRecords}
        onSimulateAttack={handleSimulateAttack}
        isSimulating={isSimulating}
        onRefresh={loadData}
      />

      {/* Navigation Tabs */}
      <nav className="nav-tabs-bar">
        <button
          onClick={() => setActiveTab('studio')}
          className={`nav-tab ${activeTab === 'studio' ? 'active' : ''}`}
        >
          <Cpu className="tab-icon" />
          <span>Action Guardrail Tester</span>
        </button>

        <button
          onClick={() => setActiveTab('audit')}
          className={`nav-tab ${activeTab === 'audit' ? 'active' : ''}`}
        >
          <FileText className="tab-icon" />
          <span>Action Audit Log</span>
          {auditRecords.length > 0 && (
            <span className="badge-count cyan">{auditRecords.length}</span>
          )}
        </button>

        <button
          onClick={() => setActiveTab('hitl')}
          className={`nav-tab ${activeTab === 'hitl' ? 'active' : ''}`}
        >
          <PauseCircle className="tab-icon" />
          <span>HITL Approval Queue</span>
          {pendingHitlRecords.length > 0 && (
            <span className="badge-count amber">{pendingHitlRecords.length}</span>
          )}
        </button>

        <button
          onClick={() => setActiveTab('rules')}
          className={`nav-tab ${activeTab === 'rules' ? 'active' : ''}`}
        >
          <Sliders className="tab-icon" />
          <span>Declarative Rules (`action_rules.yaml`)</span>
        </button>

        <button
          onClick={() => setActiveTab('connectors')}
          className={`nav-tab ${activeTab === 'connectors' ? 'active' : ''}`}
        >
          <Plug className="tab-icon" />
          <span>Agent Connections</span>
        </button>
      </nav>

      {/* Main Content View (Tab-Persistent State) */}
      <main className="workspace-main">
        <div style={{ display: activeTab === 'studio' ? 'block' : 'none' }}>
          <AgentStudio onEventSubmitted={loadData} />
        </div>

        <div style={{ display: activeTab === 'audit' ? 'block' : 'none' }}>
          <ActionAuditLog />
        </div>

        <div style={{ display: activeTab === 'hitl' ? 'block' : 'none' }}>
          <HitlQueue />
        </div>

        <div style={{ display: activeTab === 'rules' ? 'block' : 'none' }}>
          <RuleViewer />
        </div>

        <div style={{ display: activeTab === 'connectors' ? 'block' : 'none' }}>
          <AgentConnectors />
        </div>
      </main>

      {/* Node Detail Drawer Modal */}
      {selectedNodeEvent && (
        <NodeDetailModal
          event={selectedNodeEvent}
          onClose={() => setSelectedNodeEvent(null)}
        />
      )}
    </div>
  );
}
