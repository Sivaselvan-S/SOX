# 🛡️ GriffSOX (LongWall AI) — AI Agent Security & Action Guardrail Platform

**GriffSOX** is a Security Operations & Pre-Execution Action Guardrail platform designed to monitor, intercept, evaluate, and contain autonomous AI agents (such as LangGraph agents) operating in enterprise environments.

It ensures that AI agents operate safely within defined compliance boundaries, providing **real-time tool call interception**, **Human-In-The-Loop (HITL) approval workflows**, **multi-phase attack detection**, and **automated SOAR containment actions**.

---

## 🌟 Live Demo & Deployment Links

- **Frontend Application (Vercel):** [https://sox-iota.vercel.app](https://sox-iota.vercel.app)
- **Backend API (AWS EC2):** `http://32.236.50.26:8000`
- **Interactive OpenAPI Docs (Swagger):** `http://32.236.50.26:8000/api/v1/openapi.json`
- **GitHub Repository:** [https://github.com/Sivaselvan-S/SOX](https://github.com/Sivaselvan-S/SOX)

---

## ✨ Key Features & Architecture

### 1. 🛑 Pre-Execution Action Guardrails & HITL Interception
- Intercepts sensitive agent tool calls (e.g., `database_delete`, `system_shell`, bulk data exfiltration) **before execution**.
- Supports rules with flexible operators (`>`, `<`, `==`, `!=`, `contains`, `not_in`).
- Pauses risky executions into a real-time **Human-In-The-Loop (HITL)** queue for human analyst review.
- Executes approved tool calls against the financial database upon human authorization.

### 2. 🤖 Interactive LangGraph Agent & Chat Interface
- Built-in live agent integrated with LLMs (Gemini / Heuristic) and SQLite financial records database.
- Pre-built live test scenarios:
  - 📊 **Count Records** (Log & Allow)
  - ➕ **Add Records** (Allow)
  - 🚨 **Block: Delete 500 Records** (Prohibited Action)
  - ⏳ **HITL: Bulk Delete Request** (Requires Approval)
  - 🔒 **Log & Allow: Confidential Read** (Audited)

### 3. 🔍 Multi-Phase Attack Detection & Incident Desk
- Real-time telemetry ingestion tracking agent node transitions, tool calls, and SPIFFE identity URNs.
- Automatic correlation engine identifying:
  - Escalation of Privilege
  - Prompt Injection & Jailbreaks
  - Unauthorized Data Deletion
- **Automated SOAR Containment**:
  - Process Interrupts
  - STS Key Revocation
  - Docker Container Eviction
  - SIEM Webhook Alerts

### 4. ⚙️ Dynamic Rule Management & MongoDB Persistence
- Rule editor supporting live creation, updates, and deletion of guardrail rules.
- **MongoDB Atlas persistence** ensures created rules and audit logs survive server reboots and container redeployments.

---

## 🏗️ System Architecture

```
                                    +-----------------------------------+
                                    |        Vite + React UI           |
                                    |    (Deployed on Vercel)          |
                                    +-----------------+-----------------+
                                                      |
                                                      | HTTP / WebSocket
                                                      v
                                    +-----------------+-----------------+
                                    |    FastAPI Backend Server        |
                                    |    (Containerized on AWS EC2)    |
                                    +--------+------------------+--------+
                                             |                  |
                       +---------------------+                  +---------------------+
                       v                                                              v
      +----------------+-----------------+                   +------------------------+----------------+
      |       Action Guard Engine        |                   |             MongoDB Atlas               |
      |   (Rule Evaluator & HITL Queue)  |                   | (Telemetry, Incidents, Persistent Rules)  |
      +----------------+-----------------+                   +-----------------------------------------+
                       |
                       v
      +----------------+-----------------+
      |    SQLite Financial Database     |
      | (Target DB for Agent Actions)    |
      +----------------------------------+
```

---

## 🚀 Quick Start Guide (Local Development)

### Prerequisites
- **Python:** 3.10+
- **Node.js:** v18+ & `npm`
- **MongoDB:** Local instance or MongoDB Atlas Connection URI

---

### Step 1: Clone Repository
```bash
git clone https://github.com/Sivaselvan-S/SOX.git
cd SOX
```

---

### Step 2: Backend Setup

1. **Create Virtual Environment:**
   ```bash
   python -m venv venv
   # On Windows PowerShell:
   .\venv\Scripts\Activate.ps1
   # On Linux/macOS:
   source venv/bin/activate
   ```

2. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure `.env` File:**
   Copy `.env.example` to `.env` and fill in required variables:
   ```bash
   cp .env.example .env
   ```
   *Example `.env`:*
   ```ini
   MONGO_URI=mongodb+srv://<user>:<password>@cluster.mongodb.net/griffsox_db
   MONGO_DB_NAME=griffsox_db
   JUDGE_MODE=gemini
   JUDGE_GEMINI_API_KEY=your_gemini_api_key
   ALLOWED_ORIGINS=http://localhost:5173
   ```

4. **Run Backend Server:**
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
   *The backend will start at `http://localhost:8000`.*

---

### Step 3: Frontend Setup

1. **Navigate to `frontend/` directory:**
   ```bash
   cd frontend
   npm install
   ```

2. **Set Environment Variable (Optional for local dev):**
   Create `frontend/.env`:
   ```ini
   VITE_API_BASE_URL=http://localhost:8000
   ```

3. **Start Frontend Dev Server:**
   ```bash
   npm run dev
   ```
   *The frontend application will start at `http://localhost:5173`.*

---

## 🐋 Docker & AWS EC2 Deployment

### 1. Build and Run Container Locally
```bash
docker build -t griffsox-backend .
docker run -d --name griffsox-backend -p 8000:8000 --env-file .env griffsox-backend
```

### 2. AWS EC2 Container Deployment
```bash
cd SOX
git pull origin main
docker stop griffsox-backend || true
docker rm griffsox-backend || true
docker build -t griffsox-backend .
docker run -d --name griffsox-backend --restart always -p 8000:8000 --env-file .env griffsox-backend
```

---

## 🛠️ How to Use the Application

1. **Open the Web App**: Launch [https://sox-iota.vercel.app](https://sox-iota.vercel.app).
2. **Interact with the AI Agent**:
   - Use the **Live Agent Scenarios** buttons at the top of the Chat screen to trigger test agent commands.
   - Or type custom prompts in the prompt box (e.g. `delete 4 records from finance db`).
3. **Review HITL Approvals**:
   - When an action requires approval (e.g., bulk delete), it appears in the **HITL Queue** tab.
   - Click **Approve Execution** to authorize the tool and execute it on the financial database.
   - Click **Reject Action** to block it.
4. **Manage Rules**:
   - Navigate to the **Action Rules** tab to inspect, create, edit, or delete guardrail rules.
   - Rule changes take effect instantly and persist across system reboots.
5. **Inspect Audit Log & Incidents**:
   - View complete execution history and security alerts in the **Action Audit Log** and **Incident Desk** tabs.

---

## 📜 License
This project is licensed under the MIT License.
