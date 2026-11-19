import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import config

# The tests use their own fixed set of swaps, so editing the swaps in config.py
# (which is what config.py is for) never breaks them.
config.NUDGE_ARMS = {
    "walk": "Take a 2-minute walk",
    "fidget": "Grab a fidget toy or stress ball",
    "switch_task": "Switch to a different task for a few minutes",
    "water": "Get a glass of water",
    "breathe": "Do 5 slow breaths with your hands on the desk",
    "stretch": "Stand up and stretch your arms over your head",
    "hands_busy": "Hold something in both hands (pen, mug, putty)",
    "close_tab": "Close this tab and write down what you came here for",
}
config.NUDGE_ARMS_BY_TRIGGER = {
    "habit": ["walk", "fidget", "switch_task", "water", "breathe", "stretch", "hands_busy"],
    "doomscroll": ["walk", "switch_task", "water", "breathe", "stretch", "close_tab"],
}

from evals import synthetic  # noqa: E402  (after the swaps are pinned)

END = 1793534400.0   # a fixed "now" so every run sees the same data


@pytest.fixture(scope="session")
def demo_db(tmp_path_factory):
    path = str(tmp_path_factory.mktemp("demo") / "habits.db")
    synthetic.generate(path, days=28, seed=7, end=END)
    return path


@pytest.fixture
def empty_db(tmp_path):
    return str(tmp_path / "habits.db")
