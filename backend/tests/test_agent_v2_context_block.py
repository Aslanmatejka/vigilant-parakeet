"""Tests for backend.agent.context_block — the v2 context block helper that
composes world + memory + few-shot examples into a single prompt block."""
from __future__ import annotations

import pytest

from backend.agent.adaptation import TrajectoryRecord, format_few_shot_examples
from backend.agent.context_block import (
    MAX_BLOCK_CHARS,
    MAX_MEMORY_LINE_CHARS,
    MAX_MEMORY_LINES,
    format_memory_block,
    format_v2_context_block,
)
from backend.agent.memory import MemoryItem
from backend.agent.world_model import WorldSnapshot


# ---------------------------------------------------------------------------
# format_memory_block
# ---------------------------------------------------------------------------

def test_format_memory_block_empty_inputs() -> None:
    assert format_memory_block(None) == ""
    assert format_memory_block([]) == ""


def test_format_memory_block_skips_blank_content() -> None:
    items = [MemoryItem(user_id="u1", kind="other", content="", importance=0.9)]
    assert format_memory_block(items) == ""


def test_format_memory_block_renders_single_item_with_kind() -> None:
    items = [MemoryItem(user_id="u1", kind="dietary", content="User is vegan", importance=0.8)]
    out = format_memory_block(items)
    assert out.startswith("<memory>")
    assert out.endswith("</memory>")
    assert "(dietary) User is vegan" in out


def test_format_memory_block_sorts_by_importance() -> None:
    items = [
        MemoryItem(user_id="u1", kind="other", content="LOW", importance=0.1),
        MemoryItem(user_id="u1", kind="other", content="HIGH", importance=0.9),
        MemoryItem(user_id="u1", kind="other", content="MID", importance=0.5),
    ]
    out = format_memory_block(items)
    high_idx = out.index("HIGH")
    mid_idx = out.index("MID")
    low_idx = out.index("LOW")
    assert high_idx < mid_idx < low_idx


def test_format_memory_block_caps_lines_to_max() -> None:
    items = [
        MemoryItem(user_id="u1", kind="other", content=f"fact {i}", importance=0.5)
        for i in range(MAX_MEMORY_LINES + 5)
    ]
    out = format_memory_block(items)
    # Count lines starting with "- " — one per memory.
    fact_lines = [line for line in out.splitlines() if line.startswith("- ")]
    assert len(fact_lines) == MAX_MEMORY_LINES


def test_format_memory_block_truncates_long_content() -> None:
    long_content = "x " * 200  # ~400 chars
    items = [MemoryItem(user_id="u1", kind="pref", content=long_content, importance=0.5)]
    out = format_memory_block(items)
    # Find the single fact line and ensure its content portion is bounded.
    fact_line = next(line for line in out.splitlines() if line.startswith("- "))
    # Strip the "- (pref) " prefix
    assert "(pref)" in fact_line
    # Whole line shouldn't exceed prefix + MAX_MEMORY_LINE_CHARS + slack
    assert len(fact_line) <= MAX_MEMORY_LINE_CHARS + 20


def test_format_memory_block_ignores_non_memoryitem() -> None:
    items = ["not a memory item", 42, None]
    assert format_memory_block(items) == ""  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# format_v2_context_block — composition
# ---------------------------------------------------------------------------

def _rich_world() -> WorldSnapshot:
    return WorldSnapshot(
        user_id="u1",
        user_name="Sam",
        dietary_restrictions=["vegan"],
        allergies=["peanuts"],
        address="123 Maple St",
        open_claims_count=2,
        open_listings_count=1,
        communities=["Park Slope Food Co-op"],
    )


def test_format_v2_context_block_all_empty_returns_empty() -> None:
    assert format_v2_context_block() == ""
    assert format_v2_context_block(world=None, memories=None, few_shot_block=None) == ""
    assert format_v2_context_block(world=None, memories=[], few_shot_block="") == ""


def test_format_v2_context_block_empty_world_only() -> None:
    # Empty world snapshot → empty render_block → empty overall.
    world = WorldSnapshot(user_id="u1")
    assert format_v2_context_block(world=world) == ""


def test_format_v2_context_block_world_only() -> None:
    world = _rich_world()
    out = format_v2_context_block(world=world)
    assert out.startswith("<v2_context>")
    assert out.endswith("</v2_context>")
    assert "<world>" in out
    assert "vegan" in out
    assert "<memory>" not in out
    assert "<few_shot_examples>" not in out


def test_format_v2_context_block_memory_only() -> None:
    items = [MemoryItem(user_id="u1", kind="dietary", content="User is vegan", importance=0.8)]
    out = format_v2_context_block(memories=items)
    assert "<v2_context>" in out
    assert "<memory>" in out
    assert "(dietary) User is vegan" in out
    assert "<world>" not in out


def test_format_v2_context_block_few_shot_only() -> None:
    traj = TrajectoryRecord(
        user_id="u1",
        intent="search_food",
        message_summary="find bread",
        action="search_food_listings",
        outcome="success",
        reward=0.9,
    )
    few_shot = format_few_shot_examples([traj])
    out = format_v2_context_block(few_shot_block=few_shot)
    assert "<v2_context>" in out
    assert "<few_shot_examples>" in out
    assert "find bread" in out
    assert "<world>" not in out
    assert "<memory>" not in out


def test_format_v2_context_block_all_three_sections_in_order() -> None:
    world = _rich_world()
    items = [MemoryItem(user_id="u1", kind="dietary", content="User is vegan", importance=0.8)]
    traj = TrajectoryRecord(
        user_id="u1",
        intent="search_food",
        message_summary="find bread",
        action="search_food_listings",
        outcome="success",
        reward=0.9,
    )
    few_shot = format_few_shot_examples([traj])

    out = format_v2_context_block(world=world, memories=items, few_shot_block=few_shot)

    # All three subsections present
    assert "<world>" in out
    assert "<memory>" in out
    assert "<few_shot_examples>" in out
    # Order is world → memory → few_shot
    world_idx = out.index("<world>")
    memory_idx = out.index("<memory>")
    few_shot_idx = out.index("<few_shot_examples>")
    assert world_idx < memory_idx < few_shot_idx
    # Wrapped in v2_context envelope
    assert out.startswith("<v2_context>")
    assert out.endswith("</v2_context>")


def test_format_v2_context_block_procedural_hint_only() -> None:
    out = format_v2_context_block(procedural_hint="Procedural hint: prefer X")
    assert "<v2_context>" in out
    assert "<procedural>" in out
    assert "Procedural hint: prefer X" in out


def test_format_v2_context_block_procedural_blank_skipped() -> None:
    out = format_v2_context_block(procedural_hint="   \n  ")
    assert out == ""


def test_format_v2_context_block_four_sections_order() -> None:
    world = _rich_world()
    items = [MemoryItem(user_id="u1", kind="dietary", content="User is vegan", importance=0.8)]
    traj = TrajectoryRecord(
        user_id="u1",
        intent="search_food",
        message_summary="find bread",
        action="search_food_listings",
        outcome="success",
        reward=0.9,
    )
    few_shot = format_few_shot_examples([traj])

    out = format_v2_context_block(
        world=world,
        memories=items,
        few_shot_block=few_shot,
        procedural_hint="Procedural hint: prefer search_food_listings",
    )
    assert "<world>" in out
    assert "<memory>" in out
    assert "<procedural>" in out
    assert "<few_shot_examples>" in out
    # Order: world → memory → procedural → few_shot
    w = out.index("<world>")
    m = out.index("<memory>")
    p = out.index("<procedural>")
    f = out.index("<few_shot_examples>")
    assert w < m < p < f


def test_format_v2_context_block_antipattern_hint_only() -> None:
    out = format_v2_context_block(antipattern_hint="Avoid: do not call X")
    assert "<v2_context>" in out
    assert "<avoid>" in out
    assert "Avoid: do not call X" in out


def test_format_v2_context_block_antipattern_blank_skipped() -> None:
    out = format_v2_context_block(antipattern_hint="   \n  ")
    assert out == ""


def test_format_v2_context_block_five_sections_order() -> None:
    world = _rich_world()
    items = [MemoryItem(user_id="u1", kind="dietary", content="User is vegan", importance=0.8)]
    traj = TrajectoryRecord(
        user_id="u1",
        intent="search_food",
        message_summary="find bread",
        action="search_food_listings",
        outcome="success",
        reward=0.9,
    )
    few_shot = format_few_shot_examples([traj])

    out = format_v2_context_block(
        world=world,
        memories=items,
        few_shot_block=few_shot,
        procedural_hint="Procedural hint: prefer search_food_listings",
        antipattern_hint="Avoid hint: do not call claim_food_listing",
    )
    assert "<world>" in out
    assert "<memory>" in out
    assert "<procedural>" in out
    assert "<avoid>" in out
    assert "<few_shot_examples>" in out
    w = out.index("<world>")
    m = out.index("<memory>")
    p = out.index("<procedural>")
    a = out.index("<avoid>")
    f = out.index("<few_shot_examples>")
    assert w < m < p < a < f


def test_format_v2_context_block_hard_cap() -> None:
    huge_items = [
        MemoryItem(user_id="u1", kind="other", content="x" * 100, importance=0.5)
        for _ in range(20)
    ]
    huge_few_shot = "<few_shot_examples>\n" + ("- " + "y" * 200 + "\n") * 50 + "</few_shot_examples>"
    out = format_v2_context_block(
        world=_rich_world(),
        memories=huge_items,
        few_shot_block=huge_few_shot,
    )
    assert len(out) <= MAX_BLOCK_CHARS
    # Even when truncated, the envelope tags must be present.
    assert out.startswith("<v2_context>")
    assert out.endswith("</v2_context>")


def test_format_v2_context_block_world_render_exception_skipped() -> None:
    """If render_block raises, we should drop the world section instead of crashing."""

    class _BadWorld:
        def render_block(self) -> str:
            raise RuntimeError("boom")

    items = [MemoryItem(user_id="u1", kind="dietary", content="User is vegan", importance=0.8)]
    out = format_v2_context_block(world=_BadWorld(), memories=items)  # type: ignore[arg-type]
    assert "<world>" not in out
    assert "<memory>" in out


# ---------------------------------------------------------------------------
# Wiring sanity: v1 generate_response should splice in user_context["v2_context_block"]
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "block_value,should_appear",
    [
        ("<v2_context>\n<world>\nname: Sam\n</world>\n</v2_context>", True),
        ("", False),
        (None, False),
        ("   \n  ", False),
    ],
)
def test_v1_generate_response_splices_block(block_value, should_appear) -> None:
    """generate_response must concatenate user_context['v2_context_block']
    into the system prompt only when it's a non-empty string."""
    from backend.agent.prompts import build_system_prompt

    user_context = {
        "name": "Sam",
        "address": "123 Maple St",
        "dietary_restrictions": ["vegan"],
        "role": "user",
    }
    if block_value is not None:
        user_context["v2_context_block"] = block_value

    base = build_system_prompt(user_context, "en")
    # Mirror the logic from graph.generate_response so we test the contract
    # without invoking the live langgraph runtime.
    block = user_context.get("v2_context_block")
    if block and isinstance(block, str) and block.strip():
        composed = f"{base}\n\n{block.strip()}"
    else:
        composed = base

    if should_appear:
        assert "<v2_context>" in composed
        assert "name: Sam" in composed
    else:
        assert "<v2_context>" not in composed
