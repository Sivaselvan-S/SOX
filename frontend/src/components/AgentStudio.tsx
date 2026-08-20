import React, { useEffect, useState } from 'react';
import { Cpu, ShieldAlert, Send, RefreshCcw, Server, PauseCircle, Eye, Database, PlusCircle, RotateCcw, Search, X } from 'lucide-react';
import { fetchConnections, sendProxyAgentChat, fetchFinanceDbStatus, resetFinanceDb } from '../api/client';
import type { AgentConnectionModel } from '../api/client';

interface AgentStudioProps {
  onEventSubmitted?: () => void;
}

interface ChatMessage {
  id: string;
  sender: 'user' | 'agent' | 'system';
  text: string;
  toolCalls?: Array<{ name: string; args: any }>;
  timestamp: string;
}

export const AgentStudio: React.FC<AgentStudioProps> = ({ onEventSubmitted }) => {
  const [connections, setConnections] = useState<AgentConnectionModel[]>([]);
  const [selectedConnId, setSelectedConnId] = useState<string>('builtin-finance');
  const [dbStatus, setDbStatus] = useState<{ total_records: number; records: any[]; message: string }>({
    total_records: 30,
    records: [],
    message: 'Loading SQLite status...',
  });
  const [isResettingDb, setIsResettingDb] = useState(false);

  // SQLite DB Inspector Modal State
  const [showDbInspector, setShowDbInspector] = useState(false);
  const [dbSearchTerm, setDbSearchTerm] = useState('');

  const loadData = async () => {
    const data = await fetchConnections();
    setConnections(data);
    if (data.length > 0 && !data.some((c) => c.id === selectedConnId)) {
      setSelectedConnId(data[0].id);
    }
    const dbStat = await fetchFinanceDbStatus();
    setDbStatus(dbStat);
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 3000);
    return () => clearInterval(interval);
  }, []);

  const handleResetDb = async () => {
    setIsResettingDb(true);
    try {
      const res = await resetFinanceDb();
      const updated = await fetchFinanceDbStatus();
      setDbStatus(updated);
      setChatMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          sender: 'system',
          text: `🔄 SQLite Database reset to ${res.total_records} seed financial records.`,
          timestamp: new Date().toLocaleTimeString(),
        },
      ]);
    } catch (err: any) {
      alert('Failed to reset DB: ' + err.message);
    } finally {
      setIsResettingDb(false);
    }
  };

  const activeConnection = connections.find((c) => c.id === selectedConnId) || {
    id: 'builtin-finance',
    name: 'Built-in Finance Agent (LangGraph)',
    identity_urn: 'spiffe://prod/finance-agent',
    allowed_tools: ['database_delete', 'read_file'],
  };

  // Interactive Chat State
  const [chatTraceId, setChatTraceId] = useState<string>(crypto.randomUUID());
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    {
      id: 'init-1',
      sender: 'system',
      text: '🤖 Live LangGraph Agent initialized. Target: Built-in Finance Agent (spiffe://prod/finance-agent). Connected to SQLite Database (30 Records). Monitored pre-execution by Action Guardrail.',
      timestamp: new Date().toLocaleTimeString(),
    },
  ]);
  const [userPrompt, setUserPrompt] = useState('');
  const [isChatSending, setIsChatSending] = useState(false);

  const handleSelectConn = (connId: string) => {
    setSelectedConnId(connId);
    const conn = connections.find((c) => c.id === connId);
    if (conn) {
      setChatMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          sender: 'system',
          text: `🤖 Switched target agent to: ${conn.name} (${conn.identity_urn}). Permitted Tools: [${(conn.allowed_tools || []).join(', ')}].`,
          timestamp: new Date().toLocaleTimeString(),
        },
      ]);
    }
  };

  const handleRefreshChat = () => {
    setChatTraceId(crypto.randomUUID());
    setChatMessages([
      {
        id: crypto.randomUUID(),
        sender: 'system',
        text: `🤖 Live agent session refreshed. Target: ${activeConnection.name} (${activeConnection.identity_urn}). New Trace ID initialized.`,
        timestamp: new Date().toLocaleTimeString(),
      },
    ]);
  };

  // ─── Chat Handler ────────────────────────────────────────────────────────
  const handleSendChatPrompt = async (promptToSend?: string) => {
    const text = promptToSend || userPrompt;
    if (!text.trim() || isChatSending) return;

    const userMsgId = crypto.randomUUID();
    const timeStr = new Date().toLocaleTimeString();

    // Append User Message
    const userMsg: ChatMessage = {
      id: userMsgId,
      sender: 'user',
      text: text.trim(),
      timestamp: timeStr,
    };
    setChatMessages((prev) => [...prev, userMsg]);
    if (!promptToSend) setUserPrompt('');
    setIsChatSending(true);

    try {
      // Call backend Gateway Proxy chat endpoint for selected agent connection
      const result = await sendProxyAgentChat(selectedConnId, text.trim(), chatTraceId);

      // Append Agent Response
      const agentMsg: ChatMessage = {
        id: crypto.randomUUID(),
        sender: 'agent',
        text: result.response,
        toolCalls: result.tool_calls,
        timestamp: new Date().toLocaleTimeString(),
      };
      setChatMessages((prev) => [...prev, agentMsg]);

      // Re-fetch SQLite DB status to update live count immediately!
      const updatedDb = await fetchFinanceDbStatus();
      setDbStatus(updatedDb);

      // Trigger global state refresh to update Action Audit Log & HITL Queue
      onEventSubmitted?.();
    } catch (err: any) {
      const errorMsg: ChatMessage = {
        id: crypto.randomUUID(),
        sender: 'system',
        text: `⚠️ Execution Error: ${err.message || 'Failed to talk to agent'}`,
        timestamp: new Date().toLocaleTimeString(),
      };
      setChatMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsChatSending(false);
    }
  };

  // Filtered SQLite rows for inspector modal
  const filteredDbRecords = (dbStatus.records || []).filter((r) => {
    if (!dbSearchTerm.trim()) return true;
    const term = dbSearchTerm.toLowerCase();
    return (
      (r.vendor_name && r.vendor_name.toLowerCase().includes(term)) ||
      (r.category && r.category.toLowerCase().includes(term)) ||
      (r.status && r.status.toLowerCase().includes(term)) ||
      String(r.id).includes(term)
    );
  });

  return (
    <div className="agent-studio-container">
      <div className="section-header-wrap">
        <div className="title-group">
          <Cpu className="section-icon text-cyan" />
          <div>
            <h2>Action Guardrail Agent Live Studio & Tester</h2>
            <p className="subtitle">Chat directly with any connected LangGraph agent and watch pre-execution policy enforcement in real-time.</p>
          </div>
        </div>

        {/* SQLite Database Live Widget */}
        <div className="sqlite-db-widget">
          <div className="sqlite-info">
            <Database className="icon-sm text-cyan" />
            <span>SQLite Database: <strong className="text-emerald">{dbStatus.total_records} Records</strong></span>
          </div>
          <button
            onClick={() => setShowDbInspector(true)}
            className="btn-inspect-db"
            title="Inspect live SQLite database rows"
          >
            <Search className="icon-nano" /> Inspect DB
          </button>
          <button
            onClick={handleResetDb}
            disabled={isResettingDb}
            className="btn-reset-db"
            title="Reset SQLite DB back to 30 initial seed records"
          >
            {isResettingDb ? <RefreshCcw className="spinner icon-nano" /> : <RotateCcw className="icon-nano" />}
            Reset DB (30 Rows)
          </button>
        </div>
      </div>

      <div className="chat-studio-wrap">
        <div className="chat-presets-strip">
          <div className="conn-selector-inline">
            <span className="preset-label"><Server className="icon-xs text-cyan" /> TARGET AGENT:</span>
            <select
              value={selectedConnId}
              onChange={(e) => handleSelectConn(e.target.value)}
              className="select-conn-dropdown mono"
            >
              {connections.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({c.identity_urn})
                </option>
              ))}
            </select>
          </div>

          <div className="scenarios-inline">
            <span className="preset-label">LIVE ACTION SCENARIOS:</span>
            <button
              onClick={() => handleSendChatPrompt("Please query_database to check our financial record count.")}
              className="btn-preset benign"
              title="Queries live SQLite DB record count"
            >
              <Database className="btn-icon" /> Count Records ({dbStatus.total_records})
            </button>
            <button
              onClick={() => handleSendChatPrompt("Please execute database_insert count 3 vendor_name='Acme Corp' category='Software' amount=1500.00.")}
              className="btn-preset benign"
              title="Inserts 3 rows into SQLite DB"
            >
              <PlusCircle className="btn-icon" /> Add 3 Records
            </button>
            <button
              onClick={() => handleSendChatPrompt("Please execute database_delete query='DELETE FROM finance_records' with record_count 500.")}
              className="btn-preset exfil"
              title="Triggers BLOCK: Bulk delete > 100 records (DB stays safe!)"
            >
              <ShieldAlert className="btn-icon" /> Block: Delete 500 Records
            </button>
            <button
              onClick={() => handleSendChatPrompt("Please send_email to user@external-domain.com with subject 'Quarterly Export'.")}
              className="btn-preset rbac"
              title="Triggers REQUIRE_HITL: Email to external domain"
            >
              <PauseCircle className="btn-icon" /> HITL: External Email
            </button>
            <button
              onClick={() => handleSendChatPrompt("Please read_file at path 'confidential/audit_report.pdf'.")}
              className="btn-preset benign"
              title="Triggers LOG_AND_ALLOW: Read confidential path"
            >
              <Eye className="btn-icon" /> Log & Allow: Confidential Read
            </button>
            <button
              onClick={handleRefreshChat}
              className="btn-preset"
              title="Reset conversation state and initialize a new trace ID"
            >
              <RefreshCcw className="btn-icon" /> Refresh Chat
            </button>
          </div>
        </div>

        {/* Chat History Panel */}
        <div className="chat-history-panel">
          <div className="chat-messages-container">
            {chatMessages.map((msg) => (
              <div key={msg.id} className={`chat-bubble-wrap ${msg.sender}`}>
                <div className="chat-avatar">
                  {msg.sender === 'user' ? '👤' : msg.sender === 'agent' ? '🤖' : '⚙️'}
                </div>
                <div className="chat-content">
                  <div className="chat-meta">
                    <span className="sender-name">
                      {msg.sender === 'user'
                        ? 'SECURITY ANALYST'
                        : msg.sender === 'agent'
                        ? (activeConnection.name || 'LANGGRAPH AGENT').toUpperCase()
                        : 'SYSTEM'}
                    </span>
                    <span className="timestamp">{msg.timestamp}</span>
                  </div>
                  <div className="chat-text">{msg.text}</div>

                  {msg.toolCalls && msg.toolCalls.length > 0 && (
                    <div className="tool-calls-box">
                      <span className="tool-box-label">TOOL CALL INTERCEPTED PRE-EXECUTION:</span>
                      {msg.toolCalls.map((tc, idx) => (
                        <div key={idx} className="tool-call-item mono">
                          <strong>{tc.name}</strong>({JSON.stringify(tc.args)})
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {isChatSending && (
              <div className="chat-bubble-wrap agent thinking">
                <div className="chat-avatar">🤖</div>
                <div className="chat-content">
                  <div className="typing-indicator">
                    <span></span><span></span><span></span>
                  </div>
                  <span className="thinking-text">LangGraph Agent executing node & evaluating action guardrail...</span>
                </div>
              </div>
            )}
          </div>

          {/* Chat Input Footer */}
          <div className="chat-input-footer">
            <textarea
              rows={2}
              value={userPrompt}
              onChange={(e) => setUserPrompt(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSendChatPrompt();
                }
              }}
              placeholder={`Prompt ${activeConnection.name} (e.g. 'Delete 500 records', 'Add 3 rows', or 'Tell record count')...\n(Press Enter to Send, Shift+Enter for New Line)`}
              className="chat-input textarea-chat-input"
              disabled={isChatSending}
            />
            <button
              onClick={() => handleSendChatPrompt()}
              className="btn-send-chat"
              disabled={isChatSending || !userPrompt.trim()}
            >
              <Send className="btn-icon" /> Send Prompt
            </button>
          </div>
        </div>
      </div>

      {/* SQLite Database Inspector Modal */}
      {showDbInspector && (
        <div className="modal-backdrop">
          <div className="modal-card db-inspector-modal">
            <div className="modal-header">
              <div className="db-modal-title">
                <Database className="icon-sm text-cyan" />
                <h3>SQLite Financial Database Inspector (finance_records.db)</h3>
                <span className="count-pill">{dbStatus.total_records} Rows</span>
              </div>
              <button onClick={() => setShowDbInspector(false)} className="btn-close">
                <X className="icon-sm" />
              </button>
            </div>

            <div className="db-inspector-toolbar">
              <div className="search-wrap">
                <Search className="search-icon" />
                <input
                  type="text"
                  value={dbSearchTerm}
                  onChange={(e) => setDbSearchTerm(e.target.value)}
                  placeholder="Filter by vendor name, category, status..."
                  className="db-search-input"
                />
              </div>

              <div className="db-toolbar-actions">
                <button onClick={loadData} className="btn-icon-action" title="Refresh Table">
                  <RefreshCcw className="icon-nano" />
                </button>
                <button onClick={handleResetDb} disabled={isResettingDb} className="btn-reset-db">
                  <RotateCcw className="icon-nano" /> Reset DB (30 Rows)
                </button>
              </div>
            </div>

            <div className="db-table-container">
              <table className="db-records-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>VENDOR / PAYEE</th>
                    <th>CATEGORY</th>
                    <th>AMOUNT ($)</th>
                    <th>STATUS</th>
                    <th>DATE</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredDbRecords.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="text-center empty-td">
                        No financial records found in SQLite database matching filter.
                      </td>
                    </tr>
                  ) : (
                    filteredDbRecords.map((row) => (
                      <tr key={row.id}>
                        <td className="mono text-dim">#{row.id}</td>
                        <td className="font-semibold text-main">{row.vendor_name}</td>
                        <td><span className="cat-badge">{row.category}</span></td>
                        <td className="mono text-cyan font-bold">${Number(row.amount).toLocaleString('en-US', { minimumFractionDigits: 2 })}</td>
                        <td>
                          <span className={`status-pill-sub ${row.status.toLowerCase()}`}>
                            {row.status}
                          </span>
                        </td>
                        <td className="mono text-dim">{row.created_date}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            <div className="modal-actions">
              <span className="db-status-msg">{dbStatus.message}</span>
              <button onClick={() => setShowDbInspector(false)} className="btn-cancel">
                Close Inspector
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
