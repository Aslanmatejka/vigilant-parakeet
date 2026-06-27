"""
DoGoods Agentic AI System
==========================

LangGraph-based agentic architecture for Nouri AI.

This module replaces the rigid 15k-token prescriptive prompt system with:
- State machine-driven conversation flows
- Autonomous multi-step planning
- Proactive suggestions and reminders
- Preference learning
- Minimal prompts (~2k tokens)

Core components:
- state.py: Conversation state definitions
- graph.py: LangGraph workflow (nodes, edges, conditional routing)
- prompts.py: Minimal system prompts
- planner.py: Multi-step plan generation and execution
- proactive.py: Proactive suggestion engine
- learning.py: User preference tracking
"""

from backend.agent.state import AgentState, ConversationState, Message, PlanStep, ProactiveSuggestion, UserContext
from backend.agent.graph import create_agent_graph, invoke_agent
from backend.agent.prompts import build_system_prompt, ERROR_RESPONSES
from backend.agent.planner import create_plan, execute_plan_step, plan_to_text
from backend.agent.proactive import generate_proactive_suggestions, should_show_suggestion
from backend.agent.learning import update_user_preferences, get_user_preferences, get_preferred_search_params

__all__ = [
    # State
    "AgentState",
    "ConversationState",
    "Message",
    "PlanStep",
    "ProactiveSuggestion",
    "UserContext",
    
    # Graph
    "create_agent_graph",
    "invoke_agent",
    
    # Prompts
    "build_system_prompt",
    "ERROR_RESPONSES",
    
    # Planning
    "create_plan",
    "execute_plan_step",
    "plan_to_text",
    
    # Proactive
    "generate_proactive_suggestions",
    "should_show_suggestion",
    
    # Learning
    "update_user_preferences",
    "get_user_preferences",
    "get_preferred_search_params",
]
