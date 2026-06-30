from pathlib import Path

import pytest

from igpsport_mcp.config import DEFAULT_CACHE_DIR, load_config
from igpsport_mcp.exceptions import ConfigError


def test_defaults_when_env_empty():
    cfg = load_config({})
    assert cfg.username is None
    assert cfg.password is None
    assert cfg.ftp is None
    assert cfg.lthr is None
    assert cfg.cache_dir == DEFAULT_CACHE_DIR
    assert cfg.log_level == "INFO"
    assert cfg.lang == "zh"


def test_reads_all_fields():
    cfg = load_config(
        {
            "IGPSPORT_USERNAME": "rider",
            "IGPSPORT_PASSWORD": "secret",
            "IGPSPORT_FTP": "250",
            "IGPSPORT_LTHR": "165",
            "IGPSPORT_CACHE_DIR": "/tmp/igp",
            "IGPSPORT_LOG_LEVEL": "DEBUG",
        }
    )
    assert cfg.require_credentials() == ("rider", "secret")
    assert cfg.ftp == 250
    assert cfg.lthr == 165
    assert cfg.cache_dir == Path("/tmp/igp")
    assert cfg.log_level == "DEBUG"


def test_derived_paths():
    cfg = load_config({"IGPSPORT_CACHE_DIR": "/tmp/igp"})
    assert cfg.token_path == Path("/tmp/igp/token.json")
    assert cfg.db_path == Path("/tmp/igp/activities.db")
    assert cfg.fit_dir == Path("/tmp/igp/fit")


def test_require_credentials_raises_when_missing():
    cfg = load_config({"IGPSPORT_USERNAME": "rider"})
    with pytest.raises(ConfigError):
        cfg.require_credentials()


def test_invalid_int_raises():
    with pytest.raises(ConfigError):
        load_config({"IGPSPORT_FTP": "abc"})


class TestLangConfig:
    def test_lang_defaults_to_zh(self):
        cfg = load_config({})
        assert cfg.lang == "zh"

    def test_lang_from_env(self):
        cfg = load_config({"IGPSPORT_LANG": "en"})
        assert cfg.lang == "en"

    def test_lang_invalid_falls_back_to_zh(self):
        cfg = load_config({"IGPSPORT_LANG": "de"})
        assert cfg.lang == "zh"

    def test_lang_parameter_overrides_env(self):
        cfg = load_config({"IGPSPORT_LANG": "zh"}, lang="en")
        assert cfg.lang == "en"

    def test_lang_region_respected(self):
        """Verify region=cn still reads correctly alongside lang."""
        cfg = load_config({"IGPSPORT_REGION": "cn", "IGPSPORT_LANG": "en"})
        assert cfg.region == "cn"
        assert cfg.lang == "en"
