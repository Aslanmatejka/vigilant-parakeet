"""Tests for v2 context / consciousness blocks."""

from backend.agent.context_block import format_reasoning_block
from backend.agent.goals import Goal
from backend.agent.reasoning import Thought


def test_reasoning_block_includes_thought_and_goals():
    thought = Thought(
        thought="User wants to donate prepared meals for pickup tomorrow.",
        intent="donate",
        confidence=0.9,
    )
    goals = [
        Goal(
            id="g1",
            user_id="u1",
            description="Post prepared meal listing",
            intent="donate",
            status="open",
        ),
    ]
    block = format_reasoning_block(
        thought=thought,
        goals=goals,
        affect_dominant="neutral",
    )
    assert "<consciousness>" in block
    assert "prepared meal" in block.lower()
    assert "open goal:" in block


def test_reasoning_block_empty_when_no_data():
    assert format_reasoning_block() == ""
