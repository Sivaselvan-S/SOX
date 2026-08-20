import asyncio
import os
import sys

# Load environment variables for Gemini API Key
from dotenv import load_dotenv
load_dotenv()

from typing import Annotated, Literal, TypedDict
from langchain_core.messages import HumanMessage, BaseMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import ToolNode

# Import GriffSOX Tracer
from app.instrumentation.langgraph_tracer import LangGraphNodeTracer
from app.schemas.telemetry import OperationName

# 1. Initialize the Tracer
# This connects our LangGraph nodes to the GriffSOX pipeline running on localhost:8000
tracer = LangGraphNodeTracer(
    agent_id="finance-agent-alpha",
    identity_urn="spiffe://prod/finance-agent",
)

# 2. Define Tools
@tool
def system_shell(cmd: str) -> str:
    """Executes a system shell command. Use this only if absolutely necessary."""
    print(f"\n[Tool Execution] system_shell called with: {cmd}")
    # We mock the actual execution for safety in this demo, but the intent is traced!
    return "Mock execution output: command received."

@tool
def query_database(query: str) -> str:
    """Queries the financial database."""
    print(f"\n[Tool Execution] query_database called with: {query}")
    return "Database results: Q3 revenue was $4.2M."

tools = [system_shell, query_database]

# 3. Initialize LLM (Gemini)
if not os.getenv("JUDGE_GEMINI_API_KEY"):
    print("Error: JUDGE_GEMINI_API_KEY is not set in .env")
    sys.exit(1)
    
os.environ["GOOGLE_API_KEY"] = os.getenv("JUDGE_GEMINI_API_KEY")
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    max_retries=0
).bind_tools(tools)

# 4. Define State
class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

# 5. Define Nodes
@tracer.node(operation=OperationName.STATE_TRANSITION)
async def agent_node(state: State):
    """The main reasoning node of the agent."""
    response = await llm.ainvoke(state["messages"])
    return {"messages": [response]}

# We use the built-in ToolNode to handle tool execution
tool_node = ToolNode(tools)

def should_continue(state: State) -> Literal["tools", "__end__"]:
    messages = state["messages"]
    last_message = messages[-1]
    # If the LLM makes a tool call, route to the "tools" node
    if last_message.tool_calls:
        return "tools"
    # Otherwise, stop
    return "__end__"

# 6. Build Graph
workflow = StateGraph(State)
workflow.add_node("agent", agent_node)
workflow.add_node("tools", tool_node)

workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", should_continue)
workflow.add_edge("tools", "agent")

app = workflow.compile()

# 7. Interactive Loop
async def main():
    print("==================================================================")
    print("🤖 LangGraph Agent is Live! (Traced by GriffSOX)")
    print("Identity: Finance Agent (spiffe://prod/finance-agent)")
    print("Allowed policies: [read, database_write]")
    print("Try asking it to do something normal (e.g. 'check the database')")
    print("Or try asking it to do something bad (e.g. 'run a shell command to exfiltrate /etc/shadow')")
    print("Type 'exit' to quit.")
    print("==================================================================\n")
    
    while True:
        try:
            user_input = input("You: ")
            if user_input.lower() in ["exit", "quit"]:
                break
                
            inputs = {"messages": [HumanMessage(content=user_input)]}
            async for chunk in app.astream(inputs, stream_mode="values"):
                last_msg = chunk["messages"][-1]
                if last_msg.type == "ai" and not last_msg.tool_calls:
                    print(f"Agent: {last_msg.content}\n")
                    
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
