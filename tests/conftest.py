import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from evals import synthetic

END = 1793534400.0   # a fixed "now" so every run sees the same data


@pytest.fixture(scope="session")
def demo_db(tmp_path_factory):
    path = str(tmp_path_factory.mktemp("demo") / "habits.db")
    synthetic.generate(path, days=28, seed=7, end=END)
    return path


@pytest.fixture
def empty_db(tmp_path):
    return str(tmp_path / "habits.db")
