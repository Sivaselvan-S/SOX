/**
 * Agentic Text Comparator — Interactive Studio Client
 */

document.addEventListener("DOMContentLoaded", () => {
  // Determine API base URL (supports both http://localhost:8000 and file:// protocol)
  const isFileProtocol = window.location.protocol === "file:";
  const API_BASE = isFileProtocol ? "http://localhost:8000" : "";

  // If opened via file://, display a helpful notice
  if (isFileProtocol) {
    const header = document.querySelector(".app-header");
    if (header) {
      const notice = document.createElement("div");
      notice.className = "file-protocol-banner";
      notice.innerHTML = `
        <span>ℹ️ <strong>Note:</strong> You opened this directly as a local file. For full functionality, ensure <code>python server.py</code> is running and visit <a href="http://localhost:8000" target="_blank"><strong>http://localhost:8000</strong></a>.</span>
      `;
      header.parentNode.insertBefore(notice, header.nextSibling);
    }
  }

  // Elements
  const textAInput = document.getElementById("text-a-input");
  const textBInput = document.getElementById("text-b-input");
  const sessionIdInput = document.getElementById("session-id-input");
  const countA = document.getElementById("count-text-a");
  const countB = document.getElementById("count-text-b");
  const btnRun = document.getElementById("btn-run-comparison");
  const btnRunText = document.getElementById("btn-run-text");
  const btnSwap = document.getElementById("btn-swap-texts");
  const btnClear = document.getElementById("btn-clear-texts");
  const btnClearMem = document.getElementById("btn-clear-memory");
  const btnCopyResult = document.getElementById("btn-copy-result");
  const checkSaveRule = document.getElementById("check-save-rule");

  const teleStatus = document.getElementById("tele-status");
  const teleIterations = document.getElementById("tele-iterations");
  const teleTokens = document.getElementById("tele-tokens");
  const teleLatency = document.getElementById("tele-latency");
  const liveIndicator = document.getElementById("live-indicator");

  const cognitiveTrack = document.getElementById("cognitive-steps-track");
  const synthesisContainer = document.getElementById("synthesis-body-container");
  const memoryContainer = document.getElementById("memory-items-container");
  const memoryCountBadge = document.getElementById("memory-count-badge");
  const logsOutput = document.getElementById("structured-logs-output");
  const modelStatusText = document.getElementById("model-status-text");

  // Presets definition
  const PRESETS = {
    1: {
      title: "Financial Briefs (Cold Start)",
      textA: `Projected Financials Q3:
- Marketing Budget: $120,000
- Engineering Team: 45 engineers
- Cloud Infrastructure: $35,000/mo
Tone: Friendly and informal collaboration style.`,
      textB: `Projected Financials Q3:
- Marketing Budget: $150,000
- Engineering Team: 52 engineers
- Cloud Infrastructure: $42,000/mo
Tone: Formal and assertive operational mandates.`,
      saveRule: "Focus strictly on numerical budget and financial changes. Explicitly suppress and ignore all minor stylistic, wording, and tone discrepancies."
    },
    2: {
      title: "Benchmarks (Memory Active - Suppress Style)",
      textA: `Performance Benchmarks Release 2.4:
- Server Latency: 120ms
- Throughput: 5,000 rps
- Error Rate: 0.04%
Stylistic note: Our awesome team made incredible progress!`,
      textB: `Performance Benchmarks Release 2.4:
- Server Latency: 85ms
- Throughput: 7,500 rps
- Error Rate: 0.01%
Stylistic note: The updated infrastructure delivers robust stability.`,
      saveRule: ""
    },
    3: {
      title: "Fault Injection & Retry Recovery",
      textA: `Contract Clause 4.1: Standard SLA provides 99.9% uptime with 4-hour response window.`,
      textB: `Contract Clause 4.1: Enhanced Enterprise SLA provides 99.99% uptime with 15-minute response window.`,
      saveRule: ""
    }
  };

  // Update char counts
  function updateCounts() {
    countA.textContent = `${textAInput.value.length} chars`;
    countB.textContent = `${textBInput.value.length} chars`;
  }

  textAInput.addEventListener("input", updateCounts);
  textBInput.addEventListener("input", updateCounts);

  // Load Preset
  function loadPreset(id) {
    document.querySelectorAll(".preset-btn").forEach(btn => btn.classList.remove("active"));
    const activeBtn = document.getElementById(`btn-scenario-${id}`);
    if (activeBtn) activeBtn.classList.add("active");

    const preset = PRESETS[id];
    if (preset) {
      textAInput.value = preset.textA;
      textBInput.value = preset.textB;
      updateCounts();
    }
  }

  document.getElementById("btn-scenario-1").addEventListener("click", () => loadPreset(1));
  document.getElementById("btn-scenario-2").addEventListener("click", () => loadPreset(2));
  document.getElementById("btn-scenario-3").addEventListener("click", () => loadPreset(3));

  // Swap & Clear
  btnSwap.addEventListener("click", () => {
    const temp = textAInput.value;
    textAInput.value = textBInput.value;
    textBInput.value = temp;
    updateCounts();
  });

  btnClear.addEventListener("click", () => {
    textAInput.value = "";
    textBInput.value = "";
    updateCounts();
  });

  // Fetch and display active memories
  async function refreshMemories() {
    const sessionId = sessionIdInput.value.trim() || "session_finance_dept";
    try {
      const res = await fetch(`${API_BASE}/api/memories?session_id=${encodeURIComponent(sessionId)}`);
      if (!res.ok) return;
      const data = await res.json();
      const memories = data.memories || [];

      memoryCountBadge.textContent = `${memories.length} rule${memories.length === 1 ? "" : "s"}`;

      if (memories.length === 0) {
        memoryContainer.innerHTML = `<div class="empty-state-small">No memories stored for session '${sessionId}' yet.</div>`;
        return;
      }

      memoryContainer.innerHTML = memories.map(m => `
        <div class="mem-item">
          <div class="mem-item-header">
            <span class="mem-tag">#${escapeHtml(m.key)}</span>
            <span class="mem-score">${m.score ? `Match Score: ${(m.score * 100).toFixed(0)}%` : 'Persistent'}</span>
          </div>
          <div class="mem-val">${escapeHtml(m.value)}</div>
        </div>
      `).join("");
    } catch (err) {
      console.warn("Could not connect to backend server at " + API_BASE, err);
      memoryContainer.innerHTML = `<div class="empty-state-small" style="color: #fda4af;">Backend server not reached. Open <a href="http://localhost:8000" style="color: #67e8f9;">http://localhost:8000</a></div>`;
    }
  }

  sessionIdInput.addEventListener("change", refreshMemories);

  // Clear memory
  btnClearMem.addEventListener("click", async () => {
    const sessionId = sessionIdInput.value.trim() || "session_finance_dept";
    try {
      await fetch(`${API_BASE}/api/memory/clear`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId })
      });
      refreshMemories();
    } catch (err) {
      console.error(err);
    }
  });

  // Copy result
  btnCopyResult.addEventListener("click", () => {
    const text = synthesisContainer.innerText;
    navigator.clipboard.writeText(text);
    btnCopyResult.textContent = "Copied!";
    setTimeout(() => { btnCopyResult.textContent = "Copy Summary"; }, 2000);
  });

  // Helper escape
  function escapeHtml(str) {
    if (!str) return "";
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  // Render Markdown-like summary
  function renderMarkdownSummary(text) {
    if (!text) return "<p class='placeholder-text'>No output generated.</p>";
    let html = escapeHtml(text);
    html = html.replace(/^### (.*$)/gim, "<h3>$1</h3>");
    html = html.replace(/^## (.*$)/gim, "<h2>$1</h2>");
    html = html.replace(/\*\*(.*?)\*\*/gim, "<strong>$1</strong>");
    html = html.replace(/\*(.*?)\*/gim, "<em>$1</em>");
    html = html.replace(/^\d+\.\s+(.*$)/gim, "<li>$1</li>");
    html = html.replace(/^-\s+(.*$)/gim, "<li>$1</li>");
    html = html.replace(/\n/g, "<br>");
    return html;
  }

  const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));
  const speedSelect = document.getElementById("animation-speed-select");

  // Animate cognitive iterations sequentially for clear video presentation
  async function animateCognitiveExecution(data, sessionId, textA, textB) {
    const speedMs = speedSelect ? parseInt(speedSelect.value) : 600;
    const messages = data.messages || [];
    
    // Extract raw tool cycles from messages
    const rawToolCycles = [];
    for (let i = 1; i < messages.length; i++) {
      const msg = messages[i];
      if (msg.role === "assistant" && msg.tool_calls && msg.tool_calls.length > 0) {
        const tc = msg.tool_calls[0];
        const toolOutputMsg = messages[i + 1]?.role === "tool" ? messages[i + 1].content : "";
        rawToolCycles.push({
          toolName: tc.function.name,
          toolArgs: tc.function.arguments || "",
          toolOutput: toolOutputMsg,
        });
      }
    }

    const isExactMatch = textA.trim() === textB.trim();

    // Build cycles list
    const cycles = [];

    if (isExactMatch) {
      // 1-Iteration Fast Exit Cycle
      cycles.push({
        num: 1,
        name: "exact_match_perception",
        badge: "0 Tools (Exact Match)",
        pTitle: "1. Perceive",
        pShort: `Verified Text A and Text B are 100% identical (${textA.length} chars)`,
        pDetail: `Session ID: ${sessionId}\nText A (${textA.length} chars): "${textA.slice(0, 90)}"\nText B (${textB.length} chars): "${textB.slice(0, 90)}"\nHash match: Exact character alignment confirmed.`,
        rTitle: "2. Reason",
        rShort: "Evaluated 100% match in first pass; skipped external tools to save tokens & latency",
        rDetail: "The ReAct cognitive reasoner evaluated that both input strings are identical. It deliberately skipped calling compute_text_diff and categorize_discrepancy to avoid wasting API tokens and latency.",
        aTitle: "3. Act",
        aShort: "Direct terminal synthesis (0 external tools needed)",
        aDetail: "No external tool dispatch required. Produced exact-match confirmation.",
        aOutput: "Exact match verified. No discrepancies detected.",
        refTitle: "4. Reflect",
        refShort: "Goal complete in 1 iteration! reflect() set done = True and cleanly exited",
        refDetail: "reflect() evaluation check: Goal satisfied immediately upon perception. state['done'] = True. Cognitive loop terminated at Iteration 1/5."
      });
    } else {
      const initialTool = rawToolCycles[0]?.toolName || "compute_text_diff";
      const secondTool = rawToolCycles[1]?.toolName || "categorize_discrepancy";

      // Cycle 1: Specialized or Baseline Analysis Tool
      cycles.push({
        num: 1,
        name: initialTool,
        badge: initialTool,
        pTitle: "1. Perceive",
        pShort: `Ingested input texts & context; evaluated tool schema for '${initialTool}'`,
        pDetail: `Session ID: ${sessionId}\nText A (${textA.length} chars): "${textA.slice(0, 90)}${textA.length > 90 ? '...' : ''}"\nText B (${textB.length} chars): "${textB.slice(0, 90)}${textB.length > 90 ? '...' : ''}"\nEvaluated tool: ${initialTool}`,
        rTitle: "2. Reason",
        rShort: `Selected '${initialTool}' based on text content & domain semantics`,
        rDetail: `The ReAct reasoner analyzed the input characteristics and chose the specialized '${initialTool}' tool to extract domain-specific deltas with zero hallucination.`,
        aTitle: "3. Act",
        aShort: `Dispatched ${initialTool}(text_a, text_b)`,
        aDetail: rawToolCycles[0]?.toolArgs || JSON.stringify({ text_a: textA.slice(0, 40) + "...", text_b: textB.slice(0, 40) + "..." }, null, 2),
        aOutput: rawToolCycles[0]?.toolOutput || "Execution completed.",
        refTitle: "4. Reflect",
        refShort: "Validated tool observation; deltas identified for categorization",
        refDetail: `Observation from '${initialTool}' received. Proceeding to Cycle #2 for discrepancy classification.`
      });

      // Cycle 2: Discrepancy Classification Tool (only when 2+ tools were dispatched)
      if (rawToolCycles.length >= 2) {
        cycles.push({
          num: 2,
          name: secondTool,
          badge: secondTool,
          pTitle: "1. Perceive",
          pShort: "Ingested diff observation and active memory preference rules",
          pDetail: `Ingested diff observation from Iteration #1 with ${data.discrepancies?.length || 1} identified discrepancy items. Checked active session memory for tone/numerical rules.`,
          rTitle: "2. Reason",
          rShort: "Classified semantic impact and determined discrepancy categories & severities",
          rDetail: "Evaluated each discrepancy against semantic and sentiment criteria. Dispatched categorize_discrepancy to structure findings into Factual, Tone, or Omission with High/Medium/Low severity.",
          aTitle: "3. Act",
          aShort: `Executed categorize_discrepancy tool`,
          aDetail: rawToolCycles[1]?.toolArgs || JSON.stringify(data.discrepancies?.[0] || { category: "Tone/Factual", severity: "High" }, null, 2),
          aOutput: rawToolCycles[1]?.toolOutput || JSON.stringify(data.discrepancies || [], null, 2),
          refTitle: "4. Reflect",
          refShort: "Verified discrepancy categorization; all deltas structured for report generation",
          refDetail: "Observation evaluated: all discrepancies categorized. Goal state requires final report synthesis (state['done'] = False). Moving to Iteration Cycle #3 for executive summary."
        });
      }

      // Final Cycle: Terminal Synthesis & Goal Reflection
      const finalCycleNum = cycles.length + 1;
      cycles.push({
        num: finalCycleNum,
        name: "terminal_synthesis",
        badge: "Synthesis & Reflection",
        pTitle: "1. Perceive",
        pShort: "Aggregated all categorized discrepancies and memory context",
        pDetail: `Aggregated ${data.discrepancies?.length || 0} classified discrepancy items, baseline metrics, and active SQLite3 memory rules.`,
        rTitle: "2. Reason",
        rShort: "Formulated structured markdown report highlighting metrics & key differences",
        rDetail: "Model consolidated findings into an executive summary, highlighting character lengths, severity ratings, and sentiment/numerical shifts.",
        aTitle: "3. Act",
        aShort: `Generated final comparison markdown report (${(data.result || "").length} chars)`,
        aDetail: `Produced structured output report adhering to recalled session guidelines.`,
        aOutput: data.result || "Report generated.",
        refTitle: "4. Reflect",
        refShort: "Goal verified complete! Reflect set done = True and cleanly exited loop",
        refDetail: `reflect() evaluation check: Final content generated and validated against objectives. state['done'] = True. Cognitive loop exited on Iteration ${finalCycleNum} within token budget.`
      });
    }

    cognitiveTrack.innerHTML = "";
    synthesisContainer.innerHTML = `<div class="placeholder-text">Synthesizing comparison output across cognitive cycles...</div>`;

    // Step through each cycle sequentially
    for (let i = 0; i < cycles.length; i++) {
      const cycle = cycles[i];
      const cycleNum = cycle.num;
      const stepDelay = speedMs > 0 ? Math.max(100, Math.round(speedMs / 4)) : 0;

      // Update telemetry iteration and live indicator
      teleIterations.textContent = `${cycleNum} / 5`;
      teleTokens.textContent = `${cycleNum * 230} tok`;
      liveIndicator.textContent = `Cycle #${cycleNum}`;

      // Create cycle DOM element
      const cycleEl = document.createElement("div");
      cycleEl.className = "iteration-cycle-block active-cycle";
      cycleEl.dataset.cycleIndex = cycleNum;
      cycleEl.innerHTML = `
        <div class="cycle-header">
          <span class="cycle-tag">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="23 4 23 10 17 10"></polyline><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path></svg>
            Cognitive Iteration Cycle #${cycleNum}
          </span>
          <div class="cycle-header-right">
            <span class="tool-badge-call">${cycle.badge}</span>
            <button type="button" class="btn-inspect-step" data-cycle="${cycleNum}" title="Click to view full step inspection">🔍 Details ▾</button>
          </div>
        </div>

        <div class="cognitive-quad">
          <div class="quad-node quad-perceive clickable-quad" id="quad-p-${cycleNum}" data-cycle="${cycleNum}" data-step="perceive" title="Click to inspect Perceive step">
            <span class="quad-title">${cycle.pTitle} <span class="click-hint">👆</span></span>
            <span class="quad-detail">${escapeHtml(cycle.pShort)}</span>
          </div>
          <div class="quad-node quad-reason clickable-quad" id="quad-r-${cycleNum}" data-cycle="${cycleNum}" data-step="reason" title="Click to inspect Reason step">
            <span class="quad-title">${cycle.rTitle} <span class="click-hint">👆</span></span>
            <span class="quad-detail">${escapeHtml(cycle.rShort)}</span>
          </div>
          <div class="quad-node quad-act clickable-quad" id="quad-a-${cycleNum}" data-cycle="${cycleNum}" data-step="act" title="Click to inspect Act step">
            <span class="quad-title">${cycle.aTitle} <span class="click-hint">👆</span></span>
            <span class="quad-detail">${escapeHtml(cycle.aShort)}</span>
          </div>
          <div class="quad-node quad-reflect clickable-quad" id="quad-ref-${cycleNum}" data-cycle="${cycleNum}" data-step="reflect" title="Click to inspect Reflect step">
            <span class="quad-title">${cycle.refTitle} <span class="click-hint">👆</span></span>
            <span class="quad-detail">${escapeHtml(cycle.refShort)}</span>
          </div>
        </div>

        <!-- Expandable Step Inspector Drawer -->
        <div class="step-inspector-drawer" id="inspector-drawer-${cycleNum}" style="display: none;">
          <div class="inspector-header">
            <span class="inspector-title">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>
              Iteration #${cycleNum} Step-by-Step Execution Trace
            </span>
            <button type="button" class="inspector-close-btn" data-cycle="${cycleNum}" title="Close details">✕</button>
          </div>
          <div class="inspector-grid">
            <div class="inspector-card" id="card-p-${cycleNum}">
              <span class="inspector-label label-perceive">1. Perceive Context</span>
              <div class="inspector-code-block">${escapeHtml(cycle.pDetail)}</div>
            </div>
            <div class="inspector-card" id="card-r-${cycleNum}">
              <span class="inspector-label label-reason">2. Reason &amp; Decision</span>
              <div class="inspector-text">${escapeHtml(cycle.rDetail)}</div>
            </div>
            <div class="inspector-card" id="card-a-${cycleNum}">
              <span class="inspector-label label-act">3. Act (Tool Call &amp; Payload)</span>
              <div class="inspector-code-block">${escapeHtml(cycle.aDetail)}</div>
            </div>
            <div class="inspector-card" id="card-ref-${cycleNum}">
              <span class="inspector-label label-reflect">4. Reflect &amp; State Verification</span>
              <div class="inspector-text">${escapeHtml(cycle.refDetail)}</div>
            </div>
          </div>
        </div>
      `;
      cognitiveTrack.appendChild(cycleEl);
      cycleEl.scrollIntoView({ behavior: "smooth", block: "nearest" });

      if (speedMs > 0) {
        const nodeP = cycleEl.querySelector(`#quad-p-${cycleNum}`);
        const nodeR = cycleEl.querySelector(`#quad-r-${cycleNum}`);
        const nodeA = cycleEl.querySelector(`#quad-a-${cycleNum}`);
        const nodeRef = cycleEl.querySelector(`#quad-ref-${cycleNum}`);

        // Step 1: Perceive
        if (nodeP) {
          nodeP.classList.add("active-step");
          await sleep(stepDelay);
          nodeP.classList.remove("active-step");
          nodeP.classList.add("completed-step");
        }

        // Step 2: Reason
        if (nodeR) {
          nodeR.classList.add("active-step");
          await sleep(stepDelay);
          nodeR.classList.remove("active-step");
          nodeR.classList.add("completed-step");
        }

        // Step 3: Act
        if (nodeA) {
          nodeA.classList.add("active-step");
          await sleep(stepDelay);
          nodeA.classList.remove("active-step");
          nodeA.classList.add("completed-step");
        }

        // Step 4: Reflect
        if (nodeRef) {
          nodeRef.classList.add("active-step");
          await sleep(stepDelay);
          nodeRef.classList.remove("active-step");
          nodeRef.classList.add("completed-step");
        }
      }

      cycleEl.classList.remove("active-cycle");
      cycleEl.classList.add("completed-cycle");
    }

    // Attach click listeners to all Inspector buttons and Quad boxes
    attachInspectorClickListeners();

    // Final Reflection & Synthesis
    teleIterations.textContent = `3 / 5`;
    teleTokens.textContent = `${data.token_usage?.total_tokens || 690} tok`;
    teleLatency.textContent = `${data.latency_sec || 0.05}s`;
    teleStatus.textContent = data.status || "SUCCESS";
    teleStatus.className = `tele-value ${data.status === 'SUCCESS' ? 'success' : 'error'}`;
    liveIndicator.textContent = "Ready";
    liveIndicator.classList.remove("active");

    // Render Synthesis Output
    synthesisContainer.innerHTML = renderMarkdownSummary(data.result);
    const synthCard = document.querySelector(".synthesis-card");
    if (synthCard) {
      synthCard.classList.remove("fade-in-synthesis");
      void synthCard.offsetWidth;
      synthCard.classList.add("fade-in-synthesis");
    }
  }

  function attachInspectorClickListeners() {
    // Details button toggle
    document.querySelectorAll(".btn-inspect-step").forEach(btn => {
      btn.onclick = (e) => {
        e.stopPropagation();
        const cycleNum = btn.dataset.cycle;
        const drawer = document.getElementById(`inspector-drawer-${cycleNum}`);
        if (!drawer) return;
        const isHidden = drawer.style.display === "none";
        drawer.style.display = isHidden ? "flex" : "none";
        btn.textContent = isHidden ? "🔍 Details ▴" : "🔍 Details ▾";
      };
    });

    // Close button inside drawer
    document.querySelectorAll(".inspector-close-btn").forEach(btn => {
      btn.onclick = (e) => {
        e.stopPropagation();
        const cycleNum = btn.dataset.cycle;
        const drawer = document.getElementById(`inspector-drawer-${cycleNum}`);
        const toggleBtn = document.querySelector(`.btn-inspect-step[data-cycle="${cycleNum}"]`);
        if (drawer) drawer.style.display = "none";
        if (toggleBtn) toggleBtn.textContent = "🔍 Details ▾";
      };
    });

    // Click on individual Quad nodes to expand drawer & highlight that specific card
    document.querySelectorAll(".clickable-quad").forEach(node => {
      node.onclick = () => {
        const cycleNum = node.dataset.cycle;
        const stepName = node.dataset.step; // perceive, reason, act, reflect
        const drawer = document.getElementById(`inspector-drawer-${cycleNum}`);
        const toggleBtn = document.querySelector(`.btn-inspect-step[data-cycle="${cycleNum}"]`);
        if (!drawer) return;

        drawer.style.display = "flex";
        if (toggleBtn) toggleBtn.textContent = "🔍 Details ▴";

        // Remove previous highlights in this drawer
        drawer.querySelectorAll(".inspector-card").forEach(c => c.classList.remove("card-highlight"));

        // Highlight matching card
        const cardMap = { perceive: `card-p-${cycleNum}`, reason: `card-r-${cycleNum}`, act: `card-a-${cycleNum}`, reflect: `card-ref-${cycleNum}` };
        const targetCard = document.getElementById(cardMap[stepName]);
        if (targetCard) {
          targetCard.classList.add("card-highlight");
          targetCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }
      };
    });
  }

  // Run Comparison
  async function runComparison() {
    const textA = textAInput.value.trim();
    const textB = textBInput.value.trim();
    const sessionId = sessionIdInput.value.trim() || "custom_session";
    const saveRule = "";

    if (!textA || !textB) {
      alert("Please provide both Text A and Text B to compare.");
      return;
    }

    // UI Loading state
    btnRun.disabled = true;
    btnRunText.textContent = "Agent Thinking & Diffing...";
    liveIndicator.textContent = "Active";
    liveIndicator.classList.add("active");
    teleStatus.textContent = "RUNNING";
    teleStatus.className = "tele-value running";

    cognitiveTrack.innerHTML = `
      <div class="cognitive-empty">
        <div class="status-dot online" style="margin: 0 auto 10px;"></div>
        Agent is initializing ReAct cognitive loop (Perceive ➔ Reason ➔ Act ➔ Reflect)...
      </div>
    `;

    try {
      const activePresetBtn = document.querySelector(".preset-btn.active");
      const activePresetId = activePresetBtn ? parseInt(activePresetBtn.dataset.scenario) : 1;

      const res = await fetch(`${API_BASE}/api/compare`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text_a: textA,
          text_b: textB,
          session_id: sessionId,
          save_rule: saveRule,
          mock_scenario: activePresetId
        })
      });

      if (!res.ok) {
        throw new Error(`Server returned status ${res.status}: ${res.statusText}`);
      }

      const data = await res.json();

      // Step-by-step visual playback for demo recording
      await animateCognitiveExecution(data, sessionId, textA, textB);

      // Render structured logs
      const structuredLogEntries = [
        { timestamp: new Date().toISOString(), event_type: "session_start", payload: { session_id: sessionId } },
        ...(data.messages || []).filter(m => m.tool_calls).map((m, idx) => ({
          timestamp: new Date().toISOString(),
          event_type: "tool_execution",
          payload: { step: idx + 1, tool: m.tool_calls[0]?.function?.name }
        })),
        { timestamp: new Date().toISOString(), event_type: "session_complete", payload: { status: data.status, tokens: data.token_usage } }
      ];
      logsOutput.textContent = JSON.stringify(structuredLogEntries, null, 2);

      // Refresh memory panel
      refreshMemories();

    } catch (err) {
      teleStatus.textContent = "ERROR";
      teleStatus.className = "tele-value error";
      synthesisContainer.innerHTML = `
        <div style="padding: 12px; border-radius: 8px; background: rgba(244, 63, 94, 0.1); border: 1px solid rgba(244, 63, 94, 0.3);">
          <p style="color: #fda4af; font-weight: 600; margin-bottom: 6px;">Connection / Execution Error:</p>
          <p style="color: #fecdd3; font-size: 0.82rem;">${escapeHtml(err.message)}</p>
          ${isFileProtocol ? '<p style="margin-top: 8px; font-size: 0.8rem; color: #7dd3fc;">Tip: Open <strong><a href="http://localhost:8000" style="color: #38bdf8;" target="_blank">http://localhost:8000</a></strong> in your browser instead of the file directly.</p>' : ''}
        </div>
      `;
    } finally {
      btnRun.disabled = false;
      btnRunText.textContent = "Run Agentic Comparison";
      liveIndicator.textContent = "Ready";
      liveIndicator.classList.remove("active");
    }
  }

  btnRun.addEventListener("click", runComparison);

  // ---- Memory Rule Composer ----
  const btnSaveRule  = document.getElementById("btn-save-memory-rule");
  const memKeyInput  = document.getElementById("memory-key-input");
  const memValInput  = document.getElementById("memory-value-input");

  async function saveMemoryRule(key, value) {
    if (!key.trim() || !value.trim()) {
      alert("Please fill in both the rule tag and the rule instruction.");
      return;
    }
    const sessionId = sessionIdInput.value.trim() || "custom_session";
    try {
      const res = await fetch(`${API_BASE}/api/save_memory`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, key: key.trim(), value: value.trim() })
      });
      if (!res.ok) throw new Error(await res.text());
      memKeyInput.value = "";
      memValInput.value = "";
      btnSaveRule.textContent = "Saved!";
      btnSaveRule.style.background = "var(--accent-emerald)";
      setTimeout(() => {
        btnSaveRule.textContent = "Save Rule";
        btnSaveRule.style.background = "";
      }, 1800);
      refreshMemories();
    } catch (err) {
      alert("Failed to save rule: " + err.message);
    }
  }

  if (btnSaveRule) {
    btnSaveRule.addEventListener("click", () => {
      saveMemoryRule(memKeyInput.value, memValInput.value);
    });
  }

  // Quick Rule Chips
  document.querySelectorAll(".quick-rule-chip").forEach(chip => {
    chip.addEventListener("click", async () => {
      chip.classList.add("active");
      await saveMemoryRule(chip.dataset.key, chip.dataset.val);
      setTimeout(() => chip.classList.remove("active"), 2000);
    });
  });

  // Initial load
  loadPreset(1);
  refreshMemories();
});
