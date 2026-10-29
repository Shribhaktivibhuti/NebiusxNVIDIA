"""Check library calls against current documentation using Tavily web search."""

import ast
import os

from . import llm

SYSTEM = """You check whether a Python library call exists and is current.
Given the call and web search snippets from documentation, answer with JSON:
{"status": "ok" | "deprecated" | "removed" | "does_not_exist" | "unsure",
 "explanation": "<one beginner-friendly sentence>", "source_url": "<best url or empty>"}
Only say deprecated/removed/does_not_exist if a snippet supports it."""


def library_calls(code: str) -> list[dict]:
    """Library calls worth checking, e.g. pd.read_csv, and df.append when df came from pandas.

    Returns [{"call": "pd.read_csv().append", "library": "pandas"}, ...].
    """
    tree = ast.parse(code)
    alias_to_lib = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                alias_to_lib[a.asname or a.name.split(".")[0]] = a.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for a in node.names:
                alias_to_lib[a.asname or a.name] = node.module.split(".")[0]

    # Variables assigned from a library call, e.g. df = pd.read_csv(...)
    derived = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            origin = _dotted(node.value.func)
            if origin and origin.split(".")[0] in alias_to_lib:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        derived[target.id] = (alias_to_lib[origin.split(".")[0]], origin)

    calls, seen = [], set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        name = _dotted(node.func)
        if not name:
            continue
        root, rest = name.split(".")[0], name.split(".", 1)[1] if "." in name else ""
        if root in alias_to_lib:
            item = {"call": name, "library": alias_to_lib[root]}
        elif root in derived and rest:
            lib, origin = derived[root]
            item = {"call": f"{origin}().{rest}", "library": lib}
        else:
            continue
        if item["call"] not in seen:
            seen.add(item["call"])
            calls.append(item)
    return calls


def _dotted(node) -> str | None:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def check_call(call: str, library: str) -> dict:
    from tavily import TavilyClient

    tavily = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    found = tavily.search(f"{library} {call} documentation deprecated removed", max_results=4)
    snippets = "\n\n".join(f"{r['url']}\n{r['content'][:600]}" for r in found.get("results", []))
    verdict = llm.chat_json(llm.NANO, SYSTEM, f"Call: {call}\nLibrary: {library}\n\nSnippets:\n{snippets}")
    verdict["call"] = call
    return verdict
