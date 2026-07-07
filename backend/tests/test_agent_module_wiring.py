"""Verify every agent module is reachable from the runtime graph."""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

import backend.agent as agent_pkg

# Modules that are intentionally offline / script-only (not per-turn runtime).
_SCRIPT_ONLY = frozenset({
    "procedural_store",  # upsert via nightly job; fetch wired in v2_graph
})

# Entry points that constitute "wired" for runtime modules.
_RUNTIME_IMPORTERS = (
    "backend.agent.graph",
    "backend.agent.v2_graph",
    "backend.agent.planner",
    "backend.agent.actions",
    "backend.agent.tool_actions",
    "backend.app",
    "backend.ai_engine",
    "backend.agent.proactive",
    "backend.agent.learning",
    "backend.agent.memory",
    "backend.agent.__init__",
)


def _agent_module_names() -> set[str]:
    root = Path(agent_pkg.__file__).parent
    names: set[str] = set()
    for mod in pkgutil.iter_modules([str(root)]):
        if mod.name.startswith("_"):
            continue
        if mod.name in ("tools",):
            continue
        names.add(mod.name)
    return names


def _module_referenced_by_runtime(module_name: str) -> bool:
    needle = f"backend.agent.{module_name}"
    for importer in _RUNTIME_IMPORTERS:
        try:
            src = importlib.import_module(importer)
            path = getattr(src, "__file__", "") or ""
            if not path:
                continue
            text = Path(path).read_text(encoding="utf-8")
            if needle in text or f"from backend.agent import {module_name}" in text:
                return True
            if f"import backend.agent.{module_name}" in text:
                return True
        except Exception:
            continue
    return False


def test_all_runtime_agent_modules_importable():
    for name in sorted(_agent_module_names()):
        mod = importlib.import_module(f"backend.agent.{name}")
        assert mod is not None


def test_runtime_modules_are_referenced():
    """Each agent module (except script-only) must appear in a runtime importer."""
    missing = []
    for name in sorted(_agent_module_names()):
        if name in _SCRIPT_ONLY:
            continue
        if not _module_referenced_by_runtime(name):
            missing.append(name)
    assert not missing, f"Unwired agent modules: {missing}"


def test_v2_graph_imports_core_phases():
    v2 = importlib.import_module("backend.agent.v2_graph")
    for attr in (
        "invoke_agent_v2",
        "record_trajectory",
        "evaluate_tool_results",
        "build_intercepted_action",
    ):
        assert hasattr(v2, attr) or attr in dir(v2), f"missing {attr} on v2_graph"
