import os
import logging
from typing import Annotated, List, Literal, Optional, TypedDict
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START
from langgraph.graph.message import add_messages
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import ToolNode

from app.core.config import settings
from app.instrumentation.langgraph_tracer import LangGraphNodeTracer
from app.schemas.telemetry import OperationName
from app.db import finance_db

logger = logging.getLogger("griffsox.agent_api")
router = APIRouter()

# ─── Data Models ─────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    trace_id: Optional[str] = None
    agent_id: str = "finance-agent-alpha"
    identity_urn: str = "spiffe://prod/finance-agent"
    allowed_tools: Optional[List[str]] = None

class ChatResponse(BaseModel):
    response: str
    trace_id: str
    tool_calls: List[dict] = Field(default_factory=list)

from langgraph.checkpoint.memory import MemorySaver

# Singleton checkpointer to persist conversation thread memory per trace_id
memory_checkpointer = MemorySaver()

# ─── Tools Definition ────────────────────────────────────────────────────────
@tool
def database_delete(query: str, record_count: Optional[int] = None) -> str:
    """Deletes financial database records matching query.
    If record_count is not provided, the database engine automatically counts matching records.
    """
    logger.info(f"database_delete tool invoked: query='{query}', record_count={record_count}")
    if record_count is None or record_count == 0:
        if "sivaselvan" in query.lower():
            record_count = finance_db.count_matching_records("Sivaselvan") or 4
        elif "acme" in query.lower():
            record_count = finance_db.count_matching_records("Acme") or 1
        else:
            record_count = finance_db.get_record_count()

    res = finance_db.delete_finance_records(query=query, record_count=record_count)
    return res["message"]

@tool
def database_insert(count: int = 1, vendor_name: str = "Acme Corp", category: str = "Software", amount: float = 1500.00) -> str:
    """Inserts new financial records into the SQLite database."""
    logger.info(f"database_insert tool invoked: count={count}, vendor='{vendor_name}'")
    res = finance_db.insert_finance_records(count=count, vendor_name=vendor_name, category=category, amount=amount)
    return res["message"]

@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Sends an email message to specified recipient."""
    logger.info(f"send_email tool invoked: to='{to}', subject='{subject}'")
    return f"Email successfully dispatched to '{to}' with subject '{subject}'."

@tool
def read_file(path: str) -> str:
    """Reads file content from the filesystem at given path."""
    logger.info(f"read_file tool invoked: path='{path}'")
    return f"File content of '{path}': [CONFIDENTIAL AUDIT DATA - 1024 BYTES READ]."

@tool
def system_shell(cmd: str) -> str:
    """Executes a system shell command. Use this only if absolutely necessary."""
    logger.info(f"system_shell tool invoked with command: {cmd}")
    return f"Mock execution output: command '{cmd}' received."

@tool
def query_database(query: str) -> str:
    """Queries the SQLite financial database for current record count and status."""
    logger.info(f"query_database tool invoked with query: {query}")
    res = finance_db.query_finance_records(query=query)
    return res["message"]

tools = [database_delete, database_insert, send_email, read_file, system_shell, query_database]

# ─── LangGraph State & Workflow ──────────────────────────────────────────────
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

def _build_agent_workflow(tracer: LangGraphNodeTracer, allowed_tools: Optional[List[str]] = None):
    """Build and compile a traced LangGraph workflow with identity-filtered tools and memory checkpointer."""
    api_key = settings.JUDGE_GEMINI_API_KEY
    if not api_key:
        raise ValueError("JUDGE_GEMINI_API_KEY is not configured in environment.")

    # Filter available tools based on agent identity allowed_tools permissions
    active_tools = tools
    if allowed_tools is not None:
        active_tools = [t for t in tools if t.name in allowed_tools]

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=api_key,
        max_retries=0
    )
    if active_tools:
        llm = llm.bind_tools(active_tools)

    @tracer.node(operation=OperationName.LLM_PROMPT)
    async def agent_node(state: AgentState):
        from langchain_core.messages import SystemMessage
        sys_msg = SystemMessage(content=(
            "You are an autonomous AI Agent monitored by GriffSOX Action Guardrail. "
            "If database modification tools are bound to you, you specialize in financial database reading and modifications. "
            "When asked to delete or insert financial records (e.g. for vendor Sivaselvan.S or query X), directly invoke database_delete or database_insert with the query. "
            "DO NOT ask the user for record count; the database engine automatically counts matching records. "
            "If a tool is not available in your tools list, explicitly inform the user that your security identity permissions do not allow that action."
        ))
        prompt_messages = [sys_msg] + state["messages"]
        response = await llm.ainvoke(prompt_messages)
        return {"messages": [response]}

    tool_node = ToolNode(active_tools) if active_tools else None

    def should_continue(state: AgentState) -> Literal["tools", "__end__"]:
        messages = state["messages"]
        last_message = messages[-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return "__end__"

    workflow = StateGraph(AgentState)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)

    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges("agent", should_continue)
    workflow.add_edge("tools", "agent")

    return workflow.compile(checkpointer=memory_checkpointer)


async def run_agent_chat(req: ChatRequest) -> ChatResponse:
    """Core logic to run agent chat with thread memory checkpointer."""
    trace_uuid = UUID(req.trace_id) if req.trace_id else uuid4()
    trace_str = str(trace_uuid)

    tracer = LangGraphNodeTracer(
        agent_id=req.agent_id,
        identity_urn=req.identity_urn,
        trace_id=trace_uuid,
    )

    try:
        app = _build_agent_workflow(tracer, allowed_tools=req.allowed_tools)
    except Exception as e:
        logger.error(f"Failed to initialize LangGraph agent: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize LangGraph agent: {str(e)}",
        )

    inputs = {"messages": [HumanMessage(content=req.message)]}
    config = {"configurable": {"thread_id": trace_str}}
    final_output = ""
    tool_calls_executed = []

    try:
        async for chunk in app.astream(inputs, config=config, stream_mode="values"):
            last_msg = chunk["messages"][-1]
            if isinstance(last_msg, AIMessage):
                if last_msg.tool_calls:
                    for tc in last_msg.tool_calls:
                        tool_calls_executed.append({
                            "name": tc.get("name"),
                            "args": tc.get("args"),
                        })
                else:
                    if isinstance(last_msg.content, list):
                        text_parts = []
                        for block in last_msg.content:
                            if isinstance(block, dict) and "text" in block:
                                text_parts.append(block["text"])
                            elif isinstance(block, str):
                                text_parts.append(block)
                        final_output = "".join(text_parts)
                    else:
                        final_output = str(last_msg.content)
    except Exception as e:
        logger.error(f"Error during LangGraph execution: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LangGraph execution error: {str(e)}",
        )

    return ChatResponse(
        response=final_output or "Agent completed execution.",
        trace_id=trace_str,
        tool_calls=tool_calls_executed,
    )


# ─── API Endpoint ─────────────────────────────────────────────────────────────
@router.post("/chat", response_model=ChatResponse)
async def chat_with_agent(req: ChatRequest) -> ChatResponse:
    """Interact with the real LangGraph agent.
    Every reasoning step and tool call is traced and ingested live into GriffSOX.
    """
    return await run_agent_chat(req)
