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
# Heavy runtime imports (graph / planner / proactive / learning) depend on
# langgraph + langchain_openai. They are required in production but optional
# in test environments where we only exercise the pure-Python safety / affect /
# self_model modules. Guard the imports so `import backend.agent.safety` (etc.)
# works in slim environments without pulling the full agent runtime.
try:
    from backend.agent.graph import create_agent_graph, invoke_agent
    from backend.agent.planner import create_plan, execute_plan_step, plan_to_text
    from backend.agent.proactive import generate_proactive_suggestions, should_show_suggestion
    from backend.agent.learning import update_user_preferences, get_user_preferences, get_preferred_search_params
    _AGENT_RUNTIME_AVAILABLE = True
except ImportError as _exc:  # langgraph / langchain_openai missing
    import logging as _logging
    _logging.getLogger(__name__).info(
        "backend.agent runtime deps unavailable (%s); pure-Python modules "
        "(safety, affect, self_model, actions) still importable.", _exc,
    )
    create_agent_graph = invoke_agent = None  # type: ignore[assignment]
    create_plan = execute_plan_step = plan_to_text = None  # type: ignore[assignment]
    generate_proactive_suggestions = should_show_suggestion = None  # type: ignore[assignment]
    update_user_preferences = get_user_preferences = get_preferred_search_params = None  # type: ignore[assignment]
    _AGENT_RUNTIME_AVAILABLE = False

from backend.agent.prompts import build_system_prompt, ERROR_RESPONSES

# Register the AGENT_V2 action handlers in the central actions registry.
# Side-effectful but cheap: it only populates an in-process dict. Wrapped in
# try/except so a stale import error here never breaks the v1 graph or the
# pure safety modules.
try:
    from backend.agent.tool_actions import register_all as _register_agent_v2_actions
    _register_agent_v2_actions()
except Exception as _act_exc:  # noqa: BLE001
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "agent_v2 action registrations skipped: %s", _act_exc,
    )

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
