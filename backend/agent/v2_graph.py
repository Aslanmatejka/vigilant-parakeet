"""
AGENT_V2 Graph Wrapper (Slice A)
=================================

Wraps the existing LangGraph workflow with new pre- and post-nodes:

    safety_in -> classify_affect -> build_self_model
        -> (existing v1 graph: understand → plan → execute → respond → proactive → learn)
        -> reflect -> self_eval -> safety_out

Design notes:

- The existing v1 graph (`backend.agent.graph.create_agent_graph`) is untouched.
- We invoke it as a subgraph from inside `invoke_agent_v2()`. That keeps the
  blast radius small: any v2 bug short-circuits to the v1 result.
- All new fields written into `AgentState` are optional (`total=False`), so
  legacy consumers ignore them.
- This module is feature-flagged: callers should only route here when
  `AGENT_V2` env var is true. The legacy `invoke_agent()` is unchanged.

Slice A scope (this file):
- Pre: InputGuard, affect classification, self-model build, scope enforcement
       inputs.
- Wrap: invoke existing v1 graph.
- Post: FoodSafetyGate filter on returned listings, PersonaGuard check,
        OutputSanitizer scrub, calibrated refusal copy when blocked.

Out of scope (Slice B+):
- Explicit `think` / `reflect` LLM nodes (we use the v1 plan/execute/respond
  loop as the action layer; v2 only adds wrappers around it).
- Goal stack persistence to `agent_goals`.
- Memory retrieval / write.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.agent.affect import (
    Affect,
    Register,
    classify_affect_heuristic,
    classify_affect_llm,
    select_register,
)
from backend.agent.reasoning import (
    Reflection,
    Thought,
    calibrated_clarification_text,
    calibrated_refusal_text as _reasoning_refusal_text,
    decide,
    reflect_heuristic,
    reflect_llm,
    think_heuristic,
    think_llm,
)
from backend.agent.goals import (
    Goal,
    extract_goals_heuristic,
    extract_goals_llm,
    prioritize_goals,
    replan_suggestion,
    update_status_from_reflection,
)
from backend.agent.memory import (
    MemoryItem,
    extract_salient_facts,
    extract_salient_facts_llm,
    privacy_disclosure_text,
    retrieve_relevant_memories,
    write_memories,
)
from backend.agent.world_model import (
    WorldSnapshot,
    build_world_snapshot,
)
from backend.agent.self_eval import (
    SelfEvaluation,
    detect_pushback,
    evaluate_response_heuristic,
    evaluate_response_llm,
    should_retry,
    surface_uncertainty,
)
from backend.agent.refine import (
    refine_response_heuristic,
    refine_response_llm,
)
from backend.agent.adaptation import (
    TrajectoryRecord,
    UserStyle,
    compute_reward,
    format_few_shot_examples,
    record_trajectory,
    retrieve_similar_trajectories,
    summarise_user_style,
)
from backend.agent.curiosity import (
    generate_followup_heuristic,
    generate_followup_llm,
    should_ask_followup,
)
from backend.agent.context_block import format_v2_context_block
from backend.agent.confirmation_policy import (
    any_confirmation_required,
    decide_for_intent,
    evaluate_tool_results,
    format_decision_summary,
)
from backend.agent.procedural import (
    AntiPatternRule,
    ProceduralRule,
    fetch_recent_trajectories,
    format_antipattern_hint,
    format_procedural_hint,
    mine_antipatterns,
    mine_procedural_rules,
    select_antipattern_for_intent,
    select_rule_for_intent,
)
from backend.agent.brainstorm import (
    brainstorm_heuristic,
    brainstorm_llm,
    detect_brainstorm_intent,
    extract_count as _bs_extract_count,
    extract_topic as _bs_extract_topic,
    format_ideas_as_response,
)
from backend.agent.safety import (
    FoodSafetyGate,
    InputGuard,
    OutputSanitizer,
    SafetyDecision,
    ScopeEnforcer,
)
from backend.agent.self_model import PersonaGuard, build_self_model
from backend.agent.pending_intercept import (
    build_intercepted_action,
    build_pending_action_envelope,
    format_intercept_text,
)
from backend.agent.telemetry import log_v2_turn

logger = logging.getLogger(__name__)


# ============================================================================
# Feature flag
# ============================================================================

def is_agent_v2_enabled() -> bool:
    """Read the AGENT_V2 env var. Defaults to false so v2 is opt-in.

    Note: for per-user rollout use
    ``backend.agent.rollout.is_agent_v2_enabled_for_user`` — this helper
    only reports the master switch.
    """
    return os.getenv("AGENT_V2", "false").strip().lower() in ("true", "1", "yes", "on")


# ============================================================================
# Helpers
# ============================================================================

def _calibrated_refusal_text(decision: SafetyDecision, language: str = "en") -> str:
    """Map a SafetyDecision into user-facing copy. `decision.reason` is already
    user-friendly per the safety module — but we localize a thin wrapper."""
    msg = decision.reason or "I can't help with that right now."
    return msg


def _filter_safety_in_tool_results(tool_results: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Apply FoodSafetyGate to any listings returned by search tools.

    Returns (filtered_tool_results, blocked_listings). The blocked listings
    are surfaced to admins via state, but never to the user."""
    if not tool_results:
        return [], []

    blocked_all: list[dict[str, Any]] = []
    out: list[dict[str, Any]] = []

    SEARCH_TOOL_NAMES = {
        "search_food_near_user", "search_food_nearby",
        "get_recent_listings", "get_my_claims",
        "get_community_listings",
    }

    for tr in tool_results:
        if not isinstance(tr, dict):
            out.append(tr)
            continue

        tool_name = tr.get("tool") or tr.get("name")
        if tool_name not in SEARCH_TOOL_NAMES:
            out.append(tr)
            continue

        result = tr.get("result") if isinstance(tr.get("result"), dict) else None
        if not result:
            out.append(tr)
            continue

        listings = result.get("listings")
        if not isinstance(listings, list) or not listings:
            out.append(tr)
            continue

        safe, blocked = FoodSafetyGate.filter(listings)
        for d in blocked:
            blocked_all.append({
                "code": d.code,
                "reason": d.reason,
                "severity": d.severity,
                **(d.metadata or {}),
            })

        if len(safe) == len(listings):
            out.append(tr)
            continue

        # Rewrite this tool result with the filtered list.
        new_result = dict(result)
        new_result["listings"] = safe
        new_result["found"] = len(safe)
        if "filtered_count" not in new_result:
            new_result["filtered_count"] = len(listings) - len(safe)
        new_tr = dict(tr)
        new_tr["result"] = new_result
        out.append(new_tr)

    return out, blocked_all


# ============================================================================
# Audit log: record every successful WRITE the v1 graph performed.
# ============================================================================

async def _audit_write_tools(
    tool_results: list[dict[str, Any]],
    *,
    user_id: str,
    turn_id: str,
    conversation_id: Optional[str],
) -> list[dict[str, Any]]:
    """Walk the v1 tool trace and write `agent_audit_log` rows for any tool
    call that maps to a registered AGENT_V2 action.

    This gives admins an observable trail of every WRITE the agent took on
    behalf of the user, even though the v1 graph executed the tool directly.
    Best-effort: a DB error here NEVER blocks the user response.

    Returns a list of `{tool, status, audit_id}` rows the caller can surface
    to the frontend (debug-mode only).
    """
    if not tool_results:
        return []

    try:
        from backend.agent.actions import get_action, redact_args
        from backend.ai_engine import supabase_post
    except Exception:  # noqa: BLE001 — module-load failure short-circuits.
        return []

    audited: list[dict[str, Any]] = []
    for tr in tool_results:
        if not isinstance(tr, dict):
            continue
        tool_name = tr.get("tool") or tr.get("name")
        if not tool_name:
            continue
        spec = get_action(tool_name)
        if not spec:
            continue  # not a registered WRITE — skip

        result = tr.get("result") if isinstance(tr.get("result"), dict) else None
        args = tr.get("args") if isinstance(tr.get("args"), dict) else None
        # Treat the tool as successful only if its dict-shaped result said so.
        ok = bool(result and (result.get("success") or result.get("ok")) and not result.get("error"))

        # Pull a best-effort target_id out of the legacy return shape.
        target_id: str | None = None
        if isinstance(result, dict):
            for key in ("claim_id", "listing_id", "notification_id", "reminder_id", "id"):
                val = result.get(key)
                if val:
                    target_id = str(val)
                    break

        try:
            rows = await supabase_post("agent_audit_log", {
                "actor_user_id": user_id,
                "turn_id": turn_id,
                "conversation_id": conversation_id,
                "tool_name": tool_name,
                "args_redacted": redact_args(args or {}),
                "before_state": None,  # v1 did not capture it; Slice C will.
                "after_state": result if ok else None,
                "target_table": _action_target_table(tool_name),
                "target_id": target_id,
                "status": "committed" if ok else "failed",
                "rollback_token": None,
                "error_message": (None if ok else str(result.get("error") if isinstance(result, dict) else "tool failed")[:1000]),
            })
            audit_id = None
            if isinstance(rows, list) and rows:
                audit_id = rows[0].get("id")
            audited.append({
                "tool": tool_name,
                "status": "committed" if ok else "failed",
                "audit_id": audit_id,
                "target_id": target_id,
            })
        except Exception as exc:  # noqa: BLE001
            logger.warning("audit insert failed for tool %s: %s", tool_name, exc)
    return audited


# Map registered action names to their primary target table. Kept here (not
# on ActionSpec) so the v1 trace audit can fill in target_table without
# re-running the handler.
_ACTION_TARGET_TABLES: dict[str, str] = {
    "claim_listing": "food_claims",
    "cancel_claim": "food_claims",
    "post_food_listing": "food_listings",
    "create_food_listing": "food_listings",
    "update_food_listing": "food_listings",
    "edit_listing": "food_listings",
    "delete_listing": "food_listings",
    "deactivate_listing": "food_listings",
    "update_user_profile": "users",
    "set_dietary_preferences": "users",
    "send_notification": "notifications",
    "mark_notifications_read": "notifications",
    "dismiss_notification": "notifications",
    "dismiss_all_notifications": "notifications",
    "create_reminder": "reminders",
    "forget_about_me": "agent_user_facts",
    "message_donor": "notifications",
    "schedule_pickup": "reminders",
    "join_community": "users",
    "leave_community": "users",
}


def _action_target_table(name: str) -> str | None:
    return _ACTION_TARGET_TABLES.get(name)


# ============================================================================
# Main entry point
# ============================================================================

async def invoke_agent_v2(
    user_id: str,
    message: str,
    conversation_id: Optional[str] = None,
    user_context: Optional[Dict[str, Any]] = None,
    *,
    is_admin: bool = False,
    channel: str = "text",
) -> Dict[str, Any]:
    """V2 agent entry point. Mirrors `invoke_agent()` signature so the chat
    endpoint can route between them based on the feature flag.

    Returns the same response shape as `invoke_agent()` PLUS optional
    `pending_action`, `refusal`, `affect`, `confidence` fields the frontend
    may use to render confirmation cards, refusal copy, and dev-mode debug.
    """
    from backend.agent.graph import invoke_agent as _invoke_v1
    from backend.agent.prompts import ERROR_RESPONSES

    t0 = time.monotonic()
    conversation_id = conversation_id or str(uuid.uuid4())
    turn_id = str(uuid.uuid4())

    user_context = user_context or {"user_id": user_id}
    detected_language = user_context.get("language") or "en"

    # ----------- 1. Input safety check -----------
    input_decision = InputGuard.scan(message)
    if not input_decision.allowed:
        logger.info("InputGuard refused turn for user=%s code=%s", user_id, input_decision.code)
        # Emit one calibrated refusal; skip the v1 graph entirely.
        refusal = OutputSanitizer.scrub(_calibrated_refusal_text(input_decision, detected_language))
        return {
            "text": refusal,
            "user_id": user_id,
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "lang": detected_language,
            "tool_results": [],
            "suggestions": [],
            "refusal": {"code": input_decision.code, "severity": input_decision.severity},
            "agent_v2": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ----------- 1a. Pushback detection (Phase 7) -------------------------
    # Cheap regex on the user message. The flag is surfaced in the response
    # envelope; downstream the next turn's reasoning head can use it to
    # switch into a clarifying loop instead of doubling down.
    pushback_detected = detect_pushback(message)
    if pushback_detected:
        logger.info("pushback detected for user=%s", user_id)

    # ----------- 2. Affect classification + register selection -----------
    # Cheap; run in background-tolerant mode. If the LLM call hangs we fall
    # back to the heuristic so we don't add latency on top of the v1 graph.
    affect: Affect
    try:
        affect = await asyncio.wait_for(classify_affect_llm(message), timeout=4.0)
    except asyncio.TimeoutError:
        logger.info("affect LLM classify timed out — using heuristic")
        affect = classify_affect_heuristic(message)
    except Exception as exc:  # noqa: BLE001
        logger.info("affect classify error (%s) — using heuristic", exc)
        affect = classify_affect_heuristic(message)

    register: Register = select_register(affect, channel=channel)

    # ----------- 3. Self-model build (for grounded "what can you do?") -----
    allowed_tools = ScopeEnforcer.allowed_tools(user_id, is_admin=is_admin)
    self_model = build_self_model(
        user_role=user_context.get("role") or "user",
        is_admin=is_admin,
        allowed_tools=allowed_tools,
        open_goal_count=0,  # filled in after goal extraction below
    )

    # NOTE: For Slice A we do not yet inject the V2 system prompt into the
    # v1 graph — the v1 nodes build their own prompts internally. The
    # self-model + affect blocks are still surfaced in the final state for
    # observability and frontend consumption, and Slice B will rewire the
    # generator to use `build_system_prompt_v2`.

    # ----------- 3a-pre. Extract goals (Phase 2 lite) ----------------------
    # One short LLM call (gpt-4o-mini) decomposes the user message into
    # typed goals. Heuristic fallback handles offline/error paths.
    try:
        goals: list[Goal] = await asyncio.wait_for(
            extract_goals_llm(message, user_id=user_id, language=detected_language),
            timeout=4.0,
        )
    except asyncio.TimeoutError:
        logger.info("extract_goals LLM timed out — using heuristic")
        goals = extract_goals_heuristic(message, user_id)
    except Exception as exc:  # noqa: BLE001
        logger.info("extract_goals error (%s) — using heuristic", exc)
        goals = extract_goals_heuristic(message, user_id)
    goals = prioritize_goals(goals)
    # Reflect open goal count into the self-model snapshot so
    # "what are you working on?" stays accurate.
    self_model.open_goal_count = sum(1 for g in goals if g.status == "open")

    # ----------- 3a-mid. Memory retrieval + world snapshot + style (Phase 3+6) -
    # Fetch in parallel — every call has a graceful fallback, so a
    # Supabase outage just produces empty context rather than a turn
    # failure. Anonymous (nil-UUID) sessions skip all three queries.
    memories: list[MemoryItem] = []
    world: WorldSnapshot = WorldSnapshot(user_id=user_id, is_admin=is_admin)
    user_style: UserStyle = UserStyle()
    if user_id and not user_id.startswith("00000000"):
        try:
            mem_task = retrieve_relevant_memories(user_id, message, limit=3)
            world_task = build_world_snapshot(user_id, is_admin=is_admin)
            style_task = summarise_user_style(user_id)
            mem_result, world_result, style_result = await asyncio.wait_for(
                asyncio.gather(
                    mem_task, world_task, style_task, return_exceptions=True,
                ),
                timeout=4.0,
            )
            if isinstance(mem_result, list):
                memories = mem_result
            if isinstance(world_result, WorldSnapshot):
                world = world_result
            if isinstance(style_result, UserStyle):
                user_style = style_result
        except asyncio.TimeoutError:
            logger.info("memory+world+style fetch timed out — proceeding without")
        except Exception as exc:  # noqa: BLE001
            logger.info("memory+world+style fetch failed (%s) — proceeding without", exc)

    # ----------- 3a. Explicit ReAct think + decide (Phase 1) ----------------
    # Single short LLM call (gpt-4o-mini) to produce a Thought, then a pure
    # decide() step that may short-circuit the v1 graph for refusals or
    # clarification requests. Heuristic fallback keeps offline tests green.
    try:
        thought: Thought = await asyncio.wait_for(
            think_llm(
                message,
                affect_dominant=affect.dominant,
                self_role=user_context.get("role") or "user",
            ),
            timeout=4.0,
        )
    except asyncio.TimeoutError:
        logger.info("think LLM timed out — using heuristic")
        thought = think_heuristic(message)
    except Exception as exc:  # noqa: BLE001
        logger.info("think error (%s) — using heuristic", exc)
        thought = think_heuristic(message)

    chosen_decision = decide(thought)

    # ----------- 3b. Few-shot trajectory retrieval (Phase 6) -------------
    # Now that we have an intent we can pull the user's most successful
    # past trajectories that match. Strictly best-effort: an outage,
    # nil-UUID, or no qualifying history all return [].
    similar_trajectories: list[TrajectoryRecord] = []
    if user_id and not user_id.startswith("00000000"):
        try:
            similar_trajectories = await asyncio.wait_for(
                retrieve_similar_trajectories(
                    user_id, message,
                    query_intent=thought.intent or "",
                    limit=3,
                ),
                timeout=3.0,
            )
        except asyncio.TimeoutError:
            logger.info("few-shot trajectory fetch timed out — proceeding without")
        except Exception as exc:  # noqa: BLE001
            logger.info("few-shot trajectory fetch failed (%s) — proceeding without", exc)

    # ----------- 3b-bis. Procedural rule mining (Phase 6 mid) -------------
    # Two-tier: try the persisted cache first (`agent_procedural_rules`,
    # populated by scripts/mine_procedural_rules_nightly.py --persist).
    # If nothing hits for this user+intent, fall back to inline mining
    # over the last 50 trajectories.
    procedural_rule: ProceduralRule | None = None
    procedural_hint_text: str = ""
    antipattern_rule: AntiPatternRule | None = None
    antipattern_hint_text: str = ""
    if user_id and not user_id.startswith("00000000") and thought.intent:
        # ---- Tier 1: persisted cache ----
        try:
            from backend.agent.procedural_store import (
                fetch_antipattern_rules,
                fetch_procedural_rules,
            )
            cached_rules_task = fetch_procedural_rules(
                user_id, intent=thought.intent, limit=5,
            )
            cached_anti_task = fetch_antipattern_rules(
                user_id, intent=thought.intent, limit=5,
            )
            cached_rules, cached_anti = await asyncio.wait_for(
                asyncio.gather(
                    cached_rules_task, cached_anti_task,
                    return_exceptions=True,
                ),
                timeout=2.0,
            )
            if isinstance(cached_rules, list) and cached_rules:
                procedural_rule = select_rule_for_intent(
                    cached_rules, thought.intent,
                )
                procedural_hint_text = format_procedural_hint(
                    procedural_rule, language=detected_language,
                )
            if isinstance(cached_anti, list) and cached_anti:
                antipattern_rule = select_antipattern_for_intent(
                    cached_anti, thought.intent,
                )
                antipattern_hint_text = format_antipattern_hint(
                    antipattern_rule, language=detected_language,
                )
        except asyncio.TimeoutError:
            logger.info("procedural cache fetch timed out — falling back to inline")
        except Exception as exc:  # noqa: BLE001
            logger.info("procedural cache unavailable (%s) — falling back to inline", exc)

        # ---- Tier 2: inline mining fallback ----
        if not procedural_rule and not antipattern_rule:
            try:
                recent_trajectories = await asyncio.wait_for(
                    fetch_recent_trajectories(user_id, limit=50),
                    timeout=3.0,
                )
                rules = mine_procedural_rules(recent_trajectories)
                procedural_rule = select_rule_for_intent(rules, thought.intent)
                procedural_hint_text = format_procedural_hint(
                    procedural_rule, language=detected_language,
                )
                antipatterns = mine_antipatterns(recent_trajectories)
                antipattern_rule = select_antipattern_for_intent(
                    antipatterns, thought.intent,
                )
                antipattern_hint_text = format_antipattern_hint(
                    antipattern_rule, language=detected_language,
                )
            except asyncio.TimeoutError:
                logger.info("procedural mining timed out — proceeding without")
            except Exception as exc:  # noqa: BLE001
                logger.info("procedural mining failed (%s) — proceeding without", exc)

    # If the reasoning head is confident the right move is to refuse or
    # clarify, skip v1 entirely — answer directly with calibrated copy so we
    # don't burn tokens running the planner against a malformed turn.
    if chosen_decision in ("refuse", "ask_clarification"):
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        if chosen_decision == "refuse":
            short_text = _reasoning_refusal_text(thought, detected_language)
            refusal_block = {
                "code": "reasoning_refusal",
                "severity": "medium",
                "intent": thought.intent,
                "confidence": thought.confidence,
            }
        else:
            short_text = calibrated_clarification_text(thought, detected_language)
            refusal_block = None

        # Reflect on the early exit so the trace is complete.
        early_reflection = reflect_heuristic(thought, [], short_text)
        thought.observation = early_reflection.observation

        # Mark every open goal blocked/clarifying so the next turn knows
        # where we left off.
        early_outcome = "failed" if chosen_decision == "refuse" else "deferred"
        update_status_from_reflection(goals, early_outcome, needs_retry=False)
        early_hint = replan_suggestion(
            thought.next_action,
            early_outcome,
            needs_retry=False,
            intent=thought.intent,
        )

        logger.info(
            "agent_v2 short-circuit user=%s decision=%s intent=%s conf=%.2f ms=%d",
            user_id, chosen_decision, thought.intent, thought.confidence, elapsed_ms,
        )
        result = {
            "text": OutputSanitizer.scrub(short_text),
            "user_id": user_id,
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "lang": detected_language,
            "tool_results": [],
            "suggestions": [],
            "affect": affect.to_dict(),
            "register": register.to_dict(),
            "self_model": {
                "user_role": self_model.user_role,
                "is_admin": self_model.is_admin,
                "active_capabilities": list(self_model.active_capabilities),
                "open_goal_count": self_model.open_goal_count,
            },
            "reasoning_trace": [thought.to_dict()],
            "confidence": thought.confidence,
            "reflection": early_reflection.to_dict(),
            "goals": [g.to_dict() for g in goals],
            "next_step_hint": early_hint,
            "memories": [m.to_dict() for m in memories],
            "world_model": world.to_dict(),
            "pushback_detected": pushback_detected,
            "user_style": user_style.to_dict(),
            "few_shot_examples": [t.to_dict() for t in similar_trajectories],
            "procedural_hint": procedural_hint_text,
            "procedural_rule": procedural_rule.to_dict() if procedural_rule else None,
            "antipattern_hint": antipattern_hint_text,
            "antipattern_rule": antipattern_rule.to_dict() if antipattern_rule else None,
            "agent_v2": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "_elapsed_ms": elapsed_ms,
        }
        if refusal_block is not None:
            result["refusal"] = refusal_block
        return result

    # ----------- 3b-bis. Destructive-intent interception (Phase 4 full) ---
    # If the intent is unambiguously destructive AND we can pin an exact
    # target from the world snapshot, queue a `pending_action` row via
    # the action framework and return an envelope the frontend renders
    # as a Confirm/Cancel card. The user's tap resolves via /api/ai/confirm.
    # Skipped for anonymous users (nil-UUID) and admin users are handled
    # the same way as regular users.
    intercepted_action = None
    if (
        user_id
        and not user_id.startswith("00000000")
        and chosen_decision == "execute"
    ):
        try:
            intercepted_action = build_intercepted_action(
                intent=thought.intent or "",
                confidence=thought.confidence,
                world_snapshot=world,
                language=detected_language,
            )
        except Exception as exc:  # noqa: BLE001
            logger.info("intercept builder failed: %s", exc)
            intercepted_action = None

    if intercepted_action is not None:
        try:
            from backend.agent.actions import ActionRequest, plan_action
            req = ActionRequest(
                tool=intercepted_action.tool,
                args=dict(intercepted_action.args),
                user_id=user_id,
                turn_id=turn_id,
                conversation_id=conversation_id,
                requires_confirmation=True,
                summary=(
                    intercepted_action.summary_es
                    if detected_language.startswith("es")
                    else intercepted_action.summary_en
                ),
            )
            plan_result = await asyncio.wait_for(plan_action(req), timeout=4.0)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "intercept plan_action failed (%s) — falling back to v1", exc,
            )
            plan_result = None

        if (
            plan_result is not None
            and getattr(plan_result, "status", None) == "pending"
            and getattr(plan_result, "pending_id", None)
        ):
            intercept_text = format_intercept_text(
                intercepted_action, language=detected_language,
            )
            pending_envelope = build_pending_action_envelope(
                pending_id=str(plan_result.pending_id),
                tool=intercepted_action.tool,
                args=intercepted_action.args,
                summary=(
                    intercepted_action.summary_es
                    if detected_language.startswith("es")
                    else intercepted_action.summary_en
                ),
                expires_at=getattr(plan_result, "expires_at", None),
            )
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.info(
                "agent_v2 intercepted destructive intent user=%s intent=%s tool=%s pending_id=%s",
                user_id, thought.intent, intercepted_action.tool,
                plan_result.pending_id,
            )
            intercept_payload = {
                "text": OutputSanitizer.scrub(intercept_text),
                "user_id": user_id,
                "conversation_id": conversation_id,
                "turn_id": turn_id,
                "lang": detected_language,
                "tool_results": [],
                "suggestions": [],
                "affect": affect.to_dict(),
                "register": register.to_dict(),
                "self_model": {
                    "user_role": self_model.user_role,
                    "is_admin": self_model.is_admin,
                    "active_capabilities": list(self_model.active_capabilities),
                    "open_goal_count": self_model.open_goal_count,
                },
                "reasoning_trace": [thought.to_dict()],
                "confidence": thought.confidence,
                "goals": [g.to_dict() for g in goals],
                "memories": [m.to_dict() for m in memories],
                "world_model": world.to_dict(),
                "pushback_detected": pushback_detected,
                "pending_action": pending_envelope,
                "confirmation_recommended": True,
                "agent_v2": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "_elapsed_ms": elapsed_ms,
            }
            # Best-effort telemetry (skips anonymous / errors silently).
            try:
                asyncio.create_task(log_v2_turn(intercept_payload))
            except RuntimeError:
                pass
            return intercept_payload

    # ----------- 3c. Brainstorm short-circuit (Phase 5 full) --------------
    # "Give me ideas for X" / "brainstorm Y" / "lluvia de ideas..." turns
    # are pure ideation — they must NOT trigger tool calls or writes. We
    # generate ideas directly and skip the v1 graph entirely. Safety,
    # self-eval, refine, and trajectory recording still run on the
    # produced text just like any other path.
    brainstorm_used = False
    brainstorm_ideas: list[str] = []
    if detect_brainstorm_intent(message) and chosen_decision == "execute":
        bs_topic = _bs_extract_topic(message)
        bs_count = _bs_extract_count(message)
        try:
            brainstorm_ideas = await asyncio.wait_for(
                brainstorm_llm(bs_topic, n=bs_count, language=detected_language),
                timeout=8.0,
            )
        except asyncio.TimeoutError:
            logger.info("brainstorm LLM timed out — using heuristic")
            brainstorm_ideas = brainstorm_heuristic(
                bs_topic, n=bs_count, language=detected_language,
            )
        except Exception as exc:  # noqa: BLE001
            logger.info("brainstorm error (%s) — using heuristic", exc)
            brainstorm_ideas = brainstorm_heuristic(
                bs_topic, n=bs_count, language=detected_language,
            )
        brainstorm_text = format_ideas_as_response(
            brainstorm_ideas, bs_topic, language=detected_language,
        )
        v1_result = {
            "text": brainstorm_text,
            "conversation_id": conversation_id,
            "lang": detected_language,
            "tool_results": [],
            "suggestions": [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        brainstorm_used = True
    else:
        # ----------- 4. Invoke the existing v1 graph -----------
        # Compose the v2 context block (world + memory + few-shot examples)
        # and hand it to v1 via user_context. v1's `generate_response` will
        # splice it into the system prompt so retrieved context actually
        # steers gpt-4o instead of being observability-only.
        try:
            v2_context_block = format_v2_context_block(
                world=world,
                memories=memories,
                few_shot_block=format_few_shot_examples(similar_trajectories),
                procedural_hint=procedural_hint_text,
                antipattern_hint=antipattern_hint_text,
            )
        except Exception as exc:  # noqa: BLE001
            logger.info("v2 context block compose failed: %s", exc)
            v2_context_block = ""
        v1_user_context = dict(user_context)
        if v2_context_block:
            v1_user_context["v2_context_block"] = v2_context_block
        try:
            v1_result = await _invoke_v1(
                user_id=user_id,
                message=message,
                conversation_id=conversation_id,
                user_context=v1_user_context,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("v1 graph invocation failed: %s", exc, exc_info=True)
            return {
                "text": ERROR_RESPONSES["en"]["unknown"],
                "user_id": user_id,
                "conversation_id": conversation_id,
                "turn_id": turn_id,
                "lang": detected_language,
                "tool_results": [],
                "suggestions": [],
                "error": str(exc),
                "agent_v2": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    # ----------- 5. Post-process: food safety + persona + sanitizer -------
    raw_tool_results = v1_result.get("tool_results") or []
    filtered_tool_results, blocked_listings = _filter_safety_in_tool_results(raw_tool_results)
    if blocked_listings:
        logger.info(
            "FoodSafetyGate filtered %d listing(s) for user=%s", len(blocked_listings), user_id
        )

    # ----------- 5a. Audit every WRITE the v1 graph performed -------------
    # Skipped for anonymous turns — RLS on agent_audit_log requires a real
    # actor_user_id, and unauthenticated traffic can't trigger writes anyway.
    tool_audit: list[dict[str, Any]] = []
    if user_id and not user_id.startswith("00000000"):
        try:
            tool_audit = await _audit_write_tools(
                filtered_tool_results,
                user_id=user_id,
                turn_id=turn_id,
                conversation_id=conversation_id,
            )
        except Exception as audit_exc:  # noqa: BLE001
            logger.warning("audit pass failed (non-fatal): %s", audit_exc)

    # ----------- 5a-bis. Confirmation-policy verdicts (Phase 4 mid) -------
    # Pure / observability-only on this slice: we EVALUATE every executed
    # tool call against the centralized policy and surface the verdicts so
    # the frontend can show an undo banner for destructive writes. Active
    # pre-execution gating arrives in Phase 4 full — this is the
    # foundation.
    try:
        confirmation_decisions_obj = evaluate_tool_results(
            intent=thought.intent or "",
            confidence=thought.confidence,
            tool_results=filtered_tool_results,
        )
        intent_decision_obj = decide_for_intent(
            thought.intent or "", thought.confidence,
        )
    except Exception as cp_exc:  # noqa: BLE001
        logger.info("confirmation policy failed (%s) — proceeding without", cp_exc)
        confirmation_decisions_obj = []
        intent_decision_obj = None
    confirmation_decisions: list[dict[str, Any]] = [
        d.to_dict() for d in confirmation_decisions_obj
    ]
    intent_confirmation_decision: dict[str, Any] | None = (
        intent_decision_obj.to_dict() if intent_decision_obj is not None else None
    )
    confirmation_recommended: bool = any_confirmation_required(
        confirmation_decisions_obj
    ) or (intent_decision_obj is not None and intent_decision_obj.required)
    confirmation_summary: str = format_decision_summary(
        confirmation_decisions_obj, language=detected_language,
    )

    response_text = v1_result.get("text") or ""

    # Persona check — if violated, append a corrective system-style note for
    # the next turn rather than retrying now (Slice A keeps this lightweight;
    # full self_eval-with-retry arrives in Slice C).
    persona = PersonaGuard.check(response_text)
    if not persona.ok:
        logger.info("PersonaGuard flagged response: %s", persona.issues)

    # Output sanitizer — strip credentials, JWTs, bare UUIDs, traceback chatter.
    safe_text = OutputSanitizer.scrub(response_text)
    safe_text_changed = safe_text != response_text

    # ----------- 6. Reflect on the outcome (Phase 1) ---------------------
    # Lightweight LLM-or-heuristic outcome grade. The reflection is surfaced
    # in the response so the frontend (in debug/dev mode) and downstream
    # learning jobs can see whether the turn met the user's goal.
    try:
        reflection: Reflection = await asyncio.wait_for(
            reflect_llm(message, thought, filtered_tool_results, safe_text),
            timeout=4.0,
        )
    except asyncio.TimeoutError:
        logger.info("reflect LLM timed out — using heuristic")
        reflection = reflect_heuristic(thought, filtered_tool_results, safe_text)
    except Exception as exc:  # noqa: BLE001
        logger.info("reflect error (%s) — using heuristic", exc)
        reflection = reflect_heuristic(thought, filtered_tool_results, safe_text)

    # Stamp the reflection's observation back onto the thought so the trace
    # is self-contained.
    thought.observation = reflection.observation
    # Record which tool the v1 graph actually ran (first one).
    if filtered_tool_results:
        first = filtered_tool_results[0] if isinstance(filtered_tool_results[0], dict) else None
        if first:
            thought.tool_name = first.get("tool") or first.get("name")

    # ----------- 6a. Update goal statuses + emit replan hint (Phase 2) ----
    update_status_from_reflection(
        goals,
        reflection.outcome,
        needs_retry=reflection.needs_retry,
    )
    next_step_hint = replan_suggestion(
        thought.next_action,
        reflection.outcome,
        needs_retry=reflection.needs_retry,
        intent=thought.intent,
    )
    # Refresh open_goal_count so the snapshot is honest.
    self_model.open_goal_count = sum(
        1 for g in goals if g.status in ("open", "in_progress")
    )

    # ----------- 6b. Persist salient facts to long-term memory (Phase 3) --
    # Only on successful turns and only for authenticated users — we never
    # write memory for nil-UUID sessions or refused/clarifying turns. The
    # write itself is best-effort: any Supabase failure just logs.
    new_memories: list[MemoryItem] = []
    privacy_disclosure: Optional[str] = None
    if (
        user_id
        and not user_id.startswith("00000000")
        and reflection.outcome in ("success", "partial")
    ):
        try:
            candidates = await asyncio.wait_for(
                extract_salient_facts_llm(
                    message, user_id=user_id, source_turn_id=turn_id,
                ),
                timeout=4.0,
            )
        except asyncio.TimeoutError:
            logger.info("extract_salient_facts LLM timed out — using heuristic")
            candidates = extract_salient_facts(
                message, user_id=user_id, source_turn_id=turn_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.info("extract_salient_facts error (%s) — using heuristic", exc)
            candidates = extract_salient_facts(
                message, user_id=user_id, source_turn_id=turn_id,
            )

        if candidates:
            try:
                new_memories = await asyncio.wait_for(
                    write_memories(user_id, candidates, source_turn_id=turn_id),
                    timeout=4.0,
                )
            except Exception as exc:  # noqa: BLE001
                logger.info("write_memories failed (%s)", exc)
                new_memories = []

            # If the user had zero memories before AND we just wrote some,
            # surface a one-time privacy disclosure. The frontend can
            # choose whether to render it.
            if new_memories and not memories:
                privacy_disclosure = privacy_disclosure_text(detected_language)

    # ----------- 6c. Self-evaluation + uncertainty hedge (Phase 7 lite) ---
    # Rate the response on correctness/helpfulness/safety/calibration so
    # we (a) surface the score for observability and (b) decide whether to
    # prepend an uncertainty hedge. Full retry-with-critique lands in
    # Phase 7 full.
    succeeded_tools = sum(
        1 for tr in (filtered_tool_results or [])
        if isinstance(tr, dict)
        and isinstance(tr.get("result"), dict)
        and not tr["result"].get("error")
        and tr["result"].get("success") is not False
    )
    try:
        self_eval: SelfEvaluation = await asyncio.wait_for(
            evaluate_response_llm(
                message, safe_text,
                tool_results=filtered_tool_results,
                confidence=thought.confidence,
                persona_ok=persona.ok,
                safe_text_changed=safe_text_changed,
            ),
            timeout=4.0,
        )
    except asyncio.TimeoutError:
        logger.info("self_eval LLM timed out — using heuristic")
        self_eval = evaluate_response_heuristic(
            message, safe_text,
            tool_results=filtered_tool_results,
            confidence=thought.confidence,
            persona_ok=persona.ok,
            safe_text_changed=safe_text_changed,
        )
    except Exception as exc:  # noqa: BLE001
        logger.info("self_eval error (%s) — using heuristic", exc)
        self_eval = evaluate_response_heuristic(
            message, safe_text,
            tool_results=filtered_tool_results,
            confidence=thought.confidence,
            persona_ok=persona.ok,
            safe_text_changed=safe_text_changed,
        )

    # ----------- 6d. Single-shot self-refine retry (Phase 7 full) --------
    # When the self-eval recommends a retry we regenerate the response
    # ONCE with the critique fed back, then re-scrub and re-grade. We
    # never re-run the v1 graph or any tools — refine is a text-rewrite
    # head only, so side-effecting actions never repeat.
    retried = False
    original_response_text: str | None = None
    original_self_eval: SelfEvaluation | None = None
    if should_retry(self_eval) and safe_text.strip():
        original_response_text = safe_text
        original_self_eval = self_eval
        logger.info(
            "self_eval recommends retry (overall=%.2f) — running self-refine",
            self_eval.overall,
        )
        try:
            refined_text = await asyncio.wait_for(
                refine_response_llm(
                    message, safe_text, self_eval.critique,
                    language=detected_language,
                ),
                timeout=6.0,
            )
        except asyncio.TimeoutError:
            logger.info("refine LLM timed out — using heuristic refiner")
            refined_text = refine_response_heuristic(
                message, safe_text, self_eval.critique,
                language=detected_language,
            )
        except Exception as exc:  # noqa: BLE001
            logger.info("refine error (%s) — using heuristic refiner", exc)
            refined_text = refine_response_heuristic(
                message, safe_text, self_eval.critique,
                language=detected_language,
            )

        # Re-scrub the refined text — the refine head can leak just like
        # generation, and PersonaGuard runs on the new draft.
        refined_scrubbed = OutputSanitizer.scrub(refined_text or "")
        refined_safe_changed = refined_scrubbed != refined_text
        refined_persona = PersonaGuard.check(refined_scrubbed)

        # Re-grade so we can compare and pick the better response. Skip the
        # LLM on the second eval — we already spent one round; heuristic
        # is fast and deterministic.
        refined_eval = evaluate_response_heuristic(
            message, refined_scrubbed,
            tool_results=filtered_tool_results,
            confidence=thought.confidence,
            persona_ok=refined_persona.ok,
            safe_text_changed=refined_safe_changed,
        )

        # Keep the refined version when it actually improved the score
        # AND didn't regress safety. Otherwise keep the original.
        if (
            refined_scrubbed
            and refined_eval.overall >= self_eval.overall
            and refined_eval.safety >= self_eval.safety
        ):
            safe_text = refined_scrubbed
            self_eval = refined_eval
            persona = refined_persona
            safe_text_changed = refined_safe_changed
            retried = True
            logger.info(
                "self-refine accepted (overall %.2f -> %.2f)",
                original_self_eval.overall, refined_eval.overall,
            )
        else:
            logger.info(
                "self-refine rejected (overall %.2f -> %.2f) — keeping original",
                original_self_eval.overall, refined_eval.overall,
            )
            # Roll back the bookkeeping if we kept the original.
            original_response_text = None
            original_self_eval = None

    # ----------- 6d-bis. Curiosity follow-up (Phase 5 full) ---------------
    # When the reasoning head locked onto an actionable intent but didn't
    # have enough info, append ONE open question so the user can unblock
    # us. Suppressed on brainstorm turns — those already end in a tail
    # prompt. Suppressed when the world snapshot already supplies the
    # signal (dietary, allergies, address all known).
    curiosity_followup: str | None = None
    if not brainstorm_used:
        world_has_signal = bool(
            (world.dietary_restrictions or world.allergies or world.address)
        )
        if should_ask_followup(
            intent=thought.intent or "",
            confidence=thought.confidence,
            message=message,
            world_has_signal=world_has_signal,
        ):
            try:
                curiosity_followup = await asyncio.wait_for(
                    generate_followup_llm(
                        thought.intent or "", message, language=detected_language,
                    ),
                    timeout=4.0,
                )
            except asyncio.TimeoutError:
                logger.info("curiosity LLM timed out — using heuristic")
                curiosity_followup = generate_followup_heuristic(
                    thought.intent or "", message, language=detected_language,
                )
            except Exception as exc:  # noqa: BLE001
                logger.info("curiosity error (%s) — using heuristic", exc)
                curiosity_followup = generate_followup_heuristic(
                    thought.intent or "", message, language=detected_language,
                )
            if curiosity_followup and curiosity_followup.strip():
                # Append to safe_text so the user sees one coherent reply.
                safe_text = f"{safe_text.rstrip()}\n\n{curiosity_followup.strip()}"

    # Apply the uncertainty hedge only when reasoning confidence is low,
    # the tool layer didn't succeed, and the response still sounds
    # definitive. The helper is a no-op in every other case.
    safe_text = surface_uncertainty(
        safe_text,
        confidence=thought.confidence,
        tool_succeeded=bool(succeeded_tools),
        language=detected_language,
    )

    # ----------- 6e. Compute reward + record trajectory (Phase 6) ----------
    # Deterministic reward blends reflection outcome with the self-eval
    # score and a few small penalties (pushback, retried, persona fail,
    # safety scrub). The trajectory write is best-effort.
    failed_tools = sum(
        1 for tr in (filtered_tool_results or [])
        if isinstance(tr, dict) and (
            "error" in tr
            or (
                isinstance(tr.get("result"), dict)
                and (tr["result"].get("error") or tr["result"].get("success") is False)
            )
        )
    )
    reward = compute_reward(
        reflection_outcome=reflection.outcome,
        self_eval_overall=self_eval.overall,
        pushback_detected=pushback_detected,
        retried=retried,
        succeeded_tools=succeeded_tools,
        failed_tools=failed_tools,
        persona_ok=persona.ok,
        safe_text_changed=safe_text_changed,
    )
    action_label = (
        thought.tool_name
        or thought.intent
        or (chosen_decision if isinstance(chosen_decision, str) else "responded")
    )
    try:
        await asyncio.wait_for(
            record_trajectory(
                user_id,
                turn_id=turn_id,
                intent=thought.intent or "",
                message=message,
                action=action_label or "responded",
                outcome=reflection.outcome,
                reward=reward,
                confidence=thought.confidence,
                language=detected_language,
                retried=retried,
                pushback_detected=pushback_detected,
            ),
            timeout=3.0,
        )
    except asyncio.TimeoutError:
        logger.info("record_trajectory timed out — proceeding")
    except Exception as exc:  # noqa: BLE001
        logger.info("record_trajectory error (%s) — proceeding", exc)

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "agent_v2 turn complete user=%s ms=%d affect=%s tone=%s safe=%s persona_ok=%s "
        "intent=%s conf=%.2f outcome=%s",
        user_id, elapsed_ms, affect.dominant, register.tone,
        OutputSanitizer.is_safe(response_text), persona.ok,
        thought.intent, thought.confidence, reflection.outcome,
    )

    response_payload = {
        "text": safe_text,
        "user_id": user_id,
        "conversation_id": v1_result.get("conversation_id") or conversation_id,
        "turn_id": turn_id,
        "lang": v1_result.get("lang") or detected_language,
        "tool_results": filtered_tool_results,
        "suggestions": v1_result.get("suggestions") or [],
        "affect": affect.to_dict(),
        "register": register.to_dict(),
        "self_model": {
            "user_role": self_model.user_role,
            "is_admin": self_model.is_admin,
            "active_capabilities": list(self_model.active_capabilities),
            "open_goal_count": self_model.open_goal_count,
        },
        "blocked_listings": blocked_listings,
        "persona_check": {"ok": persona.ok, "issues": persona.issues},
        "tool_audit": tool_audit,
        "confirmation_recommended": confirmation_recommended,
        "confirmation_decisions": confirmation_decisions,
        "intent_confirmation_decision": intent_confirmation_decision,
        "confirmation_summary": confirmation_summary,
        "reasoning_trace": [thought.to_dict()],
        "confidence": thought.confidence,
        "reflection": reflection.to_dict(),
        "goals": [g.to_dict() for g in goals],
        "next_step_hint": next_step_hint,
        "memories": [m.to_dict() for m in memories],
        "world_model": world.to_dict(),
        "new_memories": [m.to_dict() for m in new_memories],
        "privacy_disclosure": privacy_disclosure,
        "self_eval": self_eval.to_dict(),
        "pushback_detected": pushback_detected,
        "retried": retried,
        "original_response": original_response_text,
        "original_self_eval": original_self_eval.to_dict() if original_self_eval else None,
        "user_style": user_style.to_dict(),
        "few_shot_examples": [t.to_dict() for t in similar_trajectories],
        "few_shot_block": format_few_shot_examples(similar_trajectories),
        "procedural_hint": procedural_hint_text,
        "procedural_rule": procedural_rule.to_dict() if procedural_rule else None,
        "antipattern_hint": antipattern_hint_text,
        "antipattern_rule": antipattern_rule.to_dict() if antipattern_rule else None,
        "reward": reward,
        "brainstorm_used": brainstorm_used,
        "brainstorm_ideas": list(brainstorm_ideas) if brainstorm_ideas else [],
        "curiosity_followup": curiosity_followup,
        "agent_v2": True,
        "timestamp": v1_result.get("timestamp") or datetime.now(timezone.utc).isoformat(),
        "_elapsed_ms": elapsed_ms,
    }

    # Phase 8: fire-and-forget telemetry write. Skips anonymous turns and
    # swallows any error internally, so a telemetry outage never affects
    # the response the user gets.
    try:
        asyncio.create_task(log_v2_turn(response_payload))
    except RuntimeError:
        # Rare: no running loop (e.g. called from sync context in tests).
        # Skip silently — telemetry is best-effort.
        pass

    return response_payload


__all__ = [
    "is_agent_v2_enabled",
    "invoke_agent_v2",
]
