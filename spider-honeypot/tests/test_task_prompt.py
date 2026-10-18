"""Unit tests for the shared task prompt."""
import pytest

from agents.shared.task import AGENTS_WITH_TASK, TASK_CORE, TASK_KEYWORDS, get_task_instruction

# Words that would give away the experiment or steer the agent about the traps.
FORBIDDEN_WORDS = ["honeypot", "trap", "canary", "robots", "decoy", "experiment"]


def test_every_agent_gets_the_same_core_task():
    assert AGENTS_WITH_TASK == ("crawl4ai", "claude_computer_use", "claude_text_browser")
    for agent in AGENTS_WITH_TASK:
        assert get_task_instruction(agent).startswith(TASK_CORE)


def test_agent_specific_wording_differs():
    assert get_task_instruction("crawl4ai") != get_task_instruction("claude_computer_use")


@pytest.mark.parametrize("agent", AGENTS_WITH_TASK)
def test_task_text_does_not_mention_the_traps(agent):
    text = get_task_instruction(agent).lower()
    for word in FORBIDDEN_WORDS:
        assert word not in text


@pytest.mark.parametrize("agent", AGENTS_WITH_TASK)
def test_task_names_the_cover_story_company(agent):
    assert "Dunwoodie Data Analytics" in get_task_instruction(agent)


def test_unknown_agent_is_rejected():
    with pytest.raises(ValueError):
        get_task_instruction("playwright_baseline")


def test_harnesses_use_the_shared_text():
    from agents.claude_computer_use.agent_loop import DEFAULT_TASK_INSTRUCTION as claude_task

    assert claude_task == get_task_instruction("claude_computer_use")
    assert TASK_KEYWORDS  # non-empty list used by Crawl4AI