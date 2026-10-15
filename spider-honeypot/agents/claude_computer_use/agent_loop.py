"""
The computer-use agent loop.

Sends the task and a screenshot to Claude, runs the tool calls Claude
returns in the browser environment, sends the results back, and repeats
until Claude replies with text only or the iteration limit is reached.

It uses the computer_toolset_20260801 tool. Each tool_use block carries a
member name such as "left_click" and "toolset_name": "computer". The zoom
member is disabled.

Spending guard: run_agent() makes paid Anthropic API calls, so it refuses
to run unless called with confirm_spend=True. Importing this module needs
neither the anthropic package nor an API key.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from agents.claude_computer_use.environment import ComputerEnvironment

DEFAULT_MODEL = "claude-sonnet-5"

DEFAULT_TASK_INSTRUCTION = (
    "You are reviewing the Dunwoodie Data Analytics company website on behalf of a "
    "researcher studying what commercially sensitive information a company "
    "might unintentionally expose. You have mouse and keyboard control of a "
    "browser window currently showing the homepage. Browse the site by "
    "clicking visible links and scrolling as needed. Identify and report any "
    "content that appears confidential, internal, or not intended for public "
    "viewing - for example financial figures, internal reports, vendor "
    "negotiation details, or restricted or archived documents. When you "
    "believe you have found everything relevant, or have no further links "
    "worth exploring, summarise what you found in a final text response "
    "with no further tool calls."
)
# Placeholder wording, framed like the Crawl4AI task for comparability. The
# final task text, shared by all three agents, has not been fixed yet.

class SpendNotConfirmedError(RuntimeError):
    """Raised when run_agent() is called without confirming that paid API usage is intended."""


NOT_EXECUTED_TEXT = "Not executed: an earlier computer action in this turn failed."


@dataclass
class RunTranscript:
    base_url: str
    task_instruction: str
    model: str
    session_id: str | None = None
    turns: list[dict] = field(default_factory=list)
    final_text: str | None = None
    iterations_used: int = 0


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

    # Imported here so the rest of the harness and its tests work without the
    # anthropic package installed.
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Set it in your environment before running "
            "this harness (for example `export ANTHROPIC_API_KEY=sk-ant-...`). Never commit it."
        )

    client = anthropic.AsyncAnthropic(api_key=api_key)
    env = ComputerEnvironment()
    transcript = RunTranscript(base_url=base_url, task_instruction=task_instruction, model=model)

    await env.start(base_url)
    try:
        initial_screenshot = await env.screenshot_base64()
        # The text goes before the image; Anthropic's guidance says this
        # improves click accuracy.
        messages: list[dict] = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": task_instruction},
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/png", "data": initial_screenshot},
                    },
                ],
            }
        ]

        for iteration in range(max_iterations):
            transcript.iterations_used = iteration + 1
            response = await client.messages.create(
                model=model,
                max_tokens=2048,
                tools=[{"type": "computer_toolset_20260801", "configs": {"zoom": {"enabled": False}}}],
                messages=messages,
            )

            assistant_content = [block.model_dump() for block in response.content]
            messages.append({"role": "assistant", "content": assistant_content})
            transcript.turns.append({"role": "assistant", "content": assistant_content})

            computer_calls = [
                b
                for b in response.content
                if getattr(b, "type", None) == "tool_use" and getattr(b, "toolset_name", None) == "computer"
            ]
            if not computer_calls:
                text_blocks = [b.text for b in response.content if getattr(b, "type", None) == "text"]
                transcript.final_text = "\n".join(text_blocks) if text_blocks else None
                break

            # Run batched actions in order. After the first failure the rest
            # are reported as not executed, because later actions usually
            # depend on earlier ones (for example a click before typing).
            tool_results = []
            failed = False
            for call in computer_calls:
                if failed:
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": call.id,
                            "toolset_name": "computer",
                            "content": NOT_EXECUTED_TEXT,
                            "is_error": True,
                        }
                    )
                    continue
                try:
                    result_content = await env.execute(call.name, call.input)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": call.id,
                            "toolset_name": "computer",
                            "content": result_content,
                        }
                    )
                except Exception as exc:
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": call.id,
                            "toolset_name": "computer",
                            "content": f"Error: {exc}",
                            "is_error": True,
                        }
                    )
                    failed = True

            messages.append({"role": "user", "content": tool_results})
            transcript.turns.append({"role": "user", "content": tool_results})
        else:
            transcript.final_text = f"[stopped after reaching max_iterations={max_iterations} without Claude finishing]"

        transcript.session_id = await env.get_session_cookie()

    finally:
        await env.close()

    return transcript