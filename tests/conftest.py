from pathlib import Path

import pytest

from igpsport_mcp import config

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def isolate_config_file(tmp_path_factory, monkeypatch):
    """Keep tests away from the developer's real ~/.igpsport-mcp/config.json.

    ``load_config`` reads (and the wizard writes) the module-level
    ``CONFIG_FILE``. Point it at a throwaway path so credentials living in a
    real home dir can't leak into assertions, and tests can't clobber it.
    """
    isolated = tmp_path_factory.mktemp("igpsport-home") / "config.json"
    monkeypatch.setattr(config, "CONFIG_FILE", isolated)


@pytest.fixture
def sample_fit() -> Path:
    path = FIXTURES / "sample.fit"
    if not path.exists():
        pytest.skip("tests/fixtures/sample.fit not present (gitignored real ride)")
    return path
