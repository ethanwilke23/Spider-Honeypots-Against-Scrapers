"""
Unit tests for the Claude computer-use harness's pure logic and spending guard.

ComputerEnvironment.execute() and a real run_agent() call are not tested
here: they need a browser and a paid API key respectively.
"""
from agents.claude_computer_use.environment import parse_modifiers, translate_key_combo


def test_translate_key_combo_simple_named_key():
    assert translate_key_combo("Return") == "Enter"
    assert translate_key_combo("Tab") == "Tab"


def test_translate_key_combo_with_modifier():
    # Single characters keep their case; Playwright accepts either.
    assert translate_key_combo("ctrl+s") == "Control+s"
    assert translate_key_combo("alt+Tab") == "Alt+Tab"


def test_translate_key_combo_single_letter():
    assert translate_key_combo("a") == "a"


def test_parse_modifiers_single_and_combo():
    assert parse_modifiers("ctrl") == ["Control"]
    assert parse_modifiers("ctrl+shift") == ["Control", "Shift"]


def test_parse_modifiers_none_returns_empty():
    assert parse_modifiers(None) == []


# Spending guard: these tests check that the paid path is locked without
# touching the network.

import asyncio

import pytest

from agents.claude_computer_use.agent_loop import DEFAULT_TASK_INSTRUCTION, SpendNotConfirmedError, run_agent


def test_run_agent_refuses_without_confirm_spend():
    with pytest.raises(SpendNotConfirmedError):
        asyncio.run(run_agent("http://127.0.0.1:8000"))


def test_run_agent_refuses_even_if_api_key_is_set(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-not-a-real-key")
    with pytest.raises(SpendNotConfirmedError):
        asyncio.run(run_agent("http://127.0.0.1:8000", confirm_spend=False))


def test_task_text_names_the_cover_story_company():
    assert "Dunwoodie Data Analytics" in DEFAULT_TASK_INSTRUCTION