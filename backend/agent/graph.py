"""
LangGraph Workflow Definition
===============================

Defines the agentic workflow as a state machine with conditional routing.

Workflow nodes:
- understand_intent: Classify user intent and extract entities
- plan_task: Generate multi-step plan for complex requests
- execute_tools: Run tools sequentially or in parallel
- generate_response: Create natural language response
- check_proactive: Generate proactive suggestions
- update_learning: Update user preferences

Conditional edges:
- requires_planning?: simple query → execute directly, complex → plan first
- plan_complete?: more steps → execute next, done → respond
- should_suggest?: check cooldown + context → suggest or skip
"""

import logging
from typing import Dict, Any, Optional, List, Literal
from datetime import datetime, timezone
import json

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage

from backend.agent.state import AgentState, Message, PlanStep, ProactiveSuggestion
from backend.agent.prompts import build_system_prompt, ERROR_RESPONSES
from backend.agent.planner import create_plan, execute_plan_step
from backend.agent.proactive import generate_proactive_suggestions
from backend.agent.learning import update_user_preferences

logger = logging.getLogger(__name__)

# Initialize OpenAI model for LangGraph
# Use GPT-4.1 with streaming enabled for better UX
def _get_model(temperature: float = 0.7) -> ChatOpenAI:
    import os
    return ChatOpenAI(
        model="gpt-4-1106-preview",  # GPT-4 Turbo (latest)
        temperature=temperature,
        streaming=True,
        api_key=os.getenv("OPENAI_API_KEY"),
    )


# ============================================================================
# Node Functions
# ============================================================================

async def understand_intent(state: AgentState) -> AgentState:
    """
    Classify user intent and extract entities.
    
    Intent categories:
    - search: Find food near user
    - claim: Reserve food
    - donate: Post food listing
    - navigate: Open app page
    - help: General questions
    - general: Casual conversation
    """
    logger.info(f"[understand_intent] Processing message for user {state['user_id']}")
    
    current_message = state.get("current_message", "")
    user_context = state.get("user_context", {})
    
    # Build intent classification prompt
    intent_prompt = f"""Analyze this user message and classify the intent.

User message: "{current_message}"

User context:
- Location: {user_context.get('address', 'Not set')}
- Dietary restrictions: {user_context.get('dietary_restrictions', [])}
- Role: {user_context.get('role', 'user')}

Classify into ONE of these intents:
1. search - User wants to find food
2. claim - User wants to reserve/claim food
3. donate - User wants to post food for sharing
4. navigate - User wants to open a page/section
5. help - User has questions about how things work
6. general - Casual conversation, greetings

Also extract any relevant entities:
- food_type: specific food mentioned
- location: location mentioned
- quantity: amount mentioned
- dietary_tags: dietary requirements mentioned

Respond with JSON only:
{{
  "intent": "search|claim|donate|navigate|help|general",
  "confidence": 0.0-1.0,
  "requires_action": true/false,
  "entities": {{
    "food_type": "...",
    "location": "...",
    ...
  }}
}}"""
    
    try:
        model = _get_model(temperature=0.3)  # Lower temp for classification
        messages = [HumanMessage(content=intent_prompt)]
        response = await model.ainvoke(messages)
        
        # Parse JSON response
        intent_data = json.loads(response.content)
        
        # Detect language (simple heuristic)
        spanish_indicators = ['hola', 'quiero', 'necesito', 'busco', 'gracias', 'sí', 'cómo']
        detected_language = "es" if any(word in current_message.lower() for word in spanish_indicators) else "en"
        
        # Update state
        return {
            **state,
            "detected_intent": intent_data.get("intent"),
            "detected_language": detected_language,
            "user_context": {
                **user_context,
                "last_intent_entities": intent_data.get("entities", {}),
            },
            "conversation_phase": "planning" if intent_data.get("requires_action") else "understanding",
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        
    except Exception as e:
        logger.error(f"Intent classification failed: {e}")
        return {
            **state,
            "detected_intent": "general",
            "detected_language": state.get("detected_language", "en"),
            "error": f"Intent classification error: {str(e)}",
        }


async def plan_task(state: AgentState) -> AgentState:
    """
    Generate multi-step execution plan for complex requests.
    
    Simple requests (1-2 tools) execute directly without planning.
    Complex requests get a structured plan.
    """
    logger.info(f"[plan_task] Creating plan for intent: {state.get('detected_intent')}")
    
    intent = state.get("detected_intent")
    entities = state.get("user_context", {}).get("last_intent_entities", {})
    current_message = state.get("current_message", "")
    
    # Create plan based on intent
    try:
        plan = await create_plan(
            intent=intent,
            message=current_message,
            entities=entities,
            user_context=state.get("user_context", {}),
        )
        
        return {
            **state,
            "active_plan": plan,
            "plan_goal": f"Complete {intent} task",
            "current_step": 0,
            "conversation_phase": "executing",
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        
    except Exception as e:
        logger.error(f"Planning failed: {e}")
        return {
            **state,
            "error": f"Planning error: {str(e)}",
            "conversation_phase": "completed",
        }


async def execute_tools(state: AgentState) -> AgentState:
    """
    Execute the current step in the plan or run tools directly.
    
    Handles:
    - Sequential execution for dependent steps
    - Parallel execution for independent steps (future enhancement)
    - Error recovery with retries
    """
    logger.info(f"[execute_tools] Executing step {state.get('current_step', 0)}")
    
    active_plan = state.get("active_plan", [])
    current_step_idx = state.get("current_step", 0)
    
    if not active_plan or current_step_idx >= len(active_plan):
        # No plan or plan complete
        return {
            **state,
            "conversation_phase": "completed",
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
    
    current_step = active_plan[current_step_idx]
    
    try:
        # Execute the step
        result = await execute_plan_step(
            step=current_step,
            user_id=state.get("user_id"),
            user_context=state.get("user_context", {}),
        )
        
        # Update plan with result
        updated_plan = active_plan.copy()
        updated_plan[current_step_idx] = {
            **current_step,
            "status": "completed",
            "result": result,
        }
        
        # Store tool results for response generation
        recent_results = state.get("recent_tool_results", [])
        recent_results.append(result)
        
        return {
            **state,
            "active_plan": updated_plan,
            "current_step": current_step_idx + 1,
            "recent_tool_results": recent_results[-5:],  # Keep last 5
            "conversation_phase": "executing" if current_step_idx + 1 < len(active_plan) else "completed",
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        
    except Exception as e:
        logger.error(f"Tool execution failed: {e}")
        
        # Mark step as failed
        updated_plan = active_plan.copy()
        updated_plan[current_step_idx] = {
            **current_step,
            "status": "failed",
            "result": {"error": str(e)},
        }
        
        return {
            **state,
            "active_plan": updated_plan,
            "error": f"Tool execution error: {str(e)}",
            "conversation_phase": "completed",
        }


async def generate_response(state: AgentState) -> AgentState:
    """
    Generate natural language response based on tool results and context.
    
    Uses minimal system prompt + tool results to create response.
    Much more token-efficient than the old 15k-token approach.
    """
    logger.info("[generate_response] Creating response")
    
    user_context = state.get("user_context", {})
    language = state.get("detected_language", "en")
    recent_results = state.get("recent_tool_results", [])
    current_message = state.get("current_message", "")
    detected_intent = state.get("detected_intent")
    
    # Build system prompt (minimal ~2k tokens)
    system_prompt = build_system_prompt(user_context, language)
    
    # Build context from tool results
    tool_context = ""
    if recent_results:
        tool_context = "\n\n**Tool Results:**\n"
        for i, result in enumerate(recent_results[-3:], 1):  # Last 3 results only
            tool_context += f"{i}. {json.dumps(result, indent=2)[:500]}\n"
    
    # Build conversation context (last 5 messages)
    conversation_context = ""
    messages = state.get("messages", [])
    if messages:
        conversation_context = "\n\n**Recent Conversation:**\n"
        for msg in messages[-5:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")[:200]
            conversation_context += f"{role}: {content}\n"
    
    # Generate response
    response_prompt = f"""{system_prompt}

{conversation_context}

{tool_context}

User's current message: "{current_message}"
Detected intent: {detected_intent}

Respond naturally and conversationally. If tools were executed, summarize the results.
If an action was taken, confirm it. If nothing was found, suggest alternatives.

Keep your response concise (2-3 sentences unless providing a list of options)."""
    
    try:
        model = _get_model()
        messages = [HumanMessage(content=response_prompt)]
        response = await model.ainvoke(messages)
        
        response_text = response.content
        
        # Add message to history
        updated_messages = state.get("messages", []).copy()
        updated_messages.extend([
            Message(
                role="user",
                content=current_message,
                timestamp=datetime.now(timezone.utc).isoformat(),
                tool_calls=None,
                tool_results=None,
            ),
            Message(
                role="assistant",
                content=response_text,
                timestamp=datetime.now(timezone.utc).isoformat(),
                tool_calls=None,
                tool_results=recent_results if recent_results else None,
            ),
        ])
        
        return {
            **state,
            "response_text": response_text,
            "messages": updated_messages[-50:],  # Keep last 50 messages
            "conversation_phase": "idle",
            "turn_count": state.get("turn_count", 0) + 1,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        
    except Exception as e:
        logger.error(f"Response generation failed: {e}")
        fallback = ERROR_RESPONSES.get(language, ERROR_RESPONSES["en"]).get("unknown")
        return {
            **state,
            "response_text": fallback,
            "error": f"Response generation error: {str(e)}",
            "conversation_phase": "idle",
        }


async def check_proactive(state: AgentState) -> AgentState:
    """
    Generate proactive suggestions if appropriate.
    
    Checks:
    - Cooldown period (don't spam suggestions)
    - Context relevance (unclaimed pickups, expiring food, etc.)
    - User preferences (has user dismissed similar suggestions?)
    """
    logger.info("[check_proactive] Checking for proactive suggestions")
    
    # Skip if proactive disabled
    if not state.get("enable_proactive", True):
        return {
            **state,
            "should_suggest_proactively": False,
        }
    
    try:
        suggestions = await generate_proactive_suggestions(
            user_id=state.get("user_id"),
            user_context=state.get("user_context", {}),
            recent_intent=state.get("detected_intent"),
        )
        
        return {
            **state,
            "pending_suggestions": suggestions,
            "should_suggest_proactively": len(suggestions) > 0,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        
    except Exception as e:
        logger.error(f"Proactive check failed: {e}")
        return {
            **state,
            "should_suggest_proactively": False,
        }


async def update_learning(state: AgentState) -> AgentState:
    """
    Update user preferences based on conversation.
    
    Learns:
    - Frequently searched food types
    - Preferred communities
    - Typical quantities
    - Conversation patterns
    """
    logger.info("[update_learning] Updating user preferences")
    
    # Skip if learning disabled
    if not state.get("enable_learning", True):
        return state
    
    try:
        await update_user_preferences(
            user_id=state.get("user_id"),
            intent=state.get("detected_intent"),
            entities=state.get("user_context", {}).get("last_intent_entities", {}),
            tool_results=state.get("recent_tool_results", []),
        )
        
        return {
            **state,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        
    except Exception as e:
        logger.error(f"Learning update failed: {e}")
        return state


# ============================================================================
# Conditional Edge Functions
# ============================================================================

def requires_planning(state: AgentState) -> Literal["plan", "execute", "respond"]:
    """Decide if intent requires multi-step planning."""
    intent = state.get("detected_intent")
    
    # Complex intents that benefit from planning
    complex_intents = ["donate", "claim"]  # Multi-step workflows
    
    if intent in complex_intents:
        return "plan"
    
    # Simple intents execute directly
    simple_intents = ["search", "help", "general"]
    if intent in simple_intents:
        return "execute"
    
    # Default: skip planning
    return "respond"


def plan_complete(state: AgentState) -> Literal["execute_next", "respond"]:
    """Check if there are more steps to execute."""
    active_plan = state.get("active_plan", [])
    current_step = state.get("current_step", 0)
    
    if active_plan and current_step < len(active_plan):
        return "execute_next"
    
    return "respond"


def should_suggest(state: AgentState) -> Literal["suggest", "done"]:
    """Decide if proactive suggestions should be shown."""
    if state.get("should_suggest_proactively", False):
        return "suggest"
    return "done"


# ============================================================================
# Graph Construction
# ============================================================================

def create_agent_graph() -> StateGraph:
    """
    Build the LangGraph workflow.
    
    Workflow:
    1. understand_intent → classify user message
    2. (conditional) plan_task → create execution plan
    3. execute_tools → run tools (loop until plan complete)
    4. generate_response → create natural language response
    5. (conditional) check_proactive → generate suggestions
    6. update_learning → update user preferences
    """
    
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("understand", understand_intent)
    workflow.add_node("plan", plan_task)
    workflow.add_node("execute", execute_tools)
    workflow.add_node("respond", generate_response)
    workflow.add_node("proactive", check_proactive)
    workflow.add_node("learn", update_learning)
    
    # Entry point
    workflow.set_entry_point("understand")
    
    # Conditional routing after intent classification
    workflow.add_conditional_edges(
        "understand",
        requires_planning,
        {
            "plan": "plan",
            "execute": "execute",
            "respond": "respond",
        },
    )
    
    # After planning, always execute
    workflow.add_edge("plan", "execute")
    
    # After execution, check if more steps or respond
    workflow.add_conditional_edges(
        "execute",
        plan_complete,
        {
            "execute_next": "execute",  # Loop for next step
            "respond": "respond",
        },
    )
    
    # After response, check for proactive suggestions
    workflow.add_edge("respond", "proactive")
    
    # After proactive check, update learning
    workflow.add_conditional_edges(
        "proactive",
        should_suggest,
        {
            "suggest": "learn",  # Store suggestions and learn
            "done": "learn",
        },
    )
    
    # End after learning
    workflow.add_edge("learn", END)
    
    return workflow.compile()


# ============================================================================
# Main Invocation Function
# ============================================================================

async def invoke_agent(
    user_id: str,
    message: str,
    conversation_id: Optional[str] = None,
    user_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Invoke the agent for a single conversation turn.
    
    Args:
        user_id: User's UUID
        message: User's message
        conversation_id: Optional conversation ID (creates new if None)
        user_context: Optional user context (fetched if None)
    
    Returns:
        Dict with response_text, conversation_id, tool_results, suggestions
    """
    from backend.agent.state import AgentState
    import uuid
    
    # Create or load conversation state
    if not conversation_id:
        conversation_id = str(uuid.uuid4())
    
    # Initialize state
    initial_state: AgentState = {
        "conversation_id": conversation_id,
        "user_id": user_id,
        "current_message": message,
        "messages": [],
        "user_context": user_context or {"user_id": user_id},
        "detected_language": "en",
        "turn_count": 0,
        "conversation_phase": "understanding",
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "enable_proactive": True,
        "enable_learning": True,
        "include_audio": False,
    }
    
    # Create graph
    graph = create_agent_graph()
    
    # Invoke graph
    try:
        final_state = await graph.ainvoke(initial_state)
        
        return {
            "text": final_state.get("response_text", ""),
            "user_id": user_id,
            "conversation_id": conversation_id,
            "lang": final_state.get("detected_language", "en"),
            "tool_results": final_state.get("recent_tool_results", []),
            "suggestions": final_state.get("pending_suggestions", []),
            "timestamp": final_state.get("last_updated"),
        }
        
    except Exception as e:
        logger.error(f"Agent invocation failed: {e}")
        return {
            "text": ERROR_RESPONSES["en"]["unknown"],
            "user_id": user_id,
            "conversation_id": conversation_id,
            "lang": "en",
            "tool_results": [],
            "suggestions": [],
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
