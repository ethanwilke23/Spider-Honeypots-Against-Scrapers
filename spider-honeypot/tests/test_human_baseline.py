"""
Unit tests for the synthetic human-behaviour baseline's random choices.

run_session() needs a real browser; run `python -m agents.human_baseline.run`
against a running server to try it.
"""
import random
from collections import Counter

from agents.human_baseline.simulator import (
    HumanProfile,
    choose_link,
    decide_back,
    sample_dwell,
    sample_target_pages,
)

PROFILE = HumanProfile()


def test_session_length_stays_within_the_profile_range():
    rng = random.Random(1)
    lengths = {sample_target_pages(rng, PROFILE) for _ in range(500)}
    assert min(lengths) == PROFILE.pages_min and max(lengths) == PROFILE.pages_max


def test_dwell_times_vary_and_stay_within_limits():
    rng = random.Random(2)
    dwells = [sample_dwell(rng, PROFILE) for _ in range(1000)]
    assert all(PROFILE.dwell_min_seconds <= d <= PROFILE.dwell_max_seconds for d in dwells)
    assert len({round(d, 1) for d in dwells}) > 50


def test_same_seed_makes_the_same_choices():
    def sequence(seed):
        rng = random.Random(seed)
        pages = sample_target_pages(rng, PROFILE)
        dwells = [sample_dwell(rng, PROFILE) for _ in range(5)]
        links = [choose_link(rng, ["/a", "/b", "/c"], set(), "/", PROFILE) for _ in range(5)]
        return pages, dwells, links

    assert sequence(7) == sequence(7)
    assert sequence(7) != sequence(8)


def test_current_page_is_never_chosen_and_nothing_to_click_gives_none():
    rng = random.Random(3)
    assert all(choose_link(rng, ["/a", "/b"], set(), "/a", PROFILE) == "/b" for _ in range(50))
    assert choose_link(rng, ["/a"], set(), "/a", PROFILE) is None
    assert choose_link(rng, [], set(), "/", PROFILE) is None


def test_unseen_links_are_preferred_to_seen_ones():
    rng = random.Random(4)
    counts = Counter(choose_link(rng, ["/seen", "/new"], {"/seen"}, "/", PROFILE) for _ in range(3000))
    assert counts["/new"] > 2 * counts["/seen"]
    assert counts["/seen"] > 0  # people do revisit pages


def test_going_back_needs_a_page_to_go_back_to():
    rng = random.Random(5)
    assert not any(decide_back(rng, PROFILE, history_length=1) for _ in range(200))
    assert any(decide_back(rng, PROFILE, history_length=3) for _ in range(200))