"""Core 4-step pure-Python cognitive agent loop (Perceive, Reason, Act, Reflect).

This module coordinates an LLM-driven comparison agent that iteratively calls tools,
reflects on tool output, and produces a finalized comparison summary.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional, Tuple
from tools import TOOL_HANDLERS, TOOL_SCHEMAS


def perceive(
    state: Dict[str, Any],
    observation: Optional[str] = None,
    tool_call_id: Optional[str] = None,
    tool_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Ingest external observations or tool results into conversation history.

    Args:
        state: The current agent execution state containing `messages`.
        observation: The raw string output returned from an executed tool or system.
        tool_call_id: The OpenAI tool call identifier matching the original request.
        tool_name: The name of the tool that produced the observation.

    Returns:
        The updated list of message dictionaries stored in state.
    """
    messages: List[Dict[str, Any]] = state.setdefault("messages", [])

    if observation is not None and tool_call_id is not None:
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name or "tool",
            "content": observation,
        })
    elif observation is not None:
        messages.append({
            "role": "user",
            "content": observation,
        })

    return messages


def reason(
    messages: List[Dict[str, Any]],
    tool_schemas: List[Dict[str, Any]],
    client: Any,
    model: str,
) -> Any:
    """Dispatch message history and available tools to the LLM to determine the next action.

    Args:
        messages: The sequence of messages representing conversation history.
        tool_schemas: OpenAI-compatible function calling tool schemas.
        client: An OpenAI or compatible API client instance.
        model: The model identifier string (e.g., 'gpt-4o-mini').

    Returns:
        The chat completion message object from choices[0].message.
    """
    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": messages,
    }
    if tool_schemas:
        kwargs["tools"] = tool_schemas
        kwargs["tool_choice"] = "auto"

    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message


def act(
    decision_message: Any,
    tool_handlers: Dict[str, Callable[..., str]],
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Unpack decision message and execute matching tool handler or capture response.

    Args:
        decision_message: The completion message returned by the LLM during `reason`.
        tool_handlers: Mapping of tool function names to executable Python callables.

    Returns:
        A tuple of (tool_name, tool_call_id, action_result).
        If no tool call was generated, returns (None, None, text_content).
    """
    tool_calls = getattr(decision_message, "tool_calls", None)

    if tool_calls and len(tool_calls) > 0:
        tool_call = tool_calls[0]
        tool_name = tool_call.function.name
        tool_call_id = tool_call.id
        raw_arguments = tool_call.function.arguments

        handler = tool_handlers.get(tool_name)
        if not handler:
            error_msg = f"Error: Tool '{tool_name}' is not registered in tool handlers."
            return tool_name, tool_call_id, error_msg

        try:
            parsed_args = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
            result = handler(**parsed_args)
            return tool_name, tool_call_id, str(result)
        except Exception as exc:
            error_msg = f"Error executing tool '{tool_name}': {str(exc)}"
            return tool_name, tool_call_id, error_msg

    # No tool call; final response generated
    content = getattr(decision_message, "content", "")
    return None, None, content


def reflect(
    state: Dict[str, Any],
    final_content: Optional[str],
    action_result: Optional[str],
) -> bool:
    """Evaluate whether the agent's goal is complete or if further cycles are required.

    Args:
        state: The current agent execution state dict.
        final_content: Content provided when no tool call was made.
        action_result: The raw output of an executed tool call.

    Returns:
        True if the execution loop has reached a terminal state; False otherwise.
    """
    if final_content is not None and final_content.strip():
        state["done"] = True
        state["result"] = final_content.strip()
        return True

    # If action_result contains an unrecoverable tool error
    if action_result and (action_result.startswith("Error:") or action_result.startswith("Error executing tool")):
        state["done"] = True
        state["result"] = f"Aborted due to tool error: {action_result}"
        return True

    state["done"] = False
    return False


def run_basic_loop(
    text_a: str,
    text_b: str,
    client: Any,
    model: str,
    max_iterations: int = 5,
    system_prompt: Optional[str] = None,
) -> Dict[str, Any]:
    """Coordinate the sequential cognitive cycle across multiple iterations.

    Args:
        text_a: The original baseline text.
        text_b: The modified comparison text.
        client: An OpenAI or compatible API client instance.
        model: Target model string.
        max_iterations: Maximum cognitive iterations permitted.
        system_prompt: Optional custom system prompt or memory injection.

    Returns:
        A dictionary capturing final state, iteration count, message history, and result.
    """
    default_system = (
        "You are an expert Text Comparison Agent. Your objective is to thoroughly compare Text A "
        "and Text B, identify every meaningful difference, categorize each discrepancy using the "
        "`categorize_discrepancy` tool, and provide a final comprehensive summary highlighting the key differences."
    )

    initial_messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt or default_system},
        {
            "role": "user",
            "content": f"Please compare the following texts and highlight differences.\n\n--- TEXT A ---\n{text_a}\n\n--- TEXT B ---\n{text_b}",
        },
    ]

    state: Dict[str, Any] = {
        "messages": initial_messages,
        "iterations": 0,
        "done": False,
        "result": None,
        "discrepancies": [],
    }

    while not state["done"] and state["iterations"] < max_iterations:
        state["iterations"] += 1

        # Step 1 & 2: Perceive current context & Reason next step
        decision_message = reason(
            messages=state["messages"],
            tool_schemas=TOOL_SCHEMAS,
            client=client,
            model=model,
        )

        # Convert decision message to serializable message dictionary for history
        assistant_msg: Dict[str, Any] = {"role": "assistant"}
        if getattr(decision_message, "content", None):
            assistant_msg["content"] = decision_message.content
        if getattr(decision_message, "tool_calls", None):
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in decision_message.tool_calls
            ]
        state["messages"].append(assistant_msg)

        # Step 3: Act (dispatch tool or gather final response)
        tool_name, tool_call_id, action_result = act(
            decision_message=decision_message,
            tool_handlers=TOOL_HANDLERS,
        )

        if tool_name and tool_call_id:
            # If categorization tool was called, record discrepancy in state
            if tool_name == "categorize_discrepancy" and action_result:
                try:
                    parsed = json.loads(action_result)
                    state["discrepancies"].append(parsed)
                except Exception:
                    pass

            # Perceive the tool observation
            perceive(
                state=state,
                observation=action_result,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
            )
            # Step 4: Reflect on action
            reflect(state=state, final_content=None, action_result=action_result)
        else:
            # Final text response received
            reflect(state=state, final_content=action_result, action_result=None)

    if not state["done"] and state["result"] is None:
        state["result"] = "Maximum iterations reached before final summary was completed."

    return state
