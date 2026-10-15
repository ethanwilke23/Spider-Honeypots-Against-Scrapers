"""Shared test setup."""
import pytest


@pytest.fixture(autouse=True)
def all_honeypots_active_by_default(monkeypatch):
    """
    Tests assume every honeypot variant is active, whatever HONEYPOT_VARIANT is
    set to in .env. Tests that need another setting override this.
    """
    monkeypatch.setattr("app.honeypots.active.active_setting", lambda: "all")