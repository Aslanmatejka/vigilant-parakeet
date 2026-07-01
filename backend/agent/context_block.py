"""V2 context block — composes <world>, <memory>, <few_shot_examples> into a
single markdown block injected into the v1 system prompt.

This closes the loop on Phases 3 + 6 lite: the retrieved memories, world
snapshot, and similar-past-trajectory examples are now actually visible to
the gpt-4o response generator, instead of being observability-only.

Design rules:
  - Pure / synchronous / no external IO.
  - Returns "" when every section is empty so callers can drop it cleanly.
  - Caps each section so a chatty memory store can't blow the token budget.
  - Sections are wrapped in their own xml-ish tags so the LLM can skim them.
"""
from __future__ import annotations

from typing import Iterable, Sequence

from backend.agent.memory import MemoryItem
from backend.agent.world_model import WorldSnapshot

# Caps tuned for ~600-token combined block on a noisy turn.
MAX_MEMORY_LINES = 6
MAX_MEMORY_LINE_CHARS = 160
MAX_BLOCK_CHARS = 3000


def _truncate(text: str, *, limit: int) -> str:
    """Cut to *limit* chars at the nearest whitespace; no ellipsis prose."""
    if not text:
        return ""
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut or text[:limit]


def format_memory_block(memories: Iterable[MemoryItem] | None) -> str:
    """Render long-term memories as `<memory>...</memory>`.

    Sorted by importance descending; capped to MAX_MEMORY_LINES.
    Returns "" when there are no usable items.
    """
    if not memories:
        return ""
    items = [m for m in memories if isinstance(m, MemoryItem) and m.content]
    if not items:
        return ""
    items.sort(key=lambda m: float(m.importance), reverse=True)

    lines: list[str] = ["<memory>"]
    for m in items[:MAX_MEMORY_LINES]:
        content = _truncate(str(m.content), limit=MAX_MEMORY_LINE_CHARS)
        kind = (m.kind or "other").strip() or "other"
        lines.append(f"- ({kind}) {content}")
    lines.append("</memory>")
    return "\n".join(lines)


def format_v2_context_block(
    *,
    world: WorldSnapshot | None = None,
    memories: Sequence[MemoryItem] | None = None,
    few_shot_block: str | None = None,
    procedural_hint: str | None = None,
    antipattern_hint: str | None = None,
) -> str:
    """Compose <world>, <memory>, <procedural>, <avoid>, <few_shot_examples> into one block.

    Each subsection is omitted when empty. Returns "" when nothing is
    available so the prompt builder can skip the section entirely.

    The output is wrapped in `<v2_context>` so the LLM can route around
    it cleanly when prefix-matching its own format.
    """
    sections: list[str] = []

    if world is not None:
        try:
            world_block = world.render_block()
        except Exception:  # noqa: BLE001
            world_block = ""
        if world_block:
            sections.append(world_block)

    memory_block = format_memory_block(memories)
    if memory_block:
        sections.append(memory_block)

    if procedural_hint and procedural_hint.strip():
        sections.append(
            "<procedural>\n" + procedural_hint.strip() + "\n</procedural>"
        )

    if antipattern_hint and antipattern_hint.strip():
        sections.append(
            "<avoid>\n" + antipattern_hint.strip() + "\n</avoid>"
        )

    if few_shot_block and few_shot_block.strip():
        sections.append(few_shot_block.strip())

    if not sections:
        return ""

    inner = "\n\n".join(sections)
    block = f"<v2_context>\n{inner}\n</v2_context>"

    if len(block) > MAX_BLOCK_CHARS:
        # Hard cap: keep the opening tag + as much content as fits + closing
        # tag. We never emit a malformed block.
        head = "<v2_context>\n"
        tail = "\n</v2_context>"
        budget = MAX_BLOCK_CHARS - len(head) - len(tail)
        truncated = inner[:budget].rsplit("\n", 1)[0]
        block = head + truncated + tail

    return block


__all__ = [
    "MAX_MEMORY_LINES",
    "MAX_MEMORY_LINE_CHARS",
    "MAX_BLOCK_CHARS",
    "format_memory_block",
    "format_v2_context_block",
]
