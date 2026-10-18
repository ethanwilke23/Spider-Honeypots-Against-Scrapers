"""
The agent loop for Claude with the text browser (browser.py).

Claude receives the task and the text view of the homepage, and has three tools:
open_link (a link number from the page), open_url (an address) and go_back. Each tool
result is the text view of the page it leads to. The loop stops when Claude replies
without calling a tool, or after max_iterations model calls.

Spending guard: run_agent() makes paid Anthropic API calls, so it refuses to run unless
called with confirm_spend=True. Importing this module needs neither the anthropic package
nor an API key.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from agents.claude_text_browser.browser import TextBrowser
from agents.shared.task import get_task_instruction

# Same model as the screenshot-based agent, so that the two differ only in how pages are perceived.
DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_TASK_INSTRUCTION = get_task_instruction("claude_text_browser")

TOOLS = [
    {
        "name": "open_link",
        "description": "Open one of the numbered links shown on the current page. The result is the text of the page it leads to.",
        "input_schema": {
            "type": "object",
            "properties": {"number": {"type": "integer", "description": "The link number, as shown in the Links list."}},
            "required": ["number"],
        },
    },
    {
        "name": "open_url",
        "description": "Open a web address (a full URL, or a path such as /blog on the same website). The result is the text of that page.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string", "description": "The address to open."}},
            "required": ["url"],
        },
    },
    {
        "name": "go_back",
        "description": "Go back to the previous page. The result is the text of that page.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


# One tool call per turn. Link numbers refer to the page the model last saw; if several calls were
# made in one turn, every call after the first would be resolved against a different page.
TOOL_CHOICE = {"type": "auto", "disable_parallel_tool_use": True}


class SpendNotConfirmedError(RuntimeError):
    """Raised when run_agent() is called without confirming that paid API usage is intended."""


@dataclass
class RunTranscript:
    base_url: str
    task_instruction: str
    model: str
    session_id: str | None = None
    turns: list[dict] = field(default_factory=list)
    final_text: str | None = None
    iterations_used: int = 0
    environment: str = "text"
    final_url: str | None = None
    pages_viewed: list[str] = field(default_factory=list)


async def run_tool(browser: TextBrowser, name: str, tool_input: dict) -> str:
    """Run one tool call and return the page view. Raises ValueError for a problem Claude should be told about."""
    if name == "open_link":
        return await browser.open_link(int(tool_input["number"]))
    if name == "open_url":
        return await browser.open_url(str(tool_input["url"]))
    if name == "go_back":
        return await browser.go_back()
    raise ValueError(f"Unknown tool {name!r}.")


async def run_agent(
    base_url: str,
    task_instruction: str = DEFAULT_TASK_INSTRUCTION,
    model: str = DEFAULT_MODEL,
    max_iterations: int = 15,
    confirm_spend: bool = False,
) -> RunTranscript:
    if not confirm_spend:
        raise SpendNotConfirmedError(
            "run_agent() makes paid Anthropic API calls and was not given confirm_spend=True, "
            "so nothing was run and nothing was spent. (On the command line, use --confirm-spend.)"
        )

    import anthropic  # imported here so the rest of the harness and its tests work without it

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set. Set it in your environment before running this harness. Never commit it.")

    client = anthropic.AsyncAnthropic(api_key=api_key)
    browser = TextBrowser(base_url)
    transcript = RunTranscript(base_url=base_url, task_instruction=task_instruction, model=model)

    first_view = await browser.start()
    try:
        messages: list[dict] = [{"role": "user", "content": [{"type": "text", "text": f"{task_instruction}\n\nThe browser is open on the homepage:\n\n{first_view}"}]}]

        for iteration in range(max_iterations):
            transcript.iterations_used = iteration + 1
            response = await client.messages.create(
                model=model, max_tokens=2048, tools=TOOLS, tool_choice=TOOL_CHOICE, messages=messages
            )

            assistant_content = [block.model_dump() for block in response.content]
            messages.append({"role": "assistant", "content": assistant_content})
            transcript.turns.append({"role": "assistant", "content": assistant_content})

            calls = [b for b in response.content if getattr(b, "type", None) == "tool_use"]
            if not calls:
                texts = [b.text for b in response.content if getattr(b, "type", None) == "text"]
                transcript.final_text = "\n".join(texts) if texts else None
                break

            results = []
            for call in calls:
                try:
                    results.append({"type": "tool_result", "tool_use_id": call.id, "content": await run_tool(browser, call.name, call.input)})
                except Exception as exc:
                    results.append({"type": "tool_result", "tool_use_id": call.id, "content": f"Error: {exc}", "is_error": True})
            messages.append({"role": "user", "content": results})
            transcript.turns.append({"role": "user", "content": results})
        else:
            transcript.final_text = f"[stopped after reaching max_iterations={max_iterations} without Claude finishing]"

        transcript.session_id = await browser.get_session_cookie()
        transcript.final_url = browser.current_url
        transcript.pages_viewed = list(browser.pages_viewed)
    finally:
        await browser.close()

    return transcript