"""Audit script: cross-check TOOL_DEFINITIONS, dispatcher, and handlers."""
import inspect
import re
import backend.tools as T
from backend.tools import TOOL_DEFINITIONS

src = inspect.getsource(T.execute_tool)
keys = set(re.findall(r'"(\w+)":\s*_\w+', src))
defs = {t["function"]["name"] for t in TOOL_DEFINITIONS}

print("In defs not in dispatcher:", sorted(defs - keys))
print("In dispatcher not in defs:", sorted(keys - defs))

for line in src.split("\n"):
    m = re.search(r'"(\w+)":\s*(_\w+)', line)
    if m:
        name, fn = m.groups()
        if not hasattr(T, fn):
            print("MISSING handler:", fn, "for", name)

print("Tool count:", len(defs))
