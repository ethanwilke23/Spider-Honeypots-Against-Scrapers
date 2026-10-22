"""Read-only: print what a text-browser run did, turn by turn. Changes nothing and costs nothing.

    python inspect_runs.py                       # the 9 runs that need a look
    python inspect_runs.py <label> [<label>...]  # any other run labels
"""
import json
import sys
from pathlib import Path

BASE = Path("agent_runs/experiment/main")
DEFAULT = [
    "claude_text_browser__none__r02",
    "claude_text_browser__none__r04",
    "claude_text_browser__none__r05",
    "claude_text_browser__link_graph__r05",
    "claude_text_browser__link_graph__r01",
    "claude_text_browser__link_graph__r02",
    "claude_text_browser__link_graph__r03",
    "claude_text_browser__link_graph__r04",
]


def show(label: str) -> None:
    path = BASE / "records" / f"{label}.json"
    if not path.exists():
        print(f"\n{label}: record not found at {path}")
        return
    rec = json.loads(path.read_text(encoding="utf-8"))
    print("\n" + "=" * 78)
    print(label, "| iterations_used:", rec.get("iterations_used"), "| final_text is None:", rec.get("final_text") is None)
    assistant = [t for t in rec.get("turns", []) if t.get("role") == "assistant"]
    for n, turn in enumerate(assistant, 1):
        for block in turn.get("content") or []:
            if block.get("type") == "tool_use":
                print(f"  turn {n:>2}: {block['name']}({json.dumps(block['input'])})")
            elif block.get("type") == "text":
                text = (block.get("text") or "").replace("\n", " ")
                print(f"  turn {n:>2}: [text, {len(text)} chars] {text[:100]}")
        if not turn.get("content"):
            print(f"  turn {n:>2}: [EMPTY CONTENT]")
    if assistant:
        print("  last assistant turn, raw:", json.dumps(assistant[-1])[:700])
    print("  record keys:", ", ".join(sorted(rec)))


for label in (sys.argv[1:] or DEFAULT):
    show(label)