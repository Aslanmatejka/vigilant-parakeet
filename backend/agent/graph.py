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
import re
from typing import Dict, Any, Optional, List, Literal
from datetime import datetime, timezone
import asyncio
import json
import time
import uuid

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage

from backend.agent.state import AgentState, Message, PlanStep, ProactiveSuggestion
from backend.agent.prompts import build_system_prompt, ERROR_RESPONSES
from backend.agent.planner import create_plan, execute_plan_step, enrich_entities_from_conversation
from backend.agent.proactive import generate_proactive_suggestions
from backend.agent.suggestion_chips import (
    build_turn_suggestions,
    should_load_active_communities,
)
from backend.agent.tool_results import wrap_tool_result, normalize_tool_results, compact_actions_for_metadata
from backend.debug_log import agent_debug_log

logger = logging.getLogger(__name__)

# Intents that always need a tool plan — do not rely on the LLM's
# `requires_action` flag, which is often false for help/search turns.
_ACTIONABLE_INTENTS = frozenset({"search", "claim", "donate", "navigate", "help"})

# Initialize OpenAI model for LangGraph — share CHAT_MODEL with ai_engine.py
# so the agent and legacy engine use the same primary model + fallbacks.
def _get_model(temperature: float = 0.7) -> ChatOpenAI:
    from backend.ai_engine import CHAT_MODEL, OPENAI_API_KEY
    return ChatOpenAI(
        model=CHAT_MODEL,
        temperature=temperature,
        streaming=True,
        api_key=OPENAI_API_KEY,
    )


_NIL_UUID = "00000000-0000-0000-0000-000000000000"


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
    prior = state.get("messages", []) or []
    history_snippet = ""
    if prior:
        lines = []
        for msg in prior[-6:]:
            role = msg.get("role", "user")
            content = (msg.get("content") or "")[:300]
            lines.append(f"{role}: {content}")
        history_snippet = "\n".join(lines)
    
    # Build intent classification prompt
    intent_prompt = f"""Analyze this user message and classify the intent.

Recent conversation (oldest to newest):
{history_snippet or "(none — first message)"}

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

Also extract any relevant entities from the USER MESSAGE ONLY (do not infer
dietary restrictions from profile — those are defaults, not search filters):
- food_type: specific food mentioned
- location: location mentioned
- quantity: amount mentioned
- dietary_tags: ONLY if the user explicitly asked for a diet in this message
- exclude_allergens: ONLY if the user explicitly mentioned allergens to avoid

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
        
        # Parse JSON response — gpt-4o often wraps JSON in ```json ... ``` fences,
        # so strip them before json.loads. Also handle stray prose by slicing to
        # the outermost { ... } if the fenced strip didn't produce clean JSON.
        raw = (response.content or "").strip()
        if raw.startswith("```"):
            # Drop the opening fence line (```json or ```) and any trailing ```
            lines = raw.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            raw = "\n".join(lines).strip()
        try:
            intent_data = json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                intent_data = json.loads(raw[start : end + 1])
            else:
                raise
        
        # Language was resolved in invoke_agent (sticky + profile); keep unless unset.
        detected_language = state.get("detected_language") or "en"
        if not state.get("detected_language"):
            from backend.conversation_context import detect_language_sticky
            history_rows = [
                {"role": m.get("role"), "message": m.get("content"), "metadata": {}}
                for m in prior
            ]
            detected_language = detect_language_sticky(
                current_message,
                history=history_rows,
                profile=user_context,
            )
        
        intent = intent_data.get("intent")
        confidence = float(intent_data.get("confidence", 0.7) or 0.7)
        requires_action = bool(intent_data.get("requires_action"))

        from backend.agent.user_guidance import assess_user_turn
        assessment = assess_user_turn(
            current_message, prior, intent, confidence=confidence,
        )
        if assessment.override_intent:
            intent = assessment.override_intent
        if intent in _ACTIONABLE_INTENTS:
            requires_action = True
        elif assessment.override_intent:
            requires_action = True

        guide_mode = assessment.guide_mode
        guidance_hint = assessment.guidance_hint

        # Merge entities across turns so follow-ups like "5 pounds tomorrow"
        # keep food_type/title from the prior donate/search turn.
        prior_entities = user_context.get("last_intent_entities") or {}
        new_entities = intent_data.get("entities") or {}
        merged_entities = dict(prior_entities)
        for key, value in new_entities.items():
            if value in (None, "", [], {}):
                continue
            # Classifier often emits false for confirmation flags — never downgrade.
            if key in (
                "community_confirmed", "post_confirmed", "skip_photo",
                "photo_prompted", "awaiting_post_confirm", "awaiting_photo_upload",
                "quantity_stated",
            ) and value is False:
                continue
            merged_entities[key] = value

        # Update state
        return {
            **state,
            "detected_intent": intent,
            "detected_language": detected_language,
            "user_context": {
                **user_context,
                "last_intent_entities": merged_entities,
                "guide_mode": guide_mode,
                "guidance_hint": guidance_hint,
                "intent_confidence": confidence,
            },
            "conversation_phase": "planning" if requires_action else "understanding",
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
    entities = enrich_entities_from_conversation(
        intent, entities, current_message, state.get("messages", []),
    )
    agent_debug_log(
        "graph.py:plan_task",
        "entities before plan",
        {
            "message_preview": (current_message or "")[:60],
            "community_confirmed": entities.get("community_confirmed"),
            "post_confirmed": entities.get("post_confirmed"),
            "awaiting_post_confirm": entities.get("awaiting_post_confirm"),
            "skip_photo": entities.get("skip_photo"),
            "photo_prompted": entities.get("photo_prompted"),
            "quantity_stated": entities.get("quantity_stated"),
            "title": entities.get("title"),
        },
        hypothesis_id="H3",
    )

    # Inject resolved listing reference
    resolved = state.get("user_context", {}).get("resolved_listing_ref")
    if resolved and intent in ("claim", "help", "navigate"):
        listing_id = resolved.get("id")
        if listing_id and not entities.get("listing_id"):
            entities = {**entities, "listing_id": listing_id}
    
    # Create plan based on intent
    try:
        plan = await create_plan(
            intent=intent,
            message=current_message,
            entities=entities,
            user_context=state.get("user_context", {}),
        )

        # Track intake flags implied by the planned ask_user step.
        if plan and isinstance(plan[0], dict):
            ask_q = (plan[0].get("tool_args") or {}).get("question") or ""
            ask_lo = ask_q.lower()
            if plan[0].get("tool_name") == "ask_user":
                if "photo" in ask_lo and "add" in ask_lo:
                    entities = {**entities, "photo_prompted": True}
                elif "ready when you are" in ask_lo or "camera" in ask_lo:
                    entities = {**entities, "photo_prompted": True, "awaiting_photo_upload": True}
                elif "quick check" in ask_lo or "post it?" in ask_lo:
                    entities = {**entities, "awaiting_post_confirm": True}

        return {
            **state,
            "active_plan": plan,
            "plan_goal": f"Complete {intent} task",
            "current_step": 0,
            "conversation_phase": "executing",
            "user_context": {
                **state.get("user_context", {}),
                "last_intent_entities": entities,
            },
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        
    except Exception as e:
        logger.error(f"Planning failed: {e}")
        return {
            **state,
            "error": f"Planning error: {str(e)}",
            "conversation_phase": "completed",
        }


def _step_succeeded(wrapped_result: Any) -> bool:
    """True when a plan step produced a usable tool outcome."""
    if not isinstance(wrapped_result, dict):
        return False
    if wrapped_result.get("ok") is False:
        return False
    if wrapped_result.get("requires_user_input") or wrapped_result.get("skipped"):
        return True
    inner = wrapped_result.get("result") if isinstance(wrapped_result.get("result"), dict) else wrapped_result
    if not isinstance(inner, dict):
        return True
    if inner.get("requires_user_input") or inner.get("skipped"):
        return True
    if inner.get("error") and inner.get("success") is not True:
        return False
    return True


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

        tool_name = current_step.get("tool_name") or "unknown"
        wrapped_result = (
            result if isinstance(result, dict) and result.get("tool") and "ok" in result
            else wrap_tool_result(tool_name, result)
        )

        # Store tool results for response generation
        recent_results = state.get("recent_tool_results", [])
        recent_results.append(wrapped_result)

        updated_plan = active_plan.copy()

        pending_from_step: Optional[Dict[str, Any]] = None
        if isinstance(wrapped_result, dict):
            pa = wrapped_result.get("pending_action")
            if isinstance(pa, dict):
                pending_from_step = pa
            elif isinstance(wrapped_result.get("result"), dict):
                inner_pa = wrapped_result["result"].get("pending_action")
                if isinstance(inner_pa, dict):
                    pending_from_step = inner_pa

        if pending_from_step is not None:
            updated_plan[current_step_idx] = {
                **current_step,
                "status": "pending_confirmation",
                "result": wrapped_result,
            }
            agent_debug_log(
                "graph.py:execute_tools",
                "post queued for confirmation",
                {
                    "tool": tool_name,
                    "wrapped_ok": wrapped_result.get("ok"),
                    "pending_id": pending_from_step.get("pending_id"),
                },
                hypothesis_id="H1,H5",
            )
            return {
                **state,
                "active_plan": updated_plan,
                "current_step": len(active_plan),  # skip remaining steps
                "recent_tool_results": recent_results[-5:],
                "pending_action": pending_from_step,
                "requires_user_input": True,
                "conversation_phase": "confirming",
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }

        step_ok = _step_succeeded(wrapped_result)
        step_status = "completed" if step_ok else "failed"
        updated_plan[current_step_idx] = {
            **current_step,
            "status": step_status,
            "result": wrapped_result,
        }

        if not step_ok:
            rolled_back: list[str] = []
            try:
                from backend.agent.actions import rollback_successful_writes
                prior_writes = [
                    tr for tr in recent_results[:-1]
                    if isinstance(tr, dict) and tr.get("ok")
                ]
                rolled_back = await rollback_successful_writes(
                    prior_writes,
                    user_id=state.get("user_id") or "",
                )
            except Exception as rb_exc:  # noqa: BLE001
                logger.warning("plan rollback failed: %s", rb_exc)

            return {
                **state,
                "active_plan": updated_plan,
                "current_step": len(active_plan),
                "recent_tool_results": recent_results[-5:],
                "error": f"Tool step failed: {tool_name}",
                "rolled_back_tools": rolled_back,
                "conversation_phase": "completed",
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }

        # Stop the plan when a step needs a user reply (ask_user) or when
        # a later step still has unfilled `{from_*}` placeholders.
        if isinstance(wrapped_result, dict) and (
            wrapped_result.get("requires_user_input")
            or wrapped_result.get("skipped")
            or (isinstance(wrapped_result.get("result"), dict) and (
                wrapped_result["result"].get("requires_user_input")
                or wrapped_result["result"].get("skipped")
            ))
        ):
            return {
                **state,
                "active_plan": updated_plan,
                "current_step": len(active_plan),
                "recent_tool_results": recent_results[-5:],
                "requires_user_input": True,
                "conversation_phase": "completed",
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }

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

        rolled_back: list[str] = []
        try:
            from backend.agent.actions import rollback_successful_writes
            prior = state.get("recent_tool_results", [])
            rolled_back = await rollback_successful_writes(
                [tr for tr in prior if isinstance(tr, dict) and tr.get("ok")],
                user_id=state.get("user_id") or "",
            )
        except Exception as rb_exc:  # noqa: BLE001
            logger.warning("plan rollback after exception failed: %s", rb_exc)
        
        return {
            **state,
            "active_plan": updated_plan,
            "error": f"Tool execution error: {str(e)}",
            "rolled_back_tools": rolled_back,
            "conversation_phase": "completed",
        }


def _build_response_prompt(
    *,
    system_prompt: str,
    conversation_context: str,
    tool_context: str,
    current_message: str,
    detected_intent: Optional[str],
    user_context: Dict[str, Any],
    pending_action: Optional[Dict[str, Any]],
    language: str,
    reasoning_block: str = "",
    plan_context: str = "",
) -> str:
    guide_mode = user_context.get("guide_mode") if isinstance(user_context, dict) else None
    guidance_hint = user_context.get("guidance_hint") or "(none)"
    pending_block = ""
    if isinstance(pending_action, dict) and pending_action:
        summary = str(pending_action.get("summary") or "").strip()
        pending_block = (
            f"\n**Pending confirmation (destructive action):** {summary or pending_action}\n"
            "Ask ONE natural yes/no confirmation question. The UI will show confirm/cancel buttons."
        )

    guide_block = ""
    if guide_mode or (guidance_hint and guidance_hint != "(none)"):
        guide_block = (
            f"\nUser clarity signal: guide_mode={guide_mode or 'none'}, hint={guidance_hint}\n"
            "If the user seems lost, gently clarify in your own words — stay warm and specific."
        )

    consciousness_block = ""
    if reasoning_block and reasoning_block.strip():
        consciousness_block = f"\n{reasoning_block.strip()}\n"

    return f"""{system_prompt}

{consciousness_block}{conversation_context}

{tool_context}
{plan_context}
{pending_block}
{guide_block}

User's current message: "{current_message}"
Detected intent: {detected_intent}
Response language: {"Spanish" if language == "es" else "English"}

Write as Nouri — present, attentive, and continuous across this thread.
- Echo back what you understood, then act or ask (one question max when gathering info).
- Ground claims in tool results and `<world>` / `<memory>` — never invent listings or success.
- If tools failed (success=false / ok=false), say what's still needed; never fake completion.
- If mid-flow on donate/claim/search, show you remember prior answers from the conversation.
- Search results → numbered list (1, 2, 3) of top items, then ask which they want.
- Bare "yes"/"ok" only counts as confirmation if your immediately prior turn asked yes/no."""


async def _generate_llm_response(
    state: AgentState,
    *,
    recent_results: List[Any],
    current_message: str,
    detected_intent: Optional[str],
    user_context: Dict[str, Any],
    language: str,
    pending_action: Optional[Dict[str, Any]] = None,
    conversation_phase: str = "idle",
) -> AgentState:
    """Single LLM path for all assistant replies — no scripted bypasses."""
    self_block = user_context.get("self_prompt_block") if isinstance(user_context, dict) else None
    register_block = user_context.get("register_prompt_block") if isinstance(user_context, dict) else None

    if not self_block:
        try:
            from backend.agent.self_model import build_self_model
            from backend.agent.safety import ScopeEnforcer
            uid = str(user_context.get("user_id") or user_context.get("id") or "")
            is_admin = bool(user_context.get("is_admin"))
            allowed = ScopeEnforcer.allowed_tools(uid, is_admin=is_admin)
            self_block = build_self_model(
                user_role=user_context.get("role") or user_context.get("community_role") or "user",
                is_admin=is_admin,
                allowed_tools=allowed,
            ).to_prompt_block()
        except Exception:
            pass

    from backend.agent.prompts import build_system_prompt_v2
    system_prompt = build_system_prompt_v2(
        user_context, language,
        self_block=self_block,
        affect_block=register_block,
    )

    v2_context_block = user_context.get("v2_context_block") if isinstance(user_context, dict) else None
    if v2_context_block and isinstance(v2_context_block, str) and v2_context_block.strip():
        system_prompt = f"{system_prompt}\n\n{v2_context_block.strip()}"

    reasoning_block = user_context.get("reasoning_block") if isinstance(user_context, dict) else None
    if not reasoning_block or not str(reasoning_block).strip():
        reasoning_block = ""

    memory_snapshot = user_context.get("memory_snapshot") if isinstance(user_context, dict) else None
    if memory_snapshot and isinstance(memory_snapshot, str) and memory_snapshot.strip():
        system_prompt = f"{system_prompt}\n\n{memory_snapshot.strip()}"

    resolved_ref = user_context.get("resolved_listing_ref") if isinstance(user_context, dict) else None
    if isinstance(resolved_ref, dict) and resolved_ref.get("id"):
        ref_title = resolved_ref.get("title") or "(item)"
        ref_id = resolved_ref.get("id")
        ref_owner = resolved_ref.get("listing_owner_id") or "?"
        system_prompt += (
            f"\n\nREFERENCE RESOLVED: The user's message refers to "
            f"listing_id={ref_id} (title='{ref_title}', listing_owner_id={ref_owner}). "
            f"Use THIS listing_id for claim/cancel/route tools unless the user "
            f"clearly meant a different item."
        )

    tool_context = ""
    if recent_results:
        tool_context = "\n\n**Tool Results:**\n"
        for i, result in enumerate(recent_results[-3:], 1):
            tool_context += f"{i}. {json.dumps(result, indent=2)[:800]}\n"
            if isinstance(result, dict) and result.get("tool") == "post_food_listing":
                inner = result.get("result") if isinstance(result.get("result"), dict) else result
                pending = result.get("pending_action") or (
                    inner.get("pending_action") if isinstance(inner, dict) else None
                )
                agent_debug_log(
                    "graph.py:generate_response",
                    "post_food_listing tool result for LLM",
                    {
                        "ok": result.get("ok"),
                        "inner_success": inner.get("success") if isinstance(inner, dict) else None,
                        "listing_id": inner.get("listing_id") if isinstance(inner, dict) else None,
                        "has_pending_action": bool(pending),
                        "requires_confirmation": (
                            inner.get("requires_confirmation") if isinstance(inner, dict) else None
                        ),
                        "error": inner.get("error") if isinstance(inner, dict) else None,
                    },
                    hypothesis_id="H1,H4",
                )
                if pending:
                    tool_context += (
                        "\n**NOT POSTED YET** — post_food_listing is queued for user "
                        "confirmation. Do NOT say 'Posted!' or that the listing is live. "
                        "Ask the user to confirm or cancel using the buttons.\n"
                    )
                elif isinstance(inner, dict) and inner.get("success") and inner.get("listing_id"):
                    tool_context += (
                        f"\n**LISTING POSTED SUCCESSFULLY** — listing_id={inner['listing_id']}. "
                        "Lead with 'Posted!' and the listing number. Do NOT ask for more details "
                        "or say you are about to post; the write already completed.\n"
                    )

    plan_context = ""
    active_plan = state.get("active_plan") or []
    entities = (user_context or {}).get("last_intent_entities") or {}
    if active_plan or entities:
        plan_summary = {
            "goal": state.get("plan_goal"),
            "steps": [
                {
                    "action": s.get("action"),
                    "tool": s.get("tool_name"),
                    "status": s.get("status"),
                }
                for s in active_plan[:6]
                if isinstance(s, dict)
            ],
            "entities_in_progress": {
                k: v for k, v in entities.items()
                if v not in (None, "", [], {}) and k in (
                    "title", "food_type", "quantity", "community_name",
                    "community_confirmed", "expiry_date", "location",
                    "listing_id",
                )
            },
        }
        if plan_summary["steps"] or plan_summary["entities_in_progress"]:
            plan_context = f"\n**Task in progress:**\n{json.dumps(plan_summary, indent=2)[:900]}\n"

    conversation_context = ""
    messages = state.get("messages", [])
    if messages:
        conversation_context = "\n\n**Recent Conversation:**\n"
        for msg in messages[-15:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")[:800]
            conversation_context += f"{role}: {content}\n"

    response_prompt = _build_response_prompt(
        system_prompt=system_prompt,
        conversation_context=conversation_context,
        tool_context=tool_context,
        current_message=current_message,
        detected_intent=detected_intent,
        user_context=user_context,
        pending_action=pending_action,
        language=language,
        reasoning_block=str(reasoning_block or ""),
        plan_context=plan_context,
    )

    model = _get_model(temperature=0.85)
    response = await model.ainvoke([HumanMessage(content=response_prompt)])
    response_text = (response.content or "").strip()

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
        "messages": updated_messages[-50:],
        "conversation_phase": conversation_phase,
        "turn_count": state.get("turn_count", 0) + 1,
        "last_updated": datetime.now(timezone.utc).isoformat(),
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
    pending_action = state.get("pending_action")

    try:
        return await _generate_llm_response(
            state,
            recent_results=recent_results,
            current_message=current_message,
            detected_intent=detected_intent,
            user_context=user_context,
            language=language,
            pending_action=pending_action,
            conversation_phase="confirming" if pending_action else "idle",
        )
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
        from backend.agent.learning import update_user_preferences
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

    if intent in _ACTIONABLE_INTENTS:
        return "plan"

    if state.get("conversation_phase") == "planning":
        return "plan"

    if intent in ("search",) and state.get("active_plan"):
        return "execute"

    return "respond"


def plan_complete(state: AgentState) -> Literal["execute_next", "respond"]:
    """Check if there are more steps to execute."""
    # A destructive step that queued a pending_action envelope aborts the
    # rest of the plan — subsequent steps can only run after the user
    # confirms via /api/ai/confirm.
    if state.get("pending_action"):
        return "respond"

    active_plan = state.get("active_plan", [])
    current_step = state.get("current_step", 0)

    if active_plan and current_step > 0:
        prev_idx = current_step - 1
        if prev_idx < len(active_plan):
            prev = active_plan[prev_idx]
            if isinstance(prev, dict) and prev.get("status") == "failed":
                return "respond"

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
# Telemetry
# ============================================================================

async def _log_agent_telemetry(
    user_id: str,
    conversation_id: str,
    final_state: Optional[Dict[str, Any]],
    total_execution_time_ms: int,
    error: Optional[BaseException] = None,
) -> None:
    """Best-effort insert into agent_telemetry. Never raises.

    Wired in fire-and-forget mode so a telemetry failure (network, missing
    table, RLS misconfig) can never break a user-facing chat turn.
    """
    # Skip for anonymous / nil-UUID sessions — agent_telemetry.user_id has a
    # NOT NULL FK to users(id), so nil UUIDs raise 23503 (409 via PostgREST).
    if not user_id or user_id.startswith("00000000"):
        return
    try:
        from backend.ai_engine import supabase_post

        state = final_state or {}
        tool_results = state.get("recent_tool_results") or []
        tool_names: List[str] = []
        success_count = 0
        failure_count = 0
        for tr in tool_results:
            if not isinstance(tr, dict):
                continue
            name = tr.get("tool") or tr.get("name")
            if name:
                tool_names.append(str(name))
            res = tr.get("result") if isinstance(tr.get("result"), dict) else None
            ok = bool(tr.get("ok")) or (res or {}).get("success") is True
            if ok:
                success_count += 1
            else:
                failure_count += 1

        response_text = state.get("response_text") or ""
        suggestions = state.get("pending_suggestions") or []
        active_plan = state.get("active_plan") or []

        row: Dict[str, Any] = {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "detected_intent": state.get("detected_intent"),
            "detected_language": state.get("detected_language") or "en",
            "tools_called": tool_names,
            "tool_success_count": success_count,
            "tool_failure_count": failure_count,
            "response_generated": bool(response_text),
            "response_length": len(response_text),
            "total_execution_time_ms": int(total_execution_time_ms),
            "plan_created": bool(active_plan),
            "plan_steps_count": len(active_plan),
            "plan_steps_completed": int(state.get("current_step") or 0),
            "suggestions_generated": len(suggestions),
            "error_occurred": error is not None or bool(state.get("error")),
        }
        if error is not None:
            row["error_message"] = str(error)[:1000]
            row["error_type"] = type(error).__name__
        elif state.get("error"):
            row["error_message"] = str(state.get("error"))[:1000]

        await supabase_post("agent_telemetry", row)
    except Exception as exc:  # noqa: BLE001 — telemetry must never raise
        logger.warning("agent_telemetry insert failed (non-fatal): %s", exc)


# ============================================================================
# Main Invocation Function
# ============================================================================

async def invoke_agent(
    user_id: str,
    message: str,
    conversation_id: Optional[str] = None,
    user_context: Optional[Dict[str, Any]] = None,
    *,
    silent: bool = False,
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
    from backend.conversation_store import get_conversation_history, store_message
    from backend.conversation_context import (
        build_memory_snapshot,
        detect_language_sticky,
        filter_history_for_context,
        resolve_listing_reference,
    )
    import uuid
    
    # Create or load conversation state
    if not conversation_id:
        conversation_id = str(uuid.uuid4())

    _t0 = time.monotonic()

    # Normalize profile context: Supabase rows use `id`, tools expect `user_id`.
    normalized_context = dict(user_context or {"user_id": user_id})
    normalized_context.setdefault("user_id", user_id)
    normalized_context.setdefault("id", user_id)

    # Load persisted history (with metadata for listing reference resolution).
    prior_messages: list[Message] = []
    history_rows: list[dict] = []
    if user_id and not user_id.startswith("00000000"):
        try:
            history_rows = await get_conversation_history(user_id, limit=30)
            history_rows = filter_history_for_context(history_rows)
            for row in history_rows:
                prior_messages.append(Message(
                    role=row.get("role", "user"),
                    content=(row.get("message") or "")[:4000],
                    timestamp=row.get("created_at") or "",
                    tool_calls=None,
                    tool_results=None,
                ))
        except Exception as exc:  # noqa: BLE001
            logger.warning("history load failed for %s: %s", user_id, exc)

    if history_rows:
        for row in reversed(history_rows):
            meta = row.get("metadata") or {}
            saved = meta.get("intent_entities")
            if isinstance(saved, dict) and saved:
                normalized_context["last_intent_entities"] = dict(saved)
                break

    # New share flow — discard persisted intake from a prior listing in this thread.
    if re.search(
        r"\b(want to share|share (some )?food|i('d| would) like to (share|donate)|"
        r"donate food|post a listing|publicar)\b",
        (message or ""),
        re.I,
    ):
        normalized_context.pop("last_intent_entities", None)

    sticky_lang = detect_language_sticky(message, history=history_rows, profile=normalized_context)
    resolved_listing = resolve_listing_reference(message, history_rows)
    memory_snapshot = build_memory_snapshot(history_rows)

    if resolved_listing:
        normalized_context["resolved_listing_ref"] = resolved_listing
    if memory_snapshot:
        normalized_context["memory_snapshot"] = memory_snapshot

    normalized_context["conversation_id"] = conversation_id
    turn_id = str(uuid.uuid4())
    normalized_context["turn_id"] = turn_id

    if user_id and not user_id.startswith("00000000"):
        try:
            from backend.agent.learning import get_user_preferences, get_preferred_search_params
            prefs = await get_user_preferences(user_id)
            normalized_context["learned_preferences"] = prefs
            normalized_context["preferred_search_params"] = get_preferred_search_params(prefs)
        except Exception as exc:  # noqa: BLE001
            logger.debug("preference load skipped: %s", exc)

    # Long-term memory + world snapshot for v1-only turns (v2 injects its own block).
    if (
        user_id
        and not user_id.startswith("00000000")
        and not normalized_context.get("v2_context_block")
        and not normalized_context.get("agent_v2")
    ):
        try:
            from backend.agent.memory import retrieve_relevant_memories
            from backend.agent.world_model import build_world_snapshot
            from backend.agent.context_block import format_v2_context_block

            mem_task = retrieve_relevant_memories(user_id, message, limit=3)
            world_task = build_world_snapshot(
                user_id,
                is_admin=bool(normalized_context.get("is_admin")),
            )
            memories, world = await asyncio.wait_for(
                asyncio.gather(mem_task, world_task, return_exceptions=True),
                timeout=4.0,
            )
            mem_list = memories if isinstance(memories, list) else []
            world_snap = world if not isinstance(world, Exception) else None
            ctx_block = format_v2_context_block(
                world=world_snap,
                memories=mem_list,
            )
            if ctx_block:
                normalized_context["v2_context_block"] = ctx_block
        except Exception as exc:  # noqa: BLE001
            logger.debug("v1 memory/world load skipped: %s", exc)

    # Initialize state
    initial_state: AgentState = {
        "conversation_id": conversation_id,
        "user_id": user_id,
        "current_message": message,
        "messages": prior_messages,
        "user_context": normalized_context,
        "detected_language": sticky_lang,
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

        # Fire-and-forget telemetry write so analytics doesn't add latency.
        try:
            asyncio.create_task(_log_agent_telemetry(
                user_id=user_id,
                conversation_id=conversation_id,
                final_state=final_state,
                total_execution_time_ms=int((time.monotonic() - _t0) * 1000),
                error=None,
            ))
        except Exception:  # noqa: BLE001
            pass

        response_text = final_state.get("response_text", "")
        lang = final_state.get("detected_language", "en")
        tool_results = normalize_tool_results(final_state.get("recent_tool_results", []))
        assistant_row_id: Optional[str] = None

        # After a successful post, clear intake flags so the next message cannot re-post.
        posted_ok = any(
            isinstance(tr, dict) and tr.get("tool") == "post_food_listing" and tr.get("ok")
            for tr in tool_results
        )
        if posted_ok and isinstance(final_state.get("user_context"), dict):
            cleared = dict(final_state["user_context"].get("last_intent_entities") or {})
            for k in (
                "title", "food_type", "quantity", "quantity_stated", "unit",
                "community_confirmed", "post_confirmed", "photo_prompted",
                "skip_photo", "awaiting_photo_upload", "awaiting_post_confirm",
                "expiry_date", "image_url", "location", "community_name",
            ):
                cleared.pop(k, None)
            final_state["user_context"]["last_intent_entities"] = cleared

        # Persist this turn so the next request has context (matches legacy engine).
        if user_id and user_id != _NIL_UUID and not user_id.startswith("00000000"):
            try:
                metadata: Dict[str, Any] = {"lang": lang, "agentic": True}
                compact = compact_actions_for_metadata(tool_results)
                if compact:
                    metadata["actions"] = compact
                intent_entities = (final_state.get("user_context") or {}).get("last_intent_entities") or {}
                if isinstance(intent_entities, dict) and intent_entities:
                    metadata["intent_entities"] = {
                        k: v for k, v in intent_entities.items()
                        if k in (
                            "title", "food_type", "quantity", "quantity_stated", "unit",
                            "community_name", "community_id", "community_confirmed",
                            "expiry_date", "location", "image_url",
                            "photo_prompted", "skip_photo", "awaiting_photo_upload",
                            "post_confirmed", "awaiting_post_confirm",
                        ) and v not in (None, "", [], {})
                    }
                if not silent:
                    await store_message(user_id, "user", message)
                assistant_row_id = await store_message(
                    user_id,
                    "assistant",
                    response_text,
                    metadata=metadata,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("agent message persist failed for %s: %s", user_id, exc)

        user_ctx = final_state.get("user_context") or {}
        guide_mode = user_ctx.get("guide_mode") if isinstance(user_ctx, dict) else None
        if should_load_active_communities(response_text, message, user_ctx):
            try:
                from backend.tools import _get_active_communities
                comm_result = await _get_active_communities(
                    user_id=user_id,
                    max_results=20,
                )
                user_ctx = {
                    **user_ctx,
                    "active_communities": (comm_result or {}).get("communities") or [],
                }
            except Exception as exc:  # noqa: BLE001
                logger.warning("active communities prefetch failed: %s", exc)
        suggestions = build_turn_suggestions(
            response_text=response_text,
            language=lang,
            tool_results=tool_results,
            pending_suggestions=final_state.get("pending_suggestions"),
            detected_intent=final_state.get("detected_intent"),
            guide_mode=guide_mode,
            user_context=user_ctx,
            last_user_message=message or "",
        )

        return {
            "text": response_text,
            "user_id": user_id,
            "conversation_id": assistant_row_id or conversation_id,
            "turn_id": turn_id,
            "lang": lang,
            "tool_results": tool_results,
            "suggestions": suggestions,
            "timestamp": final_state.get("last_updated"),
            "pending_action": final_state.get("pending_action"),
        }
        
    except Exception as e:
        logger.error(f"Agent invocation failed: {e}")
        try:
            asyncio.create_task(_log_agent_telemetry(
                user_id=user_id,
                conversation_id=conversation_id,
                final_state=None,
                total_execution_time_ms=int((time.monotonic() - _t0) * 1000),
                error=e,
            ))
        except Exception:  # noqa: BLE001
            pass

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
