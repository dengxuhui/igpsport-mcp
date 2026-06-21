from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_fit() -> Path:
    path = FIXTURES / "sample.fit"
    if not path.exists():
        pytest.skip("tests/fixtures/sample.fit not present (gitignored real ride)")
    return path
