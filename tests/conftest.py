import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return ROOT


@pytest.fixture
def rng():
    import numpy as np

    return np.random.default_rng(20260829)


@pytest.fixture(scope="session")
def resources():
    from trope.operators.base import load_resources

    return load_resources()


@pytest.fixture(scope="session")
def synthetic():
    from trope.data.synthetic import synthetic_dataset

    return synthetic_dataset(n=8, seed=0)


@pytest.fixture
def mock_backend(synthetic):
    from trope.backends.base import CallCounter, MeteredBackend
    from trope.backends.mock import MockBackend

    return MeteredBackend(MockBackend(synthetic, seed=0), CallCounter())
